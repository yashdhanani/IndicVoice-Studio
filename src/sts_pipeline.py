"""Real-time speech-to-speech voice agent on CPU.

    mic (16 kHz) -> Silero VAD (natural pauses + barge-in) -> Whisper/Zipformer STT
        -> LLM (Ollama or any OpenAI-compatible endpoint) -> streaming sentences
        -> sherpa-onnx TTS -> speaker

The first sentence is spoken while the LLM is still generating the rest, which
is what keeps the conversation feeling live on a laptop GPU-less CPU.

Quick smoke tests::

    python -m src.sts_pipeline --say "नमस्ते, मैं आपकी मदद कर सकता हूँ।"
    python -m src.sts_pipeline --utterance "मुझे कल दिल्ली जाना है" --llm-backend ollama
    python -m src.sts_pipeline --list-devices
    python -m src.sts_pipeline                        # live microphone loop
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import queue
import sys
import threading
import time
import io
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np
import sounddevice as sd

from . import config
from .config import LANG_NAMES, SAMPLE_RATE, detect_lang, resolve_lang
from .text_normalizer import SentenceSplitter
from .translit import localize_text
from .tts_engine import AudioPlayer, TTSPool

#: VAD frame size expected by Silero (32 ms at 16 kHz).
VAD_WINDOW = 512
VAD_WINDOW_SECONDS = VAD_WINDOW / SAMPLE_RATE

#: Latin-script words needed before a turn may switch the session language.
#: Below this a stray English word in a Hindi sentence would flip the call.
_LATIN_SWITCH_MIN_WORDS = 3


# --------------------------------------------------------------------------- #
# Speech recognition
# --------------------------------------------------------------------------- #


class STTEngine:
    """Offline speech recognition for Hindi / Gujarati / English.

    ``indic`` uses AI4Bharat's IndicConformer (NeMo CTC, INT8) per language — the
    most accurate CPU option for Hindi and Gujarati (0.3-0.8 s per utterance).
    ``auto`` picks it for languages that have an export and Whisper otherwise.
    """

    def __init__(
        self,
        backend: str = "auto",
        lang: str = "hi",
        model: str = config.DEFAULT_STT_MODEL,
        num_threads: int = config.STT_NUM_THREADS,
        model_dir: Path | None = None,
    ):
        import sherpa_onnx

        self.lang = resolve_lang(lang)
        self.model = model
        self.num_threads = num_threads
        #: recognisers are shared process-wide, so decoding is serialised
        self._lock = threading.Lock()
        self.backend = self._resolve_backend(backend, self.lang)

        if self.backend == "ctc":
            # wav2vec2 export from colab/assamese_asr_export.ipynb
            from .asr_ctc import CtcRecognizer

            self._recognizer = None
            self._ctc = CtcRecognizer(num_threads=num_threads)
            return

        if self.backend == "groq":
            # no local model: recognition happens on Groq's Whisper servers
            if self.lang not in config.GROQ_STT_LANGS:
                raise ValueError(f"Groq Whisper has no '{self.lang}' support")
            if model == config.DEFAULT_STT_MODEL:
                model = config.GROQ_STT_MODEL
            self.model = model
            self._recognizer = None
            self._cloud = _GroqWhisper(lang=self.lang, model=model,
                                       prompt=_WHISPER_PROMPTS.get(self.lang, ""))
            return

        if self.backend == "indic":
            directory = Path(model_dir or config.indic_asr_dir(self.lang))
            model_path = config.indic_asr_model(self.lang)
            tokens = config.indic_asr_tokens(self.lang)
            if not model_path.exists():
                raise FileNotFoundError(
                    f"IndicConformer model for '{self.lang}' not found in {directory}.\n"
                    f"Run:  python -m src.download_models --indic-asr {self.lang}"
                )
            self._recognizer = sherpa_onnx.OfflineRecognizer.from_nemo_ctc(
                model=str(model_path),
                tokens=str(tokens),
                num_threads=num_threads,
                sample_rate=SAMPLE_RATE,
                feature_dim=80,
                decoding_method="greedy_search",
                debug=False,
                provider="cpu",
            )
        elif self.backend == "whisper":
            encoder = config.stt_file(model, "encoder")
            decoder = config.stt_file(model, "decoder")
            tokens = config.stt_file(model, "tokens")
            if not encoder.exists():
                raise FileNotFoundError(
                    f"Whisper '{model}' not found in {config.stt_model_dir(model)}.\n"
                    f"Run:  python -m src.download_models --stt {model}"
                )
            self._recognizer = sherpa_onnx.OfflineRecognizer.from_whisper(
                encoder=str(encoder),
                decoder=str(decoder),
                tokens=str(tokens),
                language=self.lang,
                task="transcribe",
                num_threads=num_threads,
                decoding_method="greedy_search",
                debug=False,
                provider="cpu",
            )
        elif self.backend == "transducer":
            directory = Path(model_dir or config.TRANSDUCER_DIR)
            files = {p.name.lower(): p for p in directory.glob("*.onnx")}
            tokens = directory / "tokens.txt"
            encoder = next((p for k, p in sorted(files.items()) if "encoder" in k), None)
            decoder = next((p for k, p in sorted(files.items()) if "decoder" in k), None)
            joiner = next((p for k, p in sorted(files.items()) if "joiner" in k), None)
            if not (encoder and decoder and joiner and tokens.exists()):
                raise FileNotFoundError(
                    f"Streaming Zipformer files not found in {directory} "
                    "(need encoder*.onnx, decoder*.onnx, joiner*.onnx, tokens.txt)."
                )
            self._recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=str(encoder),
                decoder=str(decoder),
                joiner=str(joiner),
                tokens=str(tokens),
                num_threads=num_threads,
                sample_rate=SAMPLE_RATE,
                feature_dim=80,
                decoding_method="greedy_search",
                provider="cpu",
            )
        else:
            raise ValueError("STT backend must be 'auto', 'indic', 'whisper' or 'transducer'")

    @staticmethod
    def _resolve_backend(backend: str, lang: str) -> str:
        """Pick the recogniser that actually works for ``lang``."""
        backend = (backend or "auto").lower()
        if backend == "auto":
            if lang == "as" and config.asr_ctc_available():
                return "ctc"
            if (
                os.environ.get("GROQ_API_KEY")
                and config.STT_MODE != "accurate"
                and lang in config.STT_FAST_LANGS
            ):
                return "groq"
            if (
                config.STT_BACKEND_BY_LANG.get(lang) == "groq"
                and os.environ.get("GROQ_API_KEY")
            ):
                return "groq"
            return "indic" if lang in config.INDIC_ASR else "whisper"
        if backend == "indic" and lang not in config.INDIC_ASR:
            print(
                f"[stt] no IndicConformer export for '{lang}'; using Whisper.",
                file=sys.stderr,
            )
            return "whisper"
        return backend

    def _local_fallback(self) -> "STTEngine | None":
        """A local recogniser for this language, or ``None`` when there is none.

        Built lazily: most calls never need it, and a Conformer costs ~0.5 s and
        ~130 MB to load.
        """
        if not hasattr(self, "_fallback_engine"):
            engine = None
            if self.lang in config.INDIC_ASR:
                directory = config.indic_asr_dir(self.lang)
                if directory.is_dir():
                    try:
                        engine = shared_stt("indic", self.lang)
                    except Exception as exc:   # a missing model must not kill a call
                        print(f"[stt] local fallback unavailable: {exc}", file=sys.stderr)
            self._fallback_engine = engine
        return self._fallback_engine

    def transcribe(self, samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> str:
        audio = np.asarray(samples, dtype=np.float32).reshape(-1)
        if audio.size == 0:
            return ""
        if self.backend == "groq":
            text = self._cloud.transcribe(audio, sample_rate)
            if text and not _script_matches(text, self.lang):
                # Whisper occasionally drifts into another script entirely on a
                # short clip (measured: Tamil -> Arabic script, CER 1.0). Prefer
                # the local Conformer, which cannot wander off the language.
                local = self._local_fallback()
                if local is not None:
                    return local.transcribe(audio, sample_rate)
                return ""
            return text
        if self.backend == "ctc":
            with self._lock:
                return self._ctc.transcribe(audio, sample_rate)
        # the endpointing buffer always carries trailing silence; cutting it
        # makes decoding proportionally faster without touching the words
        with self._lock:
            stream = self._recognizer.create_stream()
            stream.accept_waveform(sample_rate, _trim_silence(audio, sample_rate))
            self._recognizer.decode_stream(stream)
        return (stream.result.text or "").strip()


def _trim_silence(samples: np.ndarray, sample_rate: int, keep: float = 0.10) -> np.ndarray:
    """Drop leading/trailing silence so the recogniser only sees speech.

    The speech gate must sit far below the loudest frame. It used to sit 24 dB
    under it (6 % of peak), which ate real speech: on a Hindi render the final
    ``है`` was quieter than that, 0.39 s of audio was cut, and the Conformer
    decoded the whole sentence as ``म`` -- decoding the same clip untrimmed
    returns ``मेरा ऑर्डर नंबर एक दो तीन है``. A Gujarati and an Odia render lost
    0.15-0.64 s the same way, which is what merged words in their transcripts.

    The gate now sits 34 dB under the peak and never below six times the clip's
    own noise floor (the 10th-percentile frame energy), so room tone is still
    removed and quiet word-final syllables are not.
    """
    frame = max(1, int(sample_rate * 0.02))
    count = len(samples) // frame
    if count < 4:
        return samples
    blocks = samples[: count * frame].reshape(count, frame)
    energy = np.sqrt((blocks.astype(np.float32) ** 2).mean(axis=1))
    peak = float(energy.max())
    if peak <= 0:
        return samples
    floor = float(np.percentile(energy, 10))
    gate = max(peak * 10 ** (-34 / 20), floor * 6.0, 1e-6)
    loud = np.flatnonzero(energy > gate)
    if loud.size == 0:
        return samples
    pad = int(sample_rate * keep)
    start = max(0, loud[0] * frame - pad)
    end = min(len(samples), (loud[-1] + 1) * frame + pad)
    return samples[start:end]


class _GroqWhisper:
    """Speech recognition through Groq's OpenAI-compatible Whisper endpoint.

    Roughly 0.3-0.6 s instead of the 1-3 s a CPU Conformer needs for the
    non-Hindi languages, and it covers Assamese natively (unlike the local
    Bengali-model workaround).
    """

    def __init__(self, lang: str, model: str, timeout: float = 20.0, prompt: str = ""):
        self.lang = lang
        self.model = model
        self.timeout = timeout
        self.prompt = prompt or ""
        self.api_key = os.environ.get("GROQ_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set; put it in .env to use the groq ASR backend."
            )
        self.url = "https://api.groq.com/openai/v1/audio/transcriptions"

    @staticmethod
    def _wav_bytes(samples: np.ndarray, sample_rate: int) -> bytes:
        if sample_rate != SAMPLE_RATE:
            n = max(1, int(len(samples) * SAMPLE_RATE / sample_rate))
            samples = np.interp(
                np.linspace(0, len(samples) - 1, n), np.arange(len(samples)), samples
            )
        pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(SAMPLE_RATE)
            handle.writeframes(pcm.tobytes())
        return buffer.getvalue()

    def transcribe(self, samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> str:
        boundary = "----IndicVoice" + uuid.uuid4().hex
        wav = self._wav_bytes(samples, sample_rate)
        fields = {"model": self.model, "language": self.lang,
                  "response_format": "json", "temperature": "0"}
        if self.prompt:
            # A native-script hint keeps Whisper's output in the right script and
            # adds sensible punctuation; without it short clips drift.
            fields["prompt"] = self.prompt
        body = bytearray()
        for name, value in fields.items():
            body += (
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n"
                f"{value}\r\n"
            ).encode("utf-8")
        body += (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f"filename=\"turn.wav\"\r\nContent-Type: audio/wav\r\n\r\n"
        ).encode("utf-8")
        body += wav + f"\r\n--{boundary}--\r\n".encode("utf-8")

        request = urllib.request.Request(
            self.url,
            data=bytes(body),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "IndicVoice/1.0 (+https://localhost)",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:200]
            raise RuntimeError(f"groq asr HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"cannot reach Groq ASR: {exc.reason}") from exc
        return (payload.get("text") or "").strip()


#: Native-script sentences that steer Whisper to the right script and style.
#: Short, phone-like, written in the caller's own language.
_WHISPER_PROMPTS = {
    "hi": "नमस्ते, मैं अपने ऑर्डर के बारे में बात कर रहा हूँ।",
    "gu": "નમસ્તે, હું મારા ઓર્ડર વિશે વાત કરું છું.",
    "mr": "नमस्कार, मी माझ्या ऑर्डरबद्दल बोलत आहे.",
    "bn": "নমস্কাৰ, আমি মোৰ অৰ্ডাৰৰ বিষয়ে কথা পাতিছোঁ।",
    "ta": "வணக்கம், நான் என் ஆர்டர் பற்றி பேசுகிறேன்.",
    "te": "నమస్తే, నేను నా ఆర్డర్ గురించి మాట్లాడుతున్నాను.",
    "kn": "ನಮಸ್ಕಾರ, ನಾನು ನನ್ನ ಆರ್ಡರ್ ಬಗ್ಗೆ ಮಾತನಾಡುತ್ತಿದ್ದೇನೆ.",
    "ml": "നമസ്കാരം, ഞാൻ എന്റെ ഓർഡറിനെക്കുറിച്ച് സംസാരിക്കുന്നു.",
    "pa": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ, ਮੈਂ ਆਪਣੇ ਆਰਡਰ ਬਾਰੇ ਗੱਲ ਕਰ ਰਿਹਾ ਹਾਂ।",
    "or": "ନମସ୍କାର, ମୁଁ ମୋ ଅର୍ଡର ବିଷୟରେ କଥା ହେଉଛି।",
    "as": "নমস্কাৰ, মই মোৰ অৰ্ডাৰৰ বিষয়ে কথা পাতিছোঁ।",
    "en": "Hello, I am calling about my order delivery.",
}


def _script_matches(text: str, lang: str) -> bool:
    """True when ``text`` is written in the script ``lang`` uses.

    A recogniser that answers in the wrong script is worse than one that answers
    nothing: the transcript goes straight to the LLM and the TTS voice cannot
    pronounce whatever comes back.
    """
    script = config.detect_script(text)
    if not script:
        return True                      # digits and punctuation only
    return lang in config.SCRIPT_LANGS.get(script, ())


#: Whisper sometimes hallucinates these on silence / noise. Single common words
#: that are also legitimate answers ("एक" = "one") must NOT be listed here: the
#: filter cannot tell a hallucination from a caller answering a numeric question.
_HALLUCINATIONS = {
    "", ".", "।", "you", "thank you.", "thanks for watching!", "bye.", "bye!",
    "[music]", "(music)", "字幕由amara.org社区提供", "字幕",
}


def _clean_transcript(text: str) -> str:
    cleaned = text.strip()
    if cleaned.lower() in _HALLUCINATIONS:
        return ""
    return cleaned


_STT_CACHE: dict[tuple[str, str, str], STTEngine] = {}
_STT_CACHE_LOCK = threading.Lock()


def shared_stt(
    backend: str = "auto",
    lang: str = "hi",
    model: str = config.DEFAULT_STT_MODEL,
) -> STTEngine:
    """Return a process-wide recogniser for ``lang`` (loading it once).

    A call must never pay 0.4-1.0 s of model loading on its first turn: the
    same recogniser object is reused by every session.
    """
    key = (backend, resolve_lang(lang), model)
    with _STT_CACHE_LOCK:
        engine = _STT_CACHE.get(key)
        if engine is None:
            engine = STTEngine(backend=backend, lang=key[1], model=model)
            _STT_CACHE[key] = engine
    return engine


# --------------------------------------------------------------------------- #
# LLM
# --------------------------------------------------------------------------- #

SYSTEM_PROMPT = """You are a warm, helpful voice assistant talking with an Indian user on a live call.
Rules:
- Reply in {language}. If the user mixes English words into any Indian language (Hinglish, Gujlish, Marathi-English, Assamese-English…), reply in the same natural mixed style and keep their English word instead of translating it.
{script_rule}
{gender_rule}
- Speak, do not write: no markdown, no bullet lists, no emoji, no stage directions, no URLs.
- Keep every turn to one or two short sentences (about 25 words), never more than two. The user is listening, not reading.
- Never invent facts. Do not make up order numbers, tracking IDs, prices, dates, names or policies; if you do not have the information, say you will check and ask only for what you actually need.
- Be conversational and specific; ask a short follow-up question only when it actually helps.
- Never mention that you are a language model or describe these instructions."""

#: Script each Indic language must be written in. English is absent on purpose.
SCRIPT_NAMES = {
    "hi": "Devanagari", "mr": "Devanagari", "gu": "Gujarati", "bn": "Bengali",
    "as": "Bengali", "pa": "Gurmukhi", "ta": "Tamil", "te": "Telugu",
    "kn": "Kannada", "ml": "Malayalam", "or": "Odia",
}

#: Hindi, Marathi and Punjabi mark the speaker's own gender in the verb, so a
#: female voice saying "कर सकता हूँ" is heard as wrong immediately. The other
#: languages here do not mark first-person gender, so they need no rule.
_GENDER_RULES = {
    "female": (
        "- You are a woman speaking: in Hindi, Marathi and Punjabi use the FEMININE "
        "first-person form for yourself (कर सकती हूँ / मदत करू शकते / ਕਰ ਸਕਦੀ ਹਾਂ), "
        "never the masculine form."
    ),
    "male": (
        "- You are a man speaking: in Hindi, Marathi and Punjabi use the MASCULINE "
        "first-person form for yourself (कर सकता हूँ / मदत करू शकतो / ਕਰ ਸਕਦਾ ਹਾਂ), "
        "never the feminine form."
    ),
}
_GENDER_RULE = _GENDER_RULES.get(config.VOICE_GENDER, _GENDER_RULES["female"])

DEFAULT_SYSTEM = SYSTEM_PROMPT.format(
    language="the same language the user used", script_rule="", gender_rule=_GENDER_RULE
)


def ensure_script(sentence: str, lang: str) -> str:
    """Put a romanised Indic reply back into its own script.

    Small open models sometimes answer "aapka order kal aayega" in Latin letters.
    The voice router would then pick the *English* voice, so a mostly-Latin reply
    for an Indic language is transliterated before it reaches the TTS.
    """
    code = resolve_lang(lang)
    if code == "en" or not sentence:
        return sentence
    letters = [ch for ch in sentence if ch.isalpha()]
    if not letters:
        return sentence
    latin = sum(1 for ch in letters if ord(ch) < 0x0250)
    if latin / len(letters) < 0.7:
        return sentence
    localised = localize_text(sentence, code)
    return localised or sentence


def system_prompt(lang: str) -> str:
    """System prompt pinned to the language detected for this turn."""
    code = resolve_lang(lang)
    name = LANG_NAMES.get(code, "the same language the user used")
    script = SCRIPT_NAMES.get(code)
    # English turns get no script rule: listing Devanagari and friends there
    # made the small models answer an English caller in Hindi.
    rule = (
        f"- Write in {script} script, never romanise the words "
        "(only genuinely English words stay in Latin letters)."
        if script
        else ""
    )
    return SYSTEM_PROMPT.format(language=f"{name} (stay in this language)",
                                script_rule=rule, gender_rule=_GENDER_RULE)

#: Bare hostnames people usually paste, mapped to the real OpenAI-compatible base.
_KNOWN_API_BASES = {
    "https://groq.com": "https://api.groq.com/openai/v1",
    "https://api.groq.com": "https://api.groq.com/openai/v1",
    "https://openrouter.ai": "https://openrouter.ai/api/v1",
    "https://api.openrouter.ai": "https://openrouter.ai/api/v1",
    "https://api.openai.com": "https://api.openai.com/v1",
    "https://generativelanguage.googleapis.com": "https://generativelanguage.googleapis.com/v1beta/openai",
    "https://api.together.xyz": "https://api.together.xyz/v1",
    "https://api.deepinfra.com": "https://api.deepinfra.com/v1/openai",
}


def normalize_api_base(base: str) -> str:
    """Fix provider hostnames that lack their ``/v1`` style path."""
    cleaned = (base or "").strip().rstrip("/")
    if cleaned in _KNOWN_API_BASES:
        return _KNOWN_API_BASES[cleaned]
    parsed = urllib.parse.urlparse(cleaned)
    if parsed.scheme and parsed.path in ("", "/"):
        print(
            f"[llm] '{cleaned}' has no API path - chat requests would 404. Most providers "
            "need one, e.g. https://api.groq.com/openai/v1 or https://openrouter.ai/api/v1.",
            file=sys.stderr,
        )
    return cleaned


class LLMClient:
    """Streaming chat against Ollama (local) or any OpenAI-compatible API."""

    def __init__(
        self,
        backend: str | None = None,
        model: str | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.6,
        timeout: float = 120.0,
    ):
        chosen = (backend or os.environ.get("INDICVOICE_LLM_BACKEND") or "").lower()
        if not chosen:
            # prefer a configured cloud key, otherwise the local Ollama daemon
            chosen = "groq" if os.environ.get("GROQ_API_KEY") else "ollama"
        self.backend = chosen
        self.temperature = temperature
        self.timeout = timeout
        self._conns: dict[tuple[str, str], http.client.HTTPConnection] = {}
        self._conn_lock = threading.Lock()
        self.reasoning_effort = (
            config.LLM_REASONING_EFFORT if self.backend == "groq" else None
        )

        if self.backend == "ollama":
            base = api_base or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434"
            if not base.startswith("http"):
                base = "http://" + base
            self.api_base = base.rstrip("/")
            self.model = model or os.environ.get("INDICVOICE_LLM_MODEL") or "llama3.2:3b"
            self.api_key = None
        elif self.backend == "groq":
            # Groq is OpenAI-compatible; the key lives in .env as GROQ_API_KEY
            self.api_base = normalize_api_base(
                api_base or os.environ.get("GROQ_BASE_URL")
                or "https://api.groq.com/openai/v1"
            )
            self.model = model or config.LLM_PRIMARY_MODEL
            self.fallback_models = [
                m for m in config.LLM_FALLBACK_MODELS if m != self.model
            ]
            self.api_key = api_key or os.environ.get("GROQ_API_KEY")
            if not self.api_key:
                raise RuntimeError(
                    "GROQ_API_KEY is not set. Put it in .env as GROQ_API_KEY=... "
                    "(copy .env.example to .env) or pass --api-key."
                )
        elif self.backend in {"openai", "openai-compatible", "api"}:
            self.backend = "openai"
            self.api_base = normalize_api_base(
                api_base or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
            )
            self.model = model or os.environ.get("INDICVOICE_LLM_MODEL") or "gpt-4o-mini"
            self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
            if not self.api_key:
                raise RuntimeError("OPENAI_API_KEY is not set (export it or pass --api-key).")
        else:
            raise ValueError("LLM backend must be 'ollama' or 'openai'")

    # -- internals ---------------------------------------------------------- #

    def _connection(self) -> tuple[http.client.HTTPConnection, urllib.parse.ParseResult]:
        """One reusable socket per host: a TLS handshake costs 300+ ms per turn."""
        parsed = urllib.parse.urlparse(self.api_base)
        key = (parsed.scheme, parsed.netloc)
        with self._conn_lock:
            conn = self._conns.get(key)
            if conn is None:
                factory = (
                    http.client.HTTPSConnection
                    if parsed.scheme == "https"
                    else http.client.HTTPConnection
                )
                conn = factory(parsed.netloc, timeout=self.timeout)
                self._conns[key] = conn
            return conn, parsed

    def _drop(self, conn: http.client.HTTPConnection) -> None:
        with self._conn_lock:
            for key, value in list(self._conns.items()):
                if value is conn:
                    del self._conns[key]
        try:
            conn.close()
        except Exception:
            pass

    def _post(self, path: str, payload: dict) -> http.client.HTTPResponse:
        body = json.dumps(payload).encode("utf-8")
        # A real User-Agent matters: Cloudflare fronts Groq and rejects the
        # default "Python-urllib/x.y" agent with HTTP 403 / error 1010.
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "IndicVoice/1.0 (+https://localhost)",
            "Accept": "text/event-stream",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        last: Exception | None = None
        for attempt in (0, 1):
            conn, parsed = self._connection()
            try:
                conn.request(
                    "POST", f"{parsed.path}{path}", body=body, headers=headers
                )
                response = conn.getresponse()
            except (http.client.HTTPException, OSError) as exc:
                last = exc
                self._drop(conn)          # stale keep-alive socket: retry once
                if attempt == 0:
                    continue
                break
            self._active_conn = conn
            if response.status >= 400:
                detail = response.read().decode("utf-8", "replace")[:300]
                self._drop(conn)
                raise RuntimeError(f"{self.backend} HTTP {response.status}: {detail}")
            return response

        hint = (
            "Is Ollama running? Start it with `ollama serve` and `ollama pull llama3.2:3b`."
            if self.backend == "ollama"
            else f"Check OPENAI_BASE_URL ({self.api_base}) and your network."
        )
        raise RuntimeError(
            f"Cannot reach {self.backend} at {self.api_base}: {last}. {hint}"
        )

    def warm(self) -> None:
        """Open the socket now so turn one skips the TLS handshake (~300 ms)."""
        try:
            conn, parsed = self._connection()
            if parsed.scheme == "https":
                conn.connect()
        except Exception:
            pass

    def abort_active(self) -> None:
        """Close every pooled socket so a stuck SSE drain cannot block the next turn.

        Used when a cancelled worker outlives its join deadline: its
        ``response.read()`` drain raises instead of holding the connection that
        the next turn is about to reuse (http.client is not thread-safe).
        """
        with self._conn_lock:
            conns = list(self._conns.values())
            self._conns.clear()
        for conn in conns:
            try:
                conn.close()
            except Exception:
                pass

    def _stream_lines(self, response: http.client.HTTPResponse) -> Iterator[str]:
        """Decode SSE lines and drain the body so the socket can be reused."""
        conn = getattr(self, "_active_conn", None)
        try:
            for raw in response:
                yield raw.decode("utf-8", "replace")
        finally:
            try:
                response.read()
            except Exception:
                if conn is not None:
                    self._drop(conn)

    # -- public API --------------------------------------------------------- #

    def stream_chat(self, messages: list[dict]) -> Iterator[str]:
        """Yield reply text deltas as the model produces them."""
        if self.backend == "ollama":
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": True,
                "options": {"temperature": self.temperature},
            }
            response = self._post("/api/chat", payload)
            for line in self._stream_lines(response):
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                if event.get("error"):
                    raise RuntimeError(f"ollama: {event['error']}")
                chunk = (event.get("message") or {}).get("content") or ""
                if chunk:
                    yield chunk
                if event.get("done"):
                    return
        else:
            last_error: RuntimeError | None = None
            for model in [self.model, *getattr(self, "fallback_models", [])]:
                try:
                    yield from self._stream_openai(messages, model)
                    return
                except RuntimeError as exc:
                    # free tiers throttle: retry the next model instead of going silent
                    if "429" not in str(exc) and "503" not in str(exc):
                        raise
                    last_error = exc
            raise last_error if last_error else RuntimeError("no model available")

    def _stream_openai(self, messages: list[dict], model: str) -> Iterator[str]:
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": self.temperature,
        }
        if self.reasoning_effort and model.startswith("openai/"):
            payload["reasoning_effort"] = self.reasoning_effort
        response = self._post("/chat/completions", payload)
        for line in self._stream_lines(response):
            line = line.strip()
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                return
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue
            choices = event.get("choices") or []
            if not choices:
                continue
            delta = (choices[0].get("delta") or {}).get("content")
            if delta:
                yield delta

    def reply(self, messages: list[dict]) -> str:
        """Non-streaming convenience wrapper."""
        return "".join(self.stream_chat(messages)).strip()


# --------------------------------------------------------------------------- #
# Voice agent
# --------------------------------------------------------------------------- #


@dataclass
class AgentConfig:
    lang: str = "hi"
    stt_lang: str = "hi"
    stt_backend: str = "auto"
    stt_model: str = config.DEFAULT_STT_MODEL
    tts_langs: tuple[str, ...] = tuple(config.LANG_NAMES)
    auto_lang: bool = True          # switch language per turn from the transcript script
    backchannel: bool = True        # play "हाँ जी..." if the LLM is slow to start
    backchannel_delay: float = 0.35   # fills the gap while a slow ASR finishes
    humanize: bool = True           # clause pauses, speed jitter, room tone, crossfade
    speed: float = 1.0
    vad_threshold: float = 0.5
    min_silence: float = config.ENDPOINT_SILENCE
    min_speech: float = 0.25
    barge_in: bool = True
    barge_in_seconds: float = 0.45
    input_device: int | str | None = None
    output_device: int | str | None = None
    llm_backend: str | None = None      # None = auto (groq if GROQ_API_KEY, else ollama)
    llm_model: str | None = None
    api_base: str | None = None
    history_turns: int = 6
    system_prompt: str = DEFAULT_SYSTEM


class VoiceAgent:
    """Duplex loop: listen, transcribe, think, speak — interruptible at any point."""

    def __init__(
        self,
        cfg: AgentConfig | None = None,
        llm: LLMClient | None = None,
        player=None,
    ):
        self.cfg = cfg or AgentConfig()
        self.cfg.lang = resolve_lang(self.cfg.lang)
        self.cfg.stt_lang = resolve_lang(self.cfg.stt_lang)
        # ``player`` lets a server inject a WebSocket sink instead of the speaker
        self.player = player or AudioPlayer(target_rate=SAMPLE_RATE, device=self.cfg.output_device)
        self.tts = TTSPool(
            langs=self.cfg.tts_langs,
            default_lang=self.cfg.lang,
            player=self.player,
            humanize=self.cfg.humanize,
        )
        self.current_lang = self.cfg.stt_lang
        self._stt: dict[str, STTEngine] = {}
        self.stt = self._recognizer(self.current_lang)
        self.llm = llm or LLMClient(
            backend=self.cfg.llm_backend,
            model=self.cfg.llm_model,
            api_base=self.cfg.api_base,
        )
        self.history: list[dict] = [{"role": "system", "content": self.cfg.system_prompt}]
        self.cancel = threading.Event()
        #: per-turn timestamps so the server can attribute the latency budget
        self.marks: dict[str, float] = {}
        self._turn_marks: dict[str, float] = self.marks
        self._worker: threading.Thread | None = None
        self._vad = None

    # -- VAD ---------------------------------------------------------------- #

    def _build_vad(self):
        import sherpa_onnx

        vad_config = sherpa_onnx.VadModelConfig(
            silero_vad=sherpa_onnx.SileroVadModelConfig(
                model=str(config.VAD_PATH),
                threshold=self.cfg.vad_threshold,
                min_silence_duration=self.cfg.min_silence,
                min_speech_duration=self.cfg.min_speech,
                window_size=VAD_WINDOW,
            ),
            sample_rate=SAMPLE_RATE,
            num_threads=1,
            provider="cpu",
        )
        return sherpa_onnx.VoiceActivityDetector(vad_config, buffer_size_in_seconds=30)

    # -- language routing --------------------------------------------------- #

    def _recognizer(self, lang: str) -> STTEngine:
        """Lazily create (and cache) a recogniser for ``lang``."""
        code = resolve_lang(lang)
        if not config.has_indic_asr(code) and code != "en":
            code = self.cfg.stt_lang
        if code not in self._stt:
            self._stt[code] = shared_stt(
                backend=self.cfg.stt_backend, lang=code, model=self.cfg.stt_model
            )
        return self._stt[code]

    def maybe_switch_language(self, transcript: str) -> str:
        """Detect the turn's language from its script and swap the recogniser.

        Returns the language that should be used for the reply.
        """
        if not self.cfg.auto_lang:
            return self.current_lang
        detected = detect_lang(transcript, self.current_lang)
        if detected == self.current_lang:
            return self.current_lang
        # A Latin-script utterance is weak evidence: "ok", "hello" or a short
        # Hinglish fragment used to flip a Hindi call to English for the rest of
        # the session. Require a few words before changing language; an Indic
        # script is unambiguous, so one word is enough there.
        if config.detect_script(transcript) == "latin":
            words = [w for w in transcript.split() if any(ch.isalpha() for ch in w)]
            if len(words) < _LATIN_SWITCH_MIN_WORDS:
                return self.current_lang
        if config.has_indic_asr(detected) or detected == "en":
            self.current_lang = detected
            self.stt = self._recognizer(detected)   # applies from the next turn
            print(f"  [lang] now speaking {LANG_NAMES.get(detected, detected)}")
        return self.current_lang

    def _maybe_backchannel(self, lang: str) -> None:
        """Play an instant "हाँ जी..." if the LLM is slow to produce audio."""
        if not self.cfg.backchannel or not self.cfg.humanize:
            return

        def _run() -> None:
            time.sleep(self.cfg.backchannel_delay)
            if not self.cancel.is_set() and not self.player.is_speaking:
                if self.tts.backchannel(lang):
                    print("  [backchannel]")

        threading.Thread(target=_run, name="backchannel", daemon=True).start()

    # -- one conversational turn -------------------------------------------- #

    def respond(self, user_text: str, on_sentence=None, reply_lang: str | None = None) -> str:
        """Stream an LLM reply into the speaker sentence by sentence."""
        self.cancel.clear()
        # a barge-in muted the sink; this turn may speak again. Without this the
        # reply after an interruption would be silent for the rest of the call.
        resume = getattr(self.player, "resume", None)
        if resume is not None:
            resume()
        # replace (not clear in place) so a late latency event from the previous
        # turn that captured this dict object still reads its own values
        self.marks = {}
        self._turn_marks = self.marks
        self.marks["start"] = time.perf_counter()
        lang = resolve_lang(reply_lang) if reply_lang else detect_lang(user_text, self.cfg.lang)
        self.history[0] = {"role": "system", "content": system_prompt(lang)}
        self.history.append({"role": "user", "content": user_text})
        messages = self.history[-(2 * self.cfg.history_turns + 1):]

        splitter = SentenceSplitter(lang=lang)
        collected: list[str] = []

        def sentences() -> Iterator[str]:
            produced = 0
            self.marks.setdefault("llm_request", time.perf_counter())
            for delta in self.llm.stream_chat(messages):
                if "llm_first" not in self.marks:
                    self.marks["llm_first"] = time.perf_counter()
                if self.cancel.is_set():
                    return
                for sentence in splitter.feed(delta):
                    produced += 1
                    if produced > config.MAX_REPLY_SENTENCES:
                        return
                    sentence = ensure_script(sentence, lang)
                    self.marks.setdefault("tts_start", time.perf_counter())
                    collected.append(sentence)
                    if on_sentence:
                        on_sentence(sentence)
                    yield sentence
            for sentence in splitter.flush():
                sentence = ensure_script(sentence, lang)
                collected.append(sentence)
                if on_sentence:
                    on_sentence(sentence)
                yield sentence

        self._maybe_backchannel(lang)
        self.tts.speak_sentences(
            sentences(), preferred_lang=lang, speed=self.cfg.speed, cancel_event=self.cancel
        )
        reply = " ".join(collected).strip()
        if reply:
            self.history.append({"role": "assistant", "content": reply})
            del self.history[1:max(1, len(self.history) - 2 * self.cfg.history_turns)]
        return reply

    def start_response(self, user_text: str, reply_lang: str | None = None, on_sentence=None) -> None:
        """Run :meth:`respond` on a worker thread so listening never blocks."""
        if self._worker is not None and self._worker.is_alive():
            self.cancel.set()
            self.player.cancel()
            self._worker.join(timeout=2.0)
            if self._worker.is_alive():
                # still draining a cancelled SSE stream: free the socket so the
                # new turn does not share it with the old worker thread
                self.llm.abort_active()

        def _run() -> None:
            try:
                self.respond(user_text, on_sentence=on_sentence, reply_lang=reply_lang)
            except Exception as exc:  # keep the conversation alive on LLM errors
                print(f"[llm error] {exc}", file=sys.stderr)

        self._worker = threading.Thread(target=_run, name="llm-tts", daemon=True)
        self._worker.start()

    # -- live loop ---------------------------------------------------------- #

    def run(self) -> None:
        print(
            f"Listening ({LANG_NAMES[self.cfg.stt_lang]} STT, {self.cfg.llm.backend}:{self.cfg.llm.model}, "
            f"auto-language={'on' if self.cfg.auto_lang else 'off'}, "
            f"voices={','.join(self.tts.langs)}). Ctrl+C to stop."
        )
        vad = self._build_vad()
        audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=64)

        def _callback(indata, frames, time_info, status) -> None:  # noqa: ANN001
            if status:
                pass
            chunk = indata[:, 0].copy()
            try:
                audio_queue.put_nowait(chunk)
            except queue.Full:
                try:
                    audio_queue.get_nowait()  # drop stale audio to keep latency low
                except queue.Empty:
                    pass

        speech_frames = 0
        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=VAD_WINDOW,
            device=self.cfg.input_device,
            callback=_callback,
        )
        stream.start()
        try:
            while True:
                try:
                    chunk = audio_queue.get(timeout=0.2)
                except queue.Empty:
                    continue

                # barge-in: sustained user speech while we are talking
                if self.cfg.barge_in and self.player.is_speaking and vad.is_speech_detected():
                    speech_frames += 1
                else:
                    speech_frames = 0
                if self.cfg.barge_in and speech_frames * VAD_WINDOW_SECONDS >= self.cfg.barge_in_seconds:
                    print("  [barge-in] interrupted")
                    self.cancel.set()
                    self.player.cancel()
                    speech_frames = 0

                vad.accept_waveform(chunk)
                while not vad.empty():
                    segment = vad.front
                    # copy BEFORE pop(): a popped segment has its samples moved out
                    samples = np.asarray(segment.samples, dtype=np.float32).copy()
                    vad.pop()
                    if samples.size < int(0.3 * SAMPLE_RATE):
                        continue
                    t0 = time.perf_counter()
                    text = _clean_transcript(self.stt.transcribe(samples))
                    if not text:
                        continue
                    print(f"\nyou ({time.perf_counter() - t0:.2f}s stt): {text}")
                    reply_lang = self.maybe_switch_language(text)
                    self.start_response(text, reply_lang=reply_lang)
        finally:
            stream.stop()
            stream.close()
            self.cancel.set()
            if self._worker is not None:
                self._worker.join(timeout=3.0)
            self.player.close()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Real-time Indian speech-to-speech voice agent (CPU)")
    parser.add_argument(
        "--lang", default="hi",
        help=f"default conversation language: {', '.join(config.LANG_NAMES)}",
    )
    parser.add_argument("--stt-lang", default=None, help="ASR language (defaults to --lang)")
    parser.add_argument(
        "--stt-backend",
        default="auto",
        choices=["auto", "indic", "whisper", "transducer"],
        help="auto = IndicConformer for Hindi/Gujarati, Whisper otherwise",
    )
    parser.add_argument("--stt-model", default=config.DEFAULT_STT_MODEL, choices=["tiny", "base"])
    parser.add_argument(
        "--langs",
        nargs="*",
        default=None,
        help="voices to load, e.g. --langs hi gu ta (default: every downloaded voice)",
    )
    parser.add_argument("--no-auto-lang", action="store_true",
                        help="keep one language for the whole session")
    parser.add_argument("--no-backchannel", action="store_true",
                        help="do not play 'हाँ जी...' while the model is thinking")
    parser.add_argument("--no-humanize", action="store_true",
                        help="disable clause pauses, speed jitter, room tone and crossfade")
    parser.add_argument("--speed", type=float, default=1.0, help="TTS speed (1.0 = natural)")
    parser.add_argument("--vad-threshold", type=float, default=0.5)
    parser.add_argument("--llm-backend", default=None, choices=["ollama", "groq", "openai"],
                        help="default: groq when GROQ_API_KEY is set, otherwise ollama")
    parser.add_argument("--llm-model", default=None,
                        help="e.g. llama-3.3-70b-versatile (groq), llama3.2:3b (ollama), gpt-4o-mini")
    parser.add_argument("--api-base", default=None,
                        help="Ollama host or OpenAI-compatible base URL")
    parser.add_argument("--api-key", default=None,
                        help="API key (or set GROQ_API_KEY / OPENAI_API_KEY in .env)")
    parser.add_argument("--input-device", default=None, help="microphone index or name")
    parser.add_argument("--output-device", default=None, help="speaker index or name")
    parser.add_argument("--no-barge-in", action="store_true", help="disable interruption while speaking")
    parser.add_argument("--say", default=None, help="TTS-only smoke test, no microphone")
    parser.add_argument("--utterance", default=None, help="one offline turn: text -> LLM -> speech (no mic)")
    parser.add_argument("--list-devices", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.list_devices:
        print(sd.query_devices())
        return 0

    missing = config_missing(args.stt_backend, args.stt_lang or args.lang, args.stt_model)
    if missing:
        print("Missing model files:", *missing, sep="\n  - ")
        print("\nRun:  python -m src.download_models --all")
        return 1

    if args.say:
        pool = TTSPool(default_lang=args.lang, humanize=not args.no_humanize)
        started = time.perf_counter()
        audio = pool.synthesize_stream(args.say, lang=args.lang, speed=args.speed)
        pool.player.wait_until_done()
        # voices differ in rate (16 kHz MMS, 44.1 kHz Supertonic), so report
        # against the rate the audio was actually rendered at
        rate = pool.engine(args.lang).sample_rate
        print(
            f"Spoke {len(audio) / rate:.2f}s of audio in {time.perf_counter() - started:.2f}s "
            f"-> {config.AUDIO_OUT_DIR / 'output.wav'}"
        )
        pool.close()
        return 0

    cfg = AgentConfig(
        lang=args.lang,
        stt_lang=args.stt_lang or args.lang,
        stt_backend=args.stt_backend,
        stt_model=args.stt_model,
        tts_langs=tuple(resolve_lang(l) for l in args.langs) if args.langs else tuple(config.LANG_NAMES),
        auto_lang=not args.no_auto_lang,
        backchannel=not args.no_backchannel,
        humanize=not args.no_humanize,
        speed=args.speed,
        vad_threshold=args.vad_threshold,
        barge_in=not args.no_barge_in,
        input_device=args.input_device,
        output_device=args.output_device,
        llm_backend=args.llm_backend,
        llm_model=args.llm_model,
        api_base=args.api_base,
    )
    llm = LLMClient(
        backend=cfg.llm_backend,
        model=cfg.llm_model,
        api_base=cfg.api_base,
        api_key=args.api_key,
    )

    if args.utterance:
        agent = VoiceAgent(cfg, llm=llm)
        try:
            reply = agent.respond(args.utterance)
        except RuntimeError as exc:
            print(f"\n[error] {exc}", file=sys.stderr)
            return 1
        print(f"\nreply: {reply}")
        agent.player.close()
        return 0

    agent = VoiceAgent(cfg, llm=llm)
    try:
        agent.run()
    except KeyboardInterrupt:
        print("\nbye")
    return 0


def config_missing(
    stt_backend: str = "auto",
    stt_lang: str = "hi",
    stt_model: str = config.DEFAULT_STT_MODEL,
) -> list[str]:
    """Human readable list of absent model artefacts."""
    gaps = []
    if not config.VAD_PATH.exists():
        gaps.append(f"VAD: {config.VAD_PATH}")

    stt_lang = resolve_lang(stt_lang)
    resolved = STTEngine._resolve_backend(stt_backend, stt_lang)
    if resolved == "indic":
        if not config.indic_asr_model(stt_lang).exists():
            gaps.append(
                f"ASR {stt_lang}: {config.indic_asr_dir(stt_lang)}  "
                f"(python -m src.download_models --indic-asr {stt_lang})"
            )
    elif resolved == "whisper":
        if not config.stt_file(stt_model, "encoder").exists():
            gaps.append(
                f"STT {stt_model}: {config.stt_model_dir(stt_model)}  "
                f"(python -m src.download_models --stt {stt_model})"
            )
    elif not config.TRANSDUCER_DIR.exists():
        gaps.append(f"STT transducer: {config.TRANSDUCER_DIR}")

    tts_dir = config.tts_model_dir("hi")
    if not (tts_dir / "model.onnx").exists():
        gaps.append(f"TTS hi: {tts_dir}  (python -m src.download_models --tts hi)")
    return gaps


if __name__ == "__main__":
    sys.exit(main())
