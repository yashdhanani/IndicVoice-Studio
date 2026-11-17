"""Pseudo-streaming ASR on top of the offline IndicConformer / Whisper engines.

True streaming Zipformers do not exist for most Indic languages, so instead the
offline recogniser is run repeatedly on the growing audio buffer *while the user
is still speaking*, producing live partial transcripts. At end-of-speech the
final transcript always comes from one authoritative full-buffer decode — the
same decode the block path does — so accuracy is identical by construction.
The latency win comes from starting that decode speculatively during the
endpoint silence window (~0.12 s after speech offset), so fast languages finish
before the endpoint fires and perceive ~0 ms ASR latency.

Partials are gated on the predicted decode cost at the current buffer length:
a model that needs >400 ms per decode cannot keep up with real time, so its
partials would be stale and would hold the engine lock exactly when the
speculative decode wants it (measured: ungated partials doubled perceived
latency on mr/kn/ta). Partials never feed the final transcript; measured A/B
runs showed that merging partial and tail hypotheses corrupts words
(kn CER 0.01 -> 0.32). A speculative result is discarded at finalize if audio
beyond the expected trailing silence arrived after its snapshot (quiet speech
resuming below the RMS gate), and after one mid-utterance pause the next
speculation waits for near-endpoint silence so a wasted decode cannot queue
ahead of the authoritative one.

Usage::

    streamer = StreamingSTT(on_partial=print)
    streamer.start(engine, seed=preroll_audio)   # VAD detected speech onset
    streamer.accept(chunk)                       # every incoming frame
    text, info = streamer.finalize()             # VAD endpoint fired
"""
from __future__ import annotations

import threading
import time

import numpy as np

from .config import ENDPOINT_SILENCE, SAMPLE_RATE


class StreamingSTT:
    """One utterance at a time; call :meth:`start` again for the next turn."""

    def __init__(
        self,
        on_partial=None,
        partial_interval: float = 0.35,
        partial_max_decode: float = 0.4,
        min_buffer: float = 0.5,
        speculate_after: float = 0.12,
        endpoint_silence: float = ENDPOINT_SILENCE,
        sample_rate: int = SAMPLE_RATE,
    ):
        self.on_partial = on_partial
        self.partial_interval = partial_interval
        self.partial_max_decode = partial_max_decode
        self.min_buffer = min_buffer
        self.speculate_after = speculate_after
        self.endpoint_silence = endpoint_silence
        self.rate = sample_rate

        self._cond = threading.Condition()
        self._stop = threading.Event()
        self._engine = None
        self._buf = np.zeros(0, dtype=np.float32)
        self._generation = 0
        self._active = False
        self._decoding = False
        self._decoded_upto = 0
        self._partial_text = ""
        self._partials = 0
        #: authoritative decode started during trailing silence, before endpoint
        self._spec_text: str | None = None
        self._spec_covered = 0
        self._spec_requested = False
        self._silent_run = 0
        self._peak = 0.0
        #: cost of the last decode on this engine; gates partial scheduling
        self._decode_ms = 0.0
        self._decode_audio_s = 0.0
        #: speculative decodes invalidated by speech resuming this turn
        self._spec_misses = 0
        self._worker = threading.Thread(target=self._loop, name="stream-stt", daemon=True)
        self._worker.start()

    # -- utterance lifecycle -------------------------------------------------- #

    def start(self, engine, seed: np.ndarray | None = None,
              endpoint_silence: float | None = None) -> None:
        """Begin an utterance. ``seed`` is pre-onset audio (ring buffer)."""
        with self._cond:
            if engine is not self._engine:
                self._decode_ms = 0.0
                self._decode_audio_s = 0.0
            if endpoint_silence is not None:
                self.endpoint_silence = endpoint_silence
            self._engine = engine
            self._generation += 1
            self._active = True
            self._buf = (
                np.asarray(seed, dtype=np.float32).reshape(-1).copy()
                if seed is not None else np.zeros(0, dtype=np.float32)
            )
            self._decoded_upto = 0
            self._partial_text = ""
            self._partials = 0
            self._spec_text = None
            self._spec_covered = 0
            self._spec_requested = False
            self._spec_misses = 0
            self._silent_run = 0
            self._peak = 0.0
            self._cond.notify_all()

    def accept(self, samples: np.ndarray) -> None:
        """Append incoming audio; cheap enough to call on the event loop."""
        chunk = np.asarray(samples, dtype=np.float32).reshape(-1)
        if chunk.size == 0:
            return
        with self._cond:
            if not self._active:
                return
            self._buf = np.concatenate([self._buf, chunk])
            rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
            self._peak = max(self._peak, rms)
            if rms > max(self._peak * 0.06, 1e-4):
                self._silent_run = 0
                if self._spec_text is not None or self._spec_requested:
                    # speech resumed after a pause: the speculative decode is
                    # stale, go back to partials until the next trailing silence
                    self._spec_text = None
                    self._spec_requested = False
                    self._spec_misses += 1
            else:
                self._silent_run += chunk.size
            # after a mid-utterance pause proved the silence non-terminal, only
            # speculate once the silence is nearly at the endpoint anyway: a
            # second wasted decode would queue behind the authoritative one
            threshold = self.speculate_after
            if self._spec_misses:
                threshold = max(threshold, self.endpoint_silence - 0.02)
            if (
                self._silent_run >= threshold * self.rate
                and len(self._buf) >= self.min_buffer * self.rate
                and self._spec_text is None
                and not self._spec_requested
                and getattr(self._engine, "backend", "") != "groq"
            ):
                self._spec_requested = True
            self._cond.notify_all()

    def cancel(self) -> None:
        with self._cond:
            self._active = False
            self._generation += 1
            self._buf = np.zeros(0, dtype=np.float32)
            self._spec_text = None
            self._spec_requested = False
            self._cond.notify_all()

    def close(self) -> None:
        self._stop.set()
        with self._cond:
            self._cond.notify_all()

    @property
    def partial(self) -> str:
        with self._cond:
            return self._partial_text

    # -- background partial decodes ------------------------------------------- #

    def _loop(self) -> None:
        while not self._stop.is_set():
            with self._cond:
                while not self._stop.is_set():
                    fresh = len(self._buf) - self._decoded_upto
                    # decode cost grows with buffer length: predict the cost at
                    # the *current* length, not the (shorter) last snapshot's
                    predicted_ms = self._decode_ms * (len(self._buf) / self.rate) / max(
                        self._decode_audio_s, 0.1
                    )
                    ready = self._engine is not None and (
                        self._spec_requested
                        or (
                            self._active
                            and getattr(self._engine, "backend", "") != "groq"
                            and self._spec_text is None
                            and predicted_ms <= self.partial_max_decode * 1000.0
                            and len(self._buf) >= self.min_buffer * self.rate
                            and fresh >= self.partial_interval * self.rate
                        )
                    )
                    if ready:
                        break
                    self._cond.wait(timeout=0.1)
                if self._stop.is_set():
                    return
                snapshot = self._buf.copy()
                generation = self._generation
                engine = self._engine
                speculative = self._spec_requested
                self._decoding = True
                self._decoded_upto = len(snapshot)

            decode_started = time.perf_counter()
            try:
                text = engine.transcribe(snapshot, self.rate)
            except Exception:
                text = ""
            decode_ms = (time.perf_counter() - decode_started) * 1000.0
            with self._cond:
                self._decoding = False
                if generation == self._generation:
                    self._decode_ms = decode_ms
                    self._decode_audio_s = len(snapshot) / self.rate
                    # accept() clears _spec_requested if speech resumed mid-decode
                    if speculative and self._spec_requested:
                        self._spec_text = text
                        self._spec_covered = len(snapshot)
                    if text:
                        changed = text != self._partial_text
                        self._partial_text = text
                        self._partials += 1
                    else:
                        changed = False
                else:
                    changed = False
                self._cond.notify_all()
            if changed and self.on_partial is not None:
                try:
                    self.on_partial(text)
                except Exception:
                    pass

    # -- end of speech ---------------------------------------------------------- #

    def finalize(self) -> tuple[str, dict]:
        """Return the final transcript and timing/strategy info.

        Called at the VAD endpoint; ``finalize_ms`` in the info dict is the
        perceived ASR latency (endpoint -> final transcript). The transcript is
        always a full-buffer decode of the utterance — either the speculative
        one started during trailing silence, or a fresh one — so accuracy
        matches the block path exactly.
        """
        started = time.perf_counter()
        with self._cond:
            self._active = False
            engine = self._engine
            local = engine is not None and getattr(engine, "backend", "") != "groq"
            if local and self._spec_text is None and self._buf.size:
                # no speculative decode yet: ask the worker for the authoritative
                # one now; it may already be queued behind a partial
                self._spec_requested = True
                self._cond.notify_all()
            deadline = time.perf_counter() + 15.0
            while (
                local
                and self._spec_text is None
                and (self._decoding or self._spec_requested)
                and time.perf_counter() < deadline
            ):
                self._cond.wait(timeout=0.05)
            buf = self._buf
            spec_text = self._spec_text
            if spec_text is not None:
                # audio kept arriving after the speculative snapshot. Up to
                # (endpoint - speculate_after) of it is expected trailing
                # silence; more means speech resumed below the RMS gate, so
                # the snapshot is stale and must not become the transcript.
                grew_s = (buf.size - self._spec_covered) / self.rate
                if grew_s > self.endpoint_silence - self.speculate_after + 0.08:
                    spec_text = None
            partials = self._partials
            self._buf = np.zeros(0, dtype=np.float32)
            self._spec_text = None
            self._spec_requested = False

        if engine is None or buf.size == 0:
            text, strategy = "", "empty"
        elif not local:
            text, strategy = engine.transcribe(buf, self.rate), "cloud"
        elif spec_text is not None:
            text, strategy = spec_text, "speculative"
        else:
            text, strategy = engine.transcribe(buf, self.rate), "full"

        info = {
            "finalize_ms": round((time.perf_counter() - started) * 1000.0, 1),
            "strategy": strategy,
            "partials": partials,
            "audio_seconds": round(buf.size / self.rate, 2),
        }
        return text.strip(), info