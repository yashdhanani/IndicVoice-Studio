"""Shared paths, language tables and model locations.

Twelve Indian languages are wired up: 11 Indic scripts plus Indian English.
Everything resolves relative to the project root so the engine behaves the same
from a module, an IDE or a notebook.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
def _load_dotenv(path: Path) -> None:
    """Read ``KEY=VALUE`` lines from ``.env`` without overriding real env vars.

    Keeps the Groq/OpenAI key out of the shell and out of git; the file is
    git-ignored and never read by anything but this loader.
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(PROJECT_ROOT / ".env")

MODELS_DIR = Path(os.environ.get("INDICVOICE_MODELS_DIR", PROJECT_ROOT / "models"))
AUDIO_OUT_DIR = Path(os.environ.get("INDICVOICE_AUDIO_DIR", PROJECT_ROOT / "audio_out"))

#: Everything acoustic in this project runs at 16 kHz mono.
SAMPLE_RATE = 16000

#: Telephony audio is 8 kHz mu-law.
TELEPHONY_RATE = 8000

#: Silence (seconds) that ends a user turn. Below ~0.2 s a natural pause inside
#: one sentence is mistaken for "finished speaking" and the agent answers half a
#: question; 0.26 s keeps most utterances whole while staying responsive.
#: Override per call with ?endpoint=0.3 or --endpoint.
ENDPOINT_SILENCE = 0.26
#: English callers pause longer, and the English voice leaves ~0.5 s between
#: sentences, so 0.45 s truncated two-sentence turns (measured: half the turn was
#: lost at 0.45, fully captured at 0.7).
ENDPOINT_SILENCE_BY_LANG = {"en": 0.45}


def endpoint_for(lang: str) -> float:
    """End-of-turn silence to use for ``lang``."""
    return ENDPOINT_SILENCE_BY_LANG.get(resolve_lang(lang), ENDPOINT_SILENCE)

#: Supported language codes -> human readable names.
LANG_NAMES = {
    "hi": "Hindi",
    "gu": "Gujarati",
    "mr": "Marathi",
    "bn": "Bengali",
    "ta": "Tamil",
    "te": "Telugu",
    "kn": "Kannada",
    "ml": "Malayalam",
    "pa": "Punjabi",
    "or": "Odia",
    "as": "Assamese",
    "en": "Indian English",
}

#: Short code -> the MMS (ISO-639-3) folder inside the converted model repo.
MMS_CODES = {
    "hi": "hin", "gu": "guj", "mr": "mar", "bn": "ben", "ta": "tam",
    "te": "tel", "kn": "kan", "ml": "mal", "pa": "pan", "or": "ory",
    "as": "asm", "en": "eng",
}

#: MMS-TTS checkpoints already converted to sherpa-onnx (model.onnx + tokens.txt).
TTS_REPO = "willwade/mms-tts-multilingual-models-onnx"
TTS_MODELS = {
    lang: {"repo": TTS_REPO, "subfolder": mms, "dir": f"tts-{lang}"}
    for lang, mms in MMS_CODES.items()
}

#: Supertonic 3 (Supertone, MIT): one 139 MB INT8 model covering 31 languages
#: with 10 speakers at 44.1 kHz. Much more natural than MMS and it reads mixed
#: Hindi/English text ("आपका order confirm है") natively, so Hindi and Indian
#: English prefer it whenever it is downloaded.
SUPERTONIC_DIR = MODELS_DIR / "sherpa-onnx-supertonic-3-tts-int8-2026-05-11"
SUPERTONIC_LANGS = ("hi", "en")
#: Flow-matching steps. Measured on this i7: 8 -> RTF 0.62, 6 -> 0.47,
#: 4 -> 0.38, 2 -> 0.21. ASR round-trip stays intact at 6 and degrades at 4,
#: so 6 is the quality/latency sweet spot for a live call.
SUPERTONIC_STEPS = 6
SUPERTONIC_FILES = (
    "tts.json",
    "voice.bin",
    "unicode_indexer.bin",
    "duration_predictor.int8.onnx",
    "text_encoder.int8.onnx",
    "vector_estimator.int8.onnx",
    "vocoder.int8.onnx",
)


def supertonic_available() -> bool:
    return all((SUPERTONIC_DIR / name).exists() for name in SUPERTONIC_FILES)


#: Indic Tiny TTS (AI4Bharat Rasa voices, Matcha + Vocos, CC-BY-4.0): 22.5 M
#: parameters, 24 kHz, one model per language for all 11 Indic languages plus
#: Indian English. Measured here at RTF 0.09-0.15 with a clean ASR round trip,
#: and its published CER (~3%) is far below MMS (~9-12%). It runs on
#: onnxruntime, which has no Python 3.15 wheel, so it needs the project's
#: Python 3.13 venv (``.venv313``); elsewhere the backend is skipped.
TINY_DIRS = {code: MODELS_DIR / f"tiny-{code}" for code in LANG_NAMES}
TINY_REPOS = {
    "hi": "sulabhkatiyar/indic-tiny-tts-hindi",
    "gu": "sulabhkatiyar/indic-tiny-tts-gujarati",
    "mr": "sulabhkatiyar/indic-tiny-tts-marathi",
    "bn": "sulabhkatiyar/indic-tiny-tts-bengali",
    "ta": "sulabhkatiyar/indic-tiny-tts-tamil",
    "te": "sulabhkatiyar/indic-tiny-tts-telugu",
    "kn": "sulabhkatiyar/indic-tiny-tts-kannada",
    "ml": "sulabhkatiyar/indic-tiny-tts-malayalam",
    "pa": "sulabhkatiyar/indic-tiny-tts-punjabi",
    "or": "sulabhkatiyar/indic-tiny-tts-odia",
    "as": "sulabhkatiyar/indic-tiny-tts-assamese",
    "en": "sulabhkatiyar/indic-tiny-tts-english",
}
#: The tiny voices are calm readers: 1.15 matches a natural phone pace, and
#: their output arrives ~8 dB quieter than MMS, so it is levelled on the way out.
TINY_SPEED = 1.15
TINY_TARGET_RMS = 0.07


def _onnxruntime_ready() -> bool:
    try:
        import onnxruntime  # noqa: F401
    except Exception:                                     # noqa: BLE001 - optional
        return False
    return True


_ORT_READY = _onnxruntime_ready()


def tiny_available(lang: str) -> bool:
    """True when the tiny model for ``lang`` is downloaded and loadable."""
    if not _ORT_READY:
        return False
    directory = TINY_DIRS.get(resolve_lang(lang))
    return bool(directory) and (directory / "onnx" / "text_encoder.onnx").exists()


def tts_backend(lang: str) -> str:
    """Best engine available for ``lang``: tiny, then supertonic, then mms."""
    code = resolve_lang(lang)
    if tiny_available(code):
        return "tiny"
    if code in SUPERTONIC_LANGS and supertonic_available():
        return "supertonic"
    return "mms"


#: Script ranges used for automatic per-turn language detection.
SCRIPT_RANGES = {
    "devanagari": (0x0900, 0x097F),
    "bengali": (0x0980, 0x09FF),
    "gurmukhi": (0x0A00, 0x0A7F),
    "gujarati": (0x0A80, 0x0AFF),
    "oriya": (0x0B00, 0x0B7F),
    "tamil": (0x0B80, 0x0BFF),
    "telugu": (0x0C00, 0x0C7F),
    "kannada": (0x0C80, 0x0CFF),
    "malayalam": (0x0D00, 0x0D7F),
    "latin": (0x0041, 0x024F),
}

#: Script -> candidate languages (order matters for the default pick).
SCRIPT_LANGS = {
    "devanagari": ("hi", "mr"),
    "bengali": ("bn", "as"),
    "gurmukhi": ("pa",),
    "gujarati": ("gu",),
    "oriya": ("or",),
    "tamil": ("ta",),
    "telugu": ("te",),
    "kannada": ("kn",),
    "malayalam": ("ml",),
    "latin": ("en",),
}

#: Silero VAD (sherpa-onnx build).
VAD_REPO = "csukuangfj/vad"
VAD_FILE = "silero_vad.onnx"
VAD_PATH = MODELS_DIR / VAD_FILE

#: Whisper INT8 checkpoints (used for Indian English and as a fallback).
STT_MODELS = {
    "tiny": {"repo": "csukuangfj/sherpa-onnx-whisper-tiny", "prefix": "tiny", "dir": "whisper-tiny"},
    "base": {"repo": "csukuangfj/sherpa-onnx-whisper-base", "prefix": "base", "dir": "whisper-base"},
}
DEFAULT_STT_MODEL = "base"

#: AI4Bharat IndicConformer (NeMo CTC, INT8) per language, converted for
#: sherpa-onnx. These exports ship without the NeMo metadata keys sherpa reads,
#: so ``patch_metadata`` is applied at download time (vocab_size is counted from
#: the token file itself).
_OVOS = "OpenVoiceOS/ai4bharat-indicconformer-{}-onnx"
_INDIC_ASR_LANGS = ("gu", "mr", "bn", "ta", "te", "kn", "ml", "pa", "or", "as")
INDIC_ASR = {
    # verified end-to-end on real speech; already carries correct metadata
    "hi": {
        "repo": "meetsync/indic-conformer-onnx-sherpa",
        "dir": "asr-hi",
        "files": {"model": "model.int8.onnx", "tokens": "tokens.txt"},
    },
}
INDIC_ASR.update({
    lang: {
        "repo": _OVOS.format(lang),
        "dir": f"asr-{lang}",
        "files": {"model": "model.int8.onnx", "tokens": "vocab.txt"},
        "patch_metadata": {
            "vocab_size": "auto",
            "subsampling_factor": "4",
            "normalize_type": "per_feature",
            "model_type": "EncDecCTCModelBPE",
        },
    }
    for lang in _INDIC_ASR_LANGS
})
# Gujarati was verified with this exact repo; keep its directory naming stable.
INDIC_ASR["gu"]["dir"] = "asr-gu"
#: No Assamese ONNX export has been published (the OpenVoiceOS repo holds only a
#: README), so Assamese audio is decoded with the Bengali Conformer: same script,
#: closely related language. Expect Bengali orthography in the transcript.
INDIC_ASR["as"] = dict(INDIC_ASR["bn"], alias_of="bn")

#: Streaming Zipformer fallback (optional; download separately).
TRANSDUCER_DIR = MODELS_DIR / "zipformer-streaming"

#: Hard cap on reply length so a runaway LLM cannot hold the speaker forever.
#: Hard cap on spoken sentences per turn; the system prompt asks for two, and a
#: phone reply that runs longer than this sounds like a lecture.
MAX_REPLY_SENTENCES = 2

#: Cloud ASR (Groq-hosted Whisper). Odia is not supported by Whisper, so it
#: always stays on the local IndicConformer model.
GROQ_STT_MODEL = os.environ.get("INDICVOICE_GROQ_STT_MODEL", "whisper-large-v3-turbo")
GROQ_STT_LANGS = frozenset({"hi", "gu", "mr", "bn", "ta", "te", "kn", "ml", "pa", "as", "en"})

#: Languages sent to cloud Whisper in "fast" mode instead of the local model.
#: Measured with the fixed eval corpus (``python -m src.evaluate --backend``):
#: the local Conformer wins on accuracy everywhere, so nothing is cloud-routed
#: for speed any more. ta CER 0.00 vs 0.10, kn 0.01 vs 0.10, te 0.03 vs 0.31 for
#: 200-400 ms more per turn (ta 661 ms, kn 834 ms, te 694 ms of decode).
#: Re-add codes here to trade accuracy back for latency.
STT_FAST_LANGS: frozenset[str] = frozenset()

#: Languages that recognise better/faster in the cloud than on this CPU.
#: Everything else stays local, because the IndicConformer models are more
#: accurate than Whisper on these languages (ml, as and or collapse there).
STT_BACKEND_BY_LANG = {"en": "groq"}

#: "fast" (default) lets slow languages use cloud ASR; "accurate" keeps them local.
STT_MODE = os.environ.get("INDICVOICE_STT_MODE", "fast").lower()

#: When set, /ws/voice and /ws/telephony require ?token=<value>. Empty = open
#: on localhost only; binding beyond localhost without a token refuses startup.
ACCESS_TOKEN = os.environ.get("INDICVOICE_TOKEN", "")

#: Extra browser origins allowed on the WebSocket endpoints (comma-separated,
#: e.g. "https://calls.example.com"). Localhost origins are always allowed;
#: clients without an Origin header (telephony gateways, scripts) are not affected.
ALLOWED_ORIGINS = tuple(
    o.strip().lower() for o in os.environ.get("INDICVOICE_ALLOWED_ORIGINS", "").split(",")
    if o.strip()
)

#: A call with no audio in either direction for this long is closed (4408).
SESSION_IDLE_SECONDS = float(os.environ.get("INDICVOICE_IDLE_TIMEOUT", "180"))

#: Abuse caps (Hardening V1 B5). Utterances longer than MAX_UTTERANCE_SECONDS
#: are truncated (with a warning event); calls older than MAX_SESSION_SECONDS
#: are closed (4410); a client that stops draining audio is dropped once the
#: outbound queue holds MAX_OUTBOUND_QUEUE items.
MAX_UTTERANCE_SECONDS = float(os.environ.get("INDICVOICE_MAX_UTTERANCE", "60"))
MAX_SESSION_SECONDS = float(os.environ.get("INDICVOICE_MAX_SESSION", "1800"))
MAX_OUTBOUND_QUEUE = int(os.environ.get("INDICVOICE_MAX_QUEUE", "4096"))

#: Lifetime of a one-time ?ticket= issued by POST /auth/ticket (B2).
TICKET_TTL_SECONDS = float(os.environ.get("INDICVOICE_TICKET_TTL", "60"))

#: gpt-oss spends most of its first-token time "thinking". "low" halves latency
#: (715 ms -> 362 ms measured) and keeps the short replies just as good.
LLM_REASONING_EFFORT = os.environ.get("INDICVOICE_REASONING_EFFORT", "low")

#: qwen/qwen3.8-27b is ~200 ms quicker but its free tier caps at 1000 output
#: tokens/min, and a 429 stalled a test turn for 30 s - unusable on a live call,
#: so gpt-oss-20b stays the default. Override with INDICVOICE_LLM_MODEL if you
#: are on a paid tier.
LLM_PRIMARY_MODEL = os.environ.get("INDICVOICE_LLM_MODEL", "openai/gpt-oss-20b")
LLM_FALLBACK_MODELS: tuple[str, ...] = ()

#: IndicConformer decoding threads. V3 Phase B live matrix on the reference
#: i7-8565U (4 physical cores): STT=4/TTS=2 gave the best tail latency and
#: loop health at 1-5 sessions; STT=8 oversubscribes, STT=2 decoded slower
#: live despite winning the isolated microbench. Override with
#: INDICVOICE_STT_THREADS (exact pre-V3 rollback: 8).
STT_NUM_THREADS = int(os.environ.get(
    "INDICVOICE_STT_THREADS", str(max(2, min(4, os.cpu_count() or 4)))))

#: Indic Tiny TTS onnxruntime intra-op threads. V3 Phase B measured best: 2.
#: 0 = onnxruntime default (all cores, the pre-V3 behaviour; rollback value).
#: Override with INDICVOICE_TTS_THREADS.
TTS_NUM_THREADS = int(os.environ.get("INDICVOICE_TTS_THREADS", "2"))

#: Dedicated ASR decode pool size, separate from the default executor so
#: outbound-audio work can never queue behind a decode (V3 Phase B).
ASR_WORKERS = int(os.environ.get("INDICVOICE_ASR_WORKERS", "2"))

#: Optional wav2vec2-CTC ONNX export (see colab/assamese_asr_export.ipynb).
#: When present it is used for Assamese instead of the Bengali Conformer.
ASR_CTC_DIR = MODELS_DIR / "asr-as-ctc"


def asr_ctc_available() -> bool:
    """True when a CTC export has been dropped into ``models/asr-as-ctc``."""
    return (ASR_CTC_DIR / "model.onnx").exists()

_LANG_ALIASES = {
    "hi": "hi", "hin": "hi", "hindi": "hi",
    "gu": "gu", "guj": "gu", "gujarati": "gu",
    "mr": "mr", "mar": "mr", "marathi": "mr",
    "bn": "bn", "ben": "bn", "bengali": "bn", "bangla": "bn",
    "ta": "ta", "tam": "ta", "tamil": "ta",
    "te": "te", "tel": "te", "telugu": "te",
    "kn": "kn", "kan": "kn", "kannada": "kn",
    "ml": "ml", "mal": "ml", "malayalam": "ml",
    "pa": "pa", "pan": "pa", "punjabi": "pa",
    "or": "or", "ory": "or", "odia": "or", "oriya": "or",
    "as": "as", "asm": "as", "assamese": "as",
    "en": "en", "eng": "en", "english": "en",
    "hinglish": "en", "gujlish": "en", "tanglish": "en", "benglish": "en",
}


def tts_model_dir(lang: str) -> Path:
    """Directory holding ``model.onnx`` / ``tokens.txt`` for ``lang``."""
    return MODELS_DIR / TTS_MODELS[resolve_lang(lang)]["dir"]


def stt_model_dir(model: str = DEFAULT_STT_MODEL) -> Path:
    return MODELS_DIR / STT_MODELS[model]["dir"]


def stt_file(model: str, part: str) -> Path:
    prefix = STT_MODELS[model]["prefix"]
    name = {
        "encoder": f"{prefix}-encoder.int8.onnx",
        "decoder": f"{prefix}-decoder.int8.onnx",
        "tokens": f"{prefix}-tokens.txt",
    }[part]
    return stt_model_dir(model) / name


def indic_asr_dir(lang: str = "hi") -> Path:
    return MODELS_DIR / INDIC_ASR[resolve_lang(lang)]["dir"]


def indic_asr_model(lang: str = "hi") -> Path:
    spec = INDIC_ASR[resolve_lang(lang)]
    return indic_asr_dir(lang) / spec["files"]["model"]


def indic_asr_tokens(lang: str = "hi") -> Path:
    spec = INDIC_ASR[resolve_lang(lang)]
    return indic_asr_dir(lang) / spec["files"]["tokens"]


def has_indic_asr(lang: str) -> bool:
    try:
        return resolve_lang(lang) in INDIC_ASR
    except ValueError:
        return False


def resolve_lang(value: str) -> str:
    """Accept ``hi``, ``hin``, ``hindi`` ... and return the short code."""
    key = (value or "").strip().lower()
    if key not in _LANG_ALIASES:
        raise ValueError(f"Unsupported language {value!r}; use one of {sorted(LANG_NAMES)}")
    return _LANG_ALIASES[key]


def detect_script(text: str) -> str:
    """Return the dominant Indic/Latin script name of ``text`` ('' when unsure)."""
    counts: dict[str, int] = {}
    for ch in text:
        code = ord(ch)
        for name, (lo, hi) in SCRIPT_RANGES.items():
            if lo <= code <= hi:
                counts[name] = counts.get(name, 0) + 1
                break
    if not counts:
        return ""
    return max(counts.items(), key=lambda kv: kv[1])[0]


def detect_lang(text: str, default: str = "hi") -> str:
    """Guess ``text``'s language from its script, preferring ``default`` on ties.

    Devanagari is shared by Hindi and Marathi, and Bengali by Bengali and
    Assamese, so the session default wins when it is a candidate.
    """
    try:
        default = resolve_lang(default)
    except ValueError:
        default = "hi"
    script = detect_script(text)
    if not script:
        return default
    candidates = SCRIPT_LANGS.get(script, (default,))
    if default in candidates:
        return default
    return candidates[0]
