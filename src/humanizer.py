"""Human-realism layer for CPU TTS.

Three things give synthetic speech away on a call: perfectly flat rhythm,
audible joins between streamed sentences, and dead air while a reply is being
generated. This module addresses each:

* :meth:`Humanizer.clauses` splits a sentence at commas and gives every clause
  its own pause (120-250 ms) and a small speed jitter (0.94-1.05).
* :class:`SeamBlender` overlap-adds consecutive audio chunks so joins are
  inaudible, and :meth:`Humanizer.with_room_tone` adds a -55 dB noise floor so
  the line never sounds digitally silent.
* :meth:`Humanizer.filler` returns a short, language-matched acknowledgment
  ("हाँ जी...", "એક મિનિટ...") that can be played instantly while the LLM is
  still thinking.

Everything here is plain numpy: no GPU, no audio files to ship. Filler clips are
synthesised once by the local TTS and cached in memory.
"""

from __future__ import annotations

import random
import re
from typing import Callable

import numpy as np

from .config import SAMPLE_RATE

#: Short acknowledgment clips per language (played before a slow LLM replies).
FILLERS = {
    "hi": ("जी, हाँ...", "अच्छा, एक मिनिट..."),
    "gu": ("હા જી...", "એક મિનિટ..."),
    "mr": ("हो, बरं...", "एक मिनिट..."),
    "bn": ("হ্যাঁ, আচ্ছা...", "এক মিনিট..."),
    "ta": ("ஆமா...", "ஒரு நிமிஷம்..."),
    "te": ("అవును...", "ఒక నిమిషం..."),
    "kn": ("ಹೌದು...", "ಒಂದು ನಿಮಿಷ..."),
    "ml": ("അതെ...", "ഒരു മിനിറ്റ്..."),
    "pa": ("ਹਾਂ ਜੀ...", "ਇੱਕ ਮਿੰਟ..."),
    "or": ("ହଁ...", "ଏକ ମିନିଟ୍..."),
    "as": ("হয়...", "এক মিনিট..."),
    "en": ("Sure, one moment...", "Right..."),
}

_CLAUSE_SPLIT = re.compile(r"(?<=[,;:])\s+|(?<=।)\s+")


class Humanizer:
    """Prosody shaping, pauses, comfort noise and filler clips."""

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        enabled: bool = True,
        seed: int = 7,
        speed_jitter: tuple[float, float] = (0.97, 1.03),
        clause_pause_ms: tuple[int, int] = (120, 250),
        sentence_pause_ms: int = 220,
        comfort_noise_db: float = -55.0,
        crossfade_ms: float = 15.0,
        filler_factory: Callable[[str, str], np.ndarray] | None = None,
    ):
        self.sample_rate = sample_rate
        self.enabled = enabled
        self._seed = seed
        self._rng = random.Random(seed)
        self._noise_rng = np.random.default_rng(seed)
        self.speed_jitter = speed_jitter
        self.clause_pause_ms = clause_pause_ms
        self.sentence_pause_ms = sentence_pause_ms
        self.comfort_noise_db = comfort_noise_db
        self.crossfade_ms = crossfade_ms
        self._filler_factory = filler_factory
        self._fillers: dict[tuple[str, str], np.ndarray] = {}

    def at_sample_rate(self, sample_rate: int) -> "Humanizer":
        """Same configuration for a voice with a different sample rate.

        Pause and room-tone lengths are sample counts, so a 44.1 kHz voice must
        not borrow the 16 kHz instance (its pauses would be 2.7x too short).
        """
        if sample_rate == self.sample_rate:
            return self
        return Humanizer(
            sample_rate=sample_rate,
            enabled=self.enabled,
            seed=self._seed,
            speed_jitter=self.speed_jitter,
            clause_pause_ms=self.clause_pause_ms,
            sentence_pause_ms=self.sentence_pause_ms,
            comfort_noise_db=self.comfort_noise_db,
            crossfade_ms=self.crossfade_ms,
            filler_factory=self._filler_factory,
        )

    # -- prosody ------------------------------------------------------------ #

    def speed_for(self, index: int) -> float:
        """Small deterministic rate variation so sentences never sound looped."""
        if not self.enabled:
            return 1.0
        low, high = self.speed_jitter
        return round(self._rng.uniform(low, high), 3)

    def clause_pause(self, final: bool = False) -> float:
        """Pause after a clause (seconds)."""
        if not self.enabled:
            return 0.02
        if final:
            return self.sentence_pause_ms / 1000.0
        low, high = self.clause_pause_ms
        return self._rng.uniform(low, high) / 1000.0

    def clauses(self, text: str) -> list[tuple[str, float]]:
        """Split ``text`` at commas/semicolons; return ``(clause, pause_seconds)``."""
        text = (text or "").strip()
        if not text:
            return []
        if not self.enabled:
            return [(text, 0.0)]
        parts = [part.strip() for part in _CLAUSE_SPLIT.split(text) if part and part.strip()]
        merged: list[str] = []
        for part in parts:
            if merged and len(part) < 12:
                merged[-1] = f"{merged[-1]} {part}"
            else:
                merged.append(part)
        if len(merged) > 1 and len(merged[0]) < 12:
            merged[0:2] = [f"{merged[0]} {merged[1]}"]
        out = []
        for i, clause in enumerate(merged):
            out.append((clause, self.clause_pause(final=(i == len(merged) - 1))))
        return out

    # -- audio shaping ------------------------------------------------------ #

    def room_tone(self, n_samples: int) -> np.ndarray:
        """Low-level noise floor (-55 dBFS by default)."""
        if not self.enabled or n_samples <= 0:
            return np.zeros(0, dtype=np.float32)
        amplitude = 10 ** (self.comfort_noise_db / 20.0)
        noise = self._noise_rng.standard_normal(n_samples).astype(np.float32)
        return (noise * amplitude * 0.3).astype(np.float32)

    def with_room_tone(self, audio: np.ndarray) -> np.ndarray:
        """Mix a barely-audible noise floor into ``audio``."""
        if not self.enabled or audio is None or len(audio) == 0:
            return np.asarray(audio if audio is not None else [], dtype=np.float32)
        audio = np.asarray(audio, dtype=np.float32)
        noise = self.room_tone(len(audio))
        return np.clip(audio + noise, -1.0, 1.0)

    def silence(self, seconds: float) -> np.ndarray:
        n = max(0, int(seconds * self.sample_rate))
        return np.zeros(n, dtype=np.float32)

    # -- backchannels ------------------------------------------------------- #

    def register_filler(self, lang: str, audio: np.ndarray, text: str = "") -> None:
        if audio is not None and len(audio):
            self._fillers[(lang, text)] = np.asarray(audio, dtype=np.float32)

    def filler(self, lang: str) -> np.ndarray | None:
        """Return a cached acknowledgment clip for ``lang`` (synthesising on first use)."""
        phrases = FILLERS.get(lang, FILLERS["en"])
        for phrase in phrases:
            cached = self._fillers.get((lang, phrase))
            if cached is not None:
                return cached
            if self._filler_factory is not None:
                try:
                    audio = self._filler_factory(lang, phrase)
                except Exception:
                    audio = None
                if audio is not None and len(audio):
                    self.register_filler(lang, audio, phrase)
                    return np.asarray(audio, dtype=np.float32)
        return None


class SeamBlender:
    """Overlap-add chunk boundary smoothing for streamed sentences.

    ``push()`` holds back the last ``overlap`` samples so the next chunk can be
    crossfaded into them; ``flush()`` releases whatever is still held.
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE, overlap_ms: float = 15.0):
        self.sample_rate = sample_rate
        self.overlap = max(1, int(sample_rate * overlap_ms / 1000.0))
        self._tail: np.ndarray | None = None
        self._buf = np.zeros(0, dtype=np.float32)

    def push(self, chunk: np.ndarray) -> np.ndarray:
        """Feed a chunk, return the audio that is ready to play."""
        chunk = np.asarray(chunk, dtype=np.float32)
        if chunk.size == 0:
            return np.zeros(0, dtype=np.float32)
        self._buf = np.concatenate([self._buf, chunk]) if self._buf.size else chunk

        if self._tail is not None and self._buf.size >= self.overlap:
            fade = np.linspace(0.0, 1.0, self.overlap, dtype=np.float32)
            blended = self._tail * (1.0 - fade) + self._buf[: self.overlap] * fade
            self._buf = np.concatenate([blended, self._buf[self.overlap:]])
            self._tail = None

        if self._buf.size <= self.overlap:
            return np.zeros(0, dtype=np.float32)

        self._tail = self._buf[-self.overlap:].copy()
        ready = self._buf[: -self.overlap]
        self._buf = np.zeros(0, dtype=np.float32)
        return ready

    def flush(self) -> np.ndarray:
        parts = [p for p in (self._buf, self._tail) if p is not None and p.size]
        self._buf = np.zeros(0, dtype=np.float32)
        self._tail = None
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
