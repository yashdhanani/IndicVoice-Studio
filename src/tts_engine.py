"""Local Indian TTS engine: sherpa-onnx VITS (MMS) on CPU + human-sounding playback.

Typical use::

    from src.tts_engine import TTSPool
    tts = TTSPool()
    tts.speak("નમસ્તે, હું તમારી મદદ કરી શકું છું.")      # language auto-detected

Streaming (audio starts while the text is still arriving)::

    tts.speak_sentences(sentence_iterator, cancel_event=stop)   # barge-in aware

The :class:`~src.humanizer.Humanizer` shapes prosody (per-clause pauses, speed
jitter, -55 dB room tone) and :class:`~src.humanizer.SeamBlender` crossfades
chunk joins, so back-to-back sentences do not sound stitched together.
"""

from __future__ import annotations

import math
import sys
import threading
import time
from collections import deque
from pathlib import Path

import numpy as np
import sounddevice as sd
from scipy import signal
from scipy.io import wavfile

from . import config
from .config import SAMPLE_RATE, detect_lang, resolve_lang
from .humanizer import Humanizer, SeamBlender
from .text_normalizer import TextNormalizer
from .translit import localize_text


# --------------------------------------------------------------------------- #
# Playback
# --------------------------------------------------------------------------- #


class AudioPlayer:
    """Persistent mono output stream with a chunk queue and instant cancel."""

    def __init__(self, target_rate: int = SAMPLE_RATE, device: int | str | None = None):
        self.target_rate = int(target_rate)
        self.device = device
        info = sd.query_devices(device, "output")
        self.device_rate = int(info.get("default_samplerate") or self.target_rate)
        self._chunks: deque[np.ndarray] = deque()
        self._lock = threading.Lock()
        self._pending = 0
        self._stream: sd.OutputStream | None = None
        self._tail = float(info.get("default_low_output_latency") or 0.05)

    # -- stream lifecycle --------------------------------------------------- #

    def _ensure_stream(self) -> sd.OutputStream:
        if self._stream is None:
            self._stream = sd.OutputStream(
                samplerate=self.device_rate,
                channels=1,
                dtype="float32",
                device=self.device,
                latency="low",
                callback=self._callback,
            )
            self._stream.start()
        return self._stream

    def _callback(self, outdata, frames, time_info, status) -> None:  # noqa: ANN001
        filled = 0
        with self._lock:
            while filled < frames and self._chunks:
                chunk = self._chunks[0]
                take = min(len(chunk), frames - filled)
                outdata[filled:filled + take, 0] = chunk[:take]
                if take == len(chunk):
                    self._chunks.popleft()
                else:
                    self._chunks[0] = chunk[take:]
                filled += take
            self._pending = max(0, self._pending - filled)
        if filled < frames:
            outdata[filled:, 0] = 0.0

    def _resample(self, samples: np.ndarray, rate: int) -> np.ndarray:
        if rate == self.device_rate:
            return samples.astype(np.float32, copy=False)
        divisor = math.gcd(int(rate), int(self.device_rate))
        return signal.resample_poly(samples, self.device_rate // divisor, rate // divisor).astype(np.float32)

    # -- public API --------------------------------------------------------- #

    def push(self, samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> None:
        if samples is None or len(samples) == 0:
            return
        self._ensure_stream()
        audio = self._resample(np.asarray(samples, dtype=np.float32), sample_rate)
        with self._lock:
            self._chunks.append(audio)
            self._pending += len(audio)

    @property
    def is_speaking(self) -> bool:
        with self._lock:
            return self._pending > 0

    def wait_until_done(self, timeout: float | None = None, poll: float = 0.02) -> bool:
        deadline = None if timeout is None else time.monotonic() + timeout
        while self.is_speaking:
            if deadline is not None and time.monotonic() > deadline:
                return False
            time.sleep(poll)
        if self._tail:
            time.sleep(min(self._tail, 0.15))
        return True

    def cancel(self) -> None:
        """Drop queued audio immediately (used for barge-in)."""
        with self._lock:
            self._chunks.clear()
            self._pending = 0
        stream = self._stream
        if stream is not None:
            try:
                stream.abort()
                stream.start()
            except Exception:
                pass

    def close(self) -> None:
        self.cancel()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None

    def __enter__(self) -> "AudioPlayer":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


# --------------------------------------------------------------------------- #
# Process-wide model cache
# --------------------------------------------------------------------------- #
#: A voice costs ~1.2 s (Supertonic) to ~0.4 s (MMS) to load. Calls arrive
#: concurrently, so the loaded sherpa objects are shared for the whole process
#: and serialised per model, because ``generate`` is not re-entrant.
_TTS_CACHE: dict[tuple, "_SharedTTS"] = {}
_TTS_CACHE_LOCK = threading.Lock()


def _normalize_level(
    audio: np.ndarray, target_rms: float = 0.07, peak_ceiling: float = 0.97
) -> np.ndarray:
    """Even out loudness so every voice arrives at the same level.

    The tiny Matcha voices come out ~8 dB quieter than MMS; a browser or a phone
    line then sounds muffled. Gain is RMS-matched and peak-limited.
    """
    audio = np.asarray(audio, dtype=np.float32)
    if audio.size == 0:
        return audio
    rms = float(np.sqrt(np.mean(np.square(audio))))
    if rms <= 1e-5:
        return audio
    gain = target_rms / rms
    peak = float(np.abs(audio).max()) * gain
    if peak > peak_ceiling:
        gain *= peak_ceiling / peak
    return (audio * gain).astype(np.float32)


class _SharedTTS:
    """One loaded voice plus the lock that serialises generation on it."""

    __slots__ = ("tts", "sample_rate", "vocab", "lock")

    def __init__(self, tts, sample_rate: int, vocab: set[str] | None):
        self.tts = tts
        self.sample_rate = int(sample_rate)
        self.vocab = vocab
        self.lock = threading.Lock()


def _build_shared_tts(
    lang: str,
    backend: str,
    num_threads: int,
    provider: str,
    model_dir: Path | None = None,
) -> _SharedTTS:
    """Load (or fetch from cache) the sherpa-onnx voice for ``lang``."""
    import sherpa_onnx

    if backend == "tiny":
        # tiny runs on onnxruntime, not sherpa: its thread count comes from
        # the explicit knob (0 = ORT default), not the sherpa num_threads arg
        num_threads = config.TTS_NUM_THREADS
    key = (lang, backend, num_threads, provider, str(model_dir or ""))
    shared = _TTS_CACHE.get(key)
    if shared is not None:
        return shared

    with _TTS_CACHE_LOCK:
        shared = _TTS_CACHE.get(key)
        if shared is not None:
            return shared

        if backend == "tiny":
            directory = config.TINY_DIRS[lang]
            if str(directory) not in sys.path:
                sys.path.insert(0, str(directory))
            from indic_tiny_tts import TinyTTSOnnx

            tts = TinyTTSOnnx.from_pretrained(
                str(directory), threads=num_threads or None)
            shared = _SharedTTS(tts, int(tts.sample_rate), None)
        elif backend == "supertonic":
            source = config.SUPERTONIC_DIR
            tts_config = sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(
                    supertonic=sherpa_onnx.OfflineTtsSupertonicModelConfig(
                        duration_predictor=str(source / "duration_predictor.int8.onnx"),
                        text_encoder=str(source / "text_encoder.int8.onnx"),
                        vector_estimator=str(source / "vector_estimator.int8.onnx"),
                        vocoder=str(source / "vocoder.int8.onnx"),
                        tts_json=str(source / "tts.json"),
                        unicode_indexer=str(source / "unicode_indexer.bin"),
                        voice_style=str(source / "voice.bin"),
                    ),
                    provider=provider,
                    num_threads=num_threads,
                    debug=False,
                ),
                max_num_sentences=1,
            )
            tts = sherpa_onnx.OfflineTts(tts_config)
            shared = _SharedTTS(tts, int(tts.sample_rate), None)
        else:
            directory = Path(model_dir) if model_dir else config.tts_model_dir(lang)
            model, tokens = directory / "model.onnx", directory / "tokens.txt"
            if not model.exists() or not tokens.exists():
                raise FileNotFoundError(
                    f"TTS voice for '{lang}' not found in {directory}.\n"
                    f"Run:  python -m src.download_models --langs {lang}"
                )
            tts_config = sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(
                    vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                        model=str(model),
                        lexicon="",
                        tokens=str(tokens),
                        data_dir="",
                        dict_dir="",
                    ),
                    provider=provider,
                    num_threads=num_threads,
                    debug=False,
                ),
                max_num_sentences=1,
            )
            tts = sherpa_onnx.OfflineTts(tts_config)
            #: Characters this voice can pronounce (the rest is transliterated).
            vocab = {
                line.split()[0]
                for line in tokens.read_text(encoding="utf-8").splitlines()
                if line.strip()
            }
            shared = _SharedTTS(tts, int(tts.sample_rate), vocab)

        _TTS_CACHE[key] = shared
        return shared


# --------------------------------------------------------------------------- #
# TTS
# --------------------------------------------------------------------------- #


class TTSEngine:
    """One loaded VITS/MMS voice for a single language."""

    def __init__(
        self,
        lang: str = "hi",
        model_dir: str | Path | None = None,
        num_threads: int = 4,
        provider: str = "cpu",
        sid: int = 0,
        player: AudioPlayer | None = None,
        humanizer: Humanizer | None = None,
        backend: str | None = None,
    ):
        import sherpa_onnx

        self.lang = resolve_lang(lang)
        self.normalizer = TextNormalizer(self.lang)
        self.sid = sid
        self.num_threads = num_threads

        self.backend = backend or config.tts_backend(self.lang)
        shared = _build_shared_tts(
            self.lang, self.backend, num_threads, provider,
            Path(model_dir) if model_dir else None,
        )
        self._tts = shared.tts
        self.sample_rate = shared.sample_rate
        #: ``None`` for Supertonic (31-language indexer); for MMS the set of
        #: characters this voice can pronounce, so text can be transliterated.
        self._vocab = shared.vocab
        self._gen_lock = shared.lock

        self._player = player
        self.humanizer = humanizer or Humanizer(sample_rate=self.sample_rate)
        self.humanizer = self.humanizer.at_sample_rate(self.sample_rate)
        self._seam = SeamBlender(sample_rate=self.sample_rate)

    # -- properties --------------------------------------------------------- #

    @property
    def num_speakers(self) -> int:
        if self.backend == "tiny":
            return 2                                   # female / male (sid 0/1)
        return int(self._tts.num_speakers)

    @property
    def player(self) -> AudioPlayer:
        if self._player is None:
            self._player = AudioPlayer(target_rate=self.sample_rate)
        return self._player

    # -- synthesis ---------------------------------------------------------- #

    def prepare(self, text: str) -> str:
        """Normalise numbers/currency, then make every word pronounceable."""
        spoken = self.normalizer.normalize(text or "").strip()
        if not spoken:
            return ""
        if self.backend == "supertonic":
            return spoken
        return localize_text(spoken, self.lang, self._vocab)

    def synthesize(
        self,
        text: str,
        speed: float = 1.0,
        normalize: bool = True,
        cancel_event: threading.Event | None = None,
    ) -> np.ndarray:
        """Return raw float32 audio for ``text`` (no playback, no humanising)."""
        spoken = self.prepare(text) if normalize else (text or "").strip()
        if not spoken:
            return np.zeros(0, dtype=np.float32)
        if cancel_event is not None and cancel_event.is_set():
            return np.zeros(0, dtype=np.float32)

        callback = None
        if cancel_event is not None:
            def callback(_samples, _progress, _ev=cancel_event) -> int:
                return 0 if _ev.is_set() else 1

        with self._gen_lock:      # one generation at a time per shared model
            if self.backend == "tiny":
                audio = self._tts.synthesize(
                    spoken,
                    voice="male" if self.sid == 1 else "female",
                    speed=float(speed) * config.TINY_SPEED,
                )
                return _normalize_level(
                    np.asarray(audio, dtype=np.float32).reshape(-1),
                    target_rms=config.TINY_TARGET_RMS,
                )
            if self.backend == "supertonic":
                import sherpa_onnx as _so

                gen = _so.GenerationConfig()
                gen.sid = self.sid
                gen.num_steps = config.SUPERTONIC_STEPS
                gen.speed = float(speed)
                gen.extra["lang"] = "en" if self.lang == "en" else "hi"
                audio = self._tts.generate(spoken, gen)
            else:
                audio = self._tts.generate(
                    spoken, sid=self.sid, speed=float(speed), callback=callback
                )
        return np.asarray(audio.samples, dtype=np.float32)

    def save_wav(self, path: str | Path, samples: np.ndarray, sample_rate: int | None = None) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        rate = int(sample_rate or self.sample_rate)
        clipped = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
        wavfile.write(str(path), rate, (clipped * 32767).astype(np.int16))
        return path

    # -- humanised rendering ------------------------------------------------ #

    def render_sentence(
        self,
        text: str,
        speed: float = 1.0,
        cancel_event: threading.Event | None = None,
        pause_after: bool = True,
    ) -> np.ndarray:
        """Synthesise one sentence clause by clause, with pauses and room tone."""
        humanizer = self.humanizer
        pieces: list[np.ndarray] = []
        clauses = self._long_clauses(text)
        if not clauses:
            return np.zeros(0, dtype=np.float32)

        for index, (clause, pause) in enumerate(clauses):
            if cancel_event is not None and cancel_event.is_set():
                break
            rate = speed * humanizer.speed_for(index)
            audio = self.synthesize(clause, speed=rate, cancel_event=cancel_event)
            if audio.size == 0:
                continue
            pieces.append(humanizer.with_room_tone(audio))
            if pause > 0 and not (index == len(clauses) - 1 and not pause_after):
                pieces.append(humanizer.silence(pause))
        return np.concatenate(pieces) if pieces else np.zeros(0, dtype=np.float32)

    @staticmethod
    def split_head(text: str, min_head: int = 3, max_head: int = 52) -> tuple[str, str]:
        """Split the opening clause off so playback can start before the rest.

        A whole reply sentence takes 350-600 ms to synthesise on this CPU; its
        first clause takes 60-200 ms. Speaking the clause while the remainder is
        still being built removes that wait from every turn.
        """
        text = (text or "").strip()
        cuts = [text.find(p) for p in (",", "?", ";", "।", ":", "｜")]
        cuts = [c for c in cuts if min_head <= c <= max_head]
        if not cuts:
            return text, ""
        cut = min(cuts) + 1
        head, tail = text[:cut].strip(), text[cut:].strip()
        return (head, tail) if head and tail else (text, "")

    def _long_clauses(self, text: str) -> list[tuple[str, float]]:
        """Split only genuinely long text; short sentences stay one VITS pass.

        Synthesising each clause separately restarts the model's prosody, which
        is what made short replies sound robotic. One pass keeps F0 and rhythm
        continuous, so we split only when the voices start to drift (~140 chars).
        """
        text = (text or "").strip()
        if not text:
            return []
        if not self.humanizer.enabled or len(text) <= 140:
            return [(text, self.humanizer.clause_pause(final=True))]
        return self.humanizer.clauses(text)

    def _emit(self, audio: np.ndarray) -> None:
        """Crossfade into the persistent seam blender and queue for playback."""
        if audio is None or audio.size == 0:
            return
        ready = self._seam.push(audio)
        if ready.size:
            self.player.push(ready, self.sample_rate)

    def finish(self) -> None:
        """Flush the seam blender's held tail."""
        tail = self._seam.flush()
        if tail.size:
            self.player.push(tail, self.sample_rate)

    def speak(
        self,
        text: str,
        speed: float = 1.0,
        wait: bool = True,
        cancel_event: threading.Event | None = None,
    ) -> np.ndarray:
        """Synthesise and play one sentence immediately."""
        audio = self.render_sentence(text, speed=speed, cancel_event=cancel_event)
        self._emit(audio)
        if wait:
            self.finish()
            self.player.wait_until_done()
        return audio

    def synthesize_stream(
        self,
        text: str,
        speed: float = 1.0,
        play: bool = True,
        out_path: str | Path | None = config.AUDIO_OUT_DIR / "output.wav",
        cancel_event: threading.Event | None = None,
    ) -> np.ndarray:
        """Sentence-by-sentence synthesis: the first sentence plays while the rest renders."""
        pieces: list[np.ndarray] = []
        sentences = self.normalizer.split_sentences(text) or ([text] if text.strip() else [])

        for sentence in sentences:
            if cancel_event is not None and cancel_event.is_set():
                break
            audio = self.render_sentence(sentence, speed=speed, cancel_event=cancel_event)
            if audio.size == 0:
                continue
            pieces.append(audio)
            if play:
                self._emit(audio)

        full = np.concatenate(pieces) if pieces else np.zeros(0, dtype=np.float32)
        if play:
            self.finish()
            self.player.wait_until_done()
        if out_path:
            self.save_wav(out_path, full)
        return full

    def speak_sentences(
        self,
        sentences,
        speed: float = 1.0,
        cancel_event: threading.Event | None = None,
    ) -> np.ndarray:
        """Speak sentences as they are produced (LLM token stream -> speech)."""
        pieces: list[np.ndarray] = []
        head_done = False
        for sentence in sentences:
            if cancel_event is not None and cancel_event.is_set():
                break
            chunks = [sentence]
            if not head_done:
                head, tail = self.split_head(sentence)
                if tail:
                    chunks = [head, tail]
                head_done = True
            for chunk in chunks:
                audio = self.render_sentence(chunk, speed=speed, cancel_event=cancel_event)
                if audio.size:
                    pieces.append(audio)
                    self._emit(audio)
        self.finish()
        if pieces:
            self.player.wait_until_done()
        return np.concatenate(pieces) if pieces else np.zeros(0, dtype=np.float32)


class TTSPool:
    """Lazily loaded voices per language, with script-based routing."""

    def __init__(
        self,
        langs: tuple[str, ...] | None = None,
        num_threads: int = 4,
        player: AudioPlayer | None = None,
        default_lang: str = "hi",
        humanize: bool = True,
    ):
        requested = tuple(dict.fromkeys(resolve_lang(l) for l in (langs or config.LANG_NAMES)))
        # only offer voices that are actually downloaded (any backend)
        self.langs = tuple(
            l for l in requested
            if config.tts_backend(l) != "mms"
            or (config.tts_model_dir(l) / "model.onnx").exists()
        ) or (resolve_lang(default_lang),)
        self.num_threads = num_threads
        self.default_lang = resolve_lang(default_lang)
        self._player = player
        self._engines: dict[str, TTSEngine] = {}
        self.humanizer = Humanizer(
            sample_rate=SAMPLE_RATE,
            enabled=humanize,
            filler_factory=self._synthesize_filler,
        )

    # -- engine management -------------------------------------------------- #

    def _synthesize_filler(self, lang: str, phrase: str) -> np.ndarray:
        """Render a short filler clip once, without humanising it again."""
        code = resolve_lang(lang)
        if code not in self.langs:
            code = self.default_lang
        return self.engine(code).synthesize(phrase)

    @property
    def player(self) -> AudioPlayer:
        if self._player is None:
            self._player = self.engine(self.default_lang).player
        return self._player

    def engine(self, lang: str | None = None) -> TTSEngine:
        code = resolve_lang(lang) if lang else self.default_lang
        if code not in self._engines:
            engine = TTSEngine(lang=code, num_threads=self.num_threads, player=self._player,
                               humanizer=self.humanizer)
            if self._player is None:
                self._player = engine.player
            self._engines[code] = engine
        return self._engines[code]

    def loaded(self, lang: str) -> bool:
        return resolve_lang(lang) in self._engines

    # -- speaking ----------------------------------------------------------- #

    def backchannel(self, lang: str | None = None) -> bool:
        """Play an instant acknowledgment clip ("हाँ जी...") if one is available."""
        code = resolve_lang(lang) if lang else self.default_lang
        if code not in self.langs:
            code = self.default_lang
        engine = self.engine(code)
        audio = engine.humanizer.filler(code)
        if audio is None or audio.size == 0:
            return False
        self.player.push(audio, engine.sample_rate)
        return True

    def speak(
        self,
        text: str,
        lang: str | None = None,
        speed: float = 1.0,
        wait: bool = True,
        cancel_event: threading.Event | None = None,
    ) -> np.ndarray:
        """Speak ``text`` in ``lang`` (auto-detected from script when omitted)."""
        code = resolve_lang(lang) if lang else detect_lang(text, self.default_lang)
        if code not in self.langs:
            code = self.default_lang
        return self.engine(code).speak(text, speed=speed, wait=wait, cancel_event=cancel_event)

    def synthesize_stream(self, text: str, lang: str | None = None, **kwargs) -> np.ndarray:
        code = resolve_lang(lang) if lang else detect_lang(text, self.default_lang)
        if code not in self.langs:
            code = self.default_lang
        return self.engine(code).synthesize_stream(text, **kwargs)

    def speak_sentences(
        self,
        sentences,
        lang: str | None = None,
        preferred_lang: str | None = None,
        speed: float = 1.0,
        cancel_event: threading.Event | None = None,
    ) -> np.ndarray:
        """Speak a mixed-language sentence stream, routing each sentence by script.

        ``preferred_lang`` only breaks ties between languages that share a script
        (Devanagari -> hi/mr, Bengali -> bn/as) while still letting a Latin-script
        Hinglish sentence use the English voice.
        """
        pieces: list[np.ndarray] = []
        current: TTSEngine | None = None
        head_done = False
        fallback = resolve_lang(preferred_lang) if preferred_lang else self.default_lang
        for sentence in sentences:
            if cancel_event is not None and cancel_event.is_set():
                break
            chunks = [sentence]
            if not head_done:
                head, tail = TTSEngine.split_head(sentence)
                if tail:
                    chunks = [head, tail]
                head_done = True
            for chunk in chunks:
                code = resolve_lang(lang) if lang else detect_lang(chunk, fallback)
                if code not in self.langs:
                    code = self.default_lang
                engine = self.engine(code)
                if current is not None and current is not engine:
                    current.finish()      # flush the previous voice's seam tail
                current = engine
                audio = engine.render_sentence(chunk, speed=speed, cancel_event=cancel_event)
                if audio.size:
                    pieces.append(audio)
                    engine._emit(audio)   # noqa: SLF001 - same package
        if current is not None:
            current.finish()
        self.player.wait_until_done()
        return np.concatenate(pieces) if pieces else np.zeros(0, dtype=np.float32)

    def close(self) -> None:
        if self._player is not None:
            self._player.close()
