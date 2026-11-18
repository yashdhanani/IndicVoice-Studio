# Model Inventory (local, as of 2026-11-18)

Total: ~4.3 GB under `models/`. 40 top-level entries.

## ASR (IndicConformer, sherpa-onnx INT8)

- `asr-hi` (meetsync/indic-conformer-onnx-sherpa, verified export, correct metadata)
- `asr-gu` (OpenVoiceOS export, patch_metadata)
- `asr-mr`, `asr-bn`, `asr-ta`, `asr-te`, `asr-kn`, `asr-ml`, `asr-pa`, `asr-or`, `asr-as` (OpenVoiceOS exports)
- `asr-as` falls back to `asr-bn` if absent; native `asr-as` export now present (parismitaglobalsolutions).
- Optional: `whisper-tiny`, `whisper-base` (sherpa INT8), `zipformer-streaming` (optional, TRANSDUCER_DIR), `asr-as-ctc` (optional CTC).

## TTS

- `tiny-{hi,gu,mr,bn,ta,te,kn,ml,pa,or,as,en}` (Indic Tiny TTS, Matcha+Vocos, onnxruntime, 24 kHz).
- `tts-{hi,...,en}` (MMS-TTS, sherpa, 16 kHz) — fallback for all 12.
- `sherpa-onnx-supertonic-3-tts-int8-2026-05-11` (Supertonic 3, 44.1 kHz, hi+en only).

## VAD

- `silero_vad.onnx` (Silero, sherpa-onnx).

## Not present (would need download, authorization, disk check)

- Nemotron Speech Streaming (GGUF) — not downloaded.
- IndicF5, Indic-Speak, Indic Parler-TTS — not downloaded.
- Whisper.cpp / Faster-Whisper — not installed (whisper sherpa INT8 used instead).
- Piper voices — not downloaded.

## Notes

- `_ORT_READY` (onnxruntime importable) gates tiny TTS availability.
- `tts_backend(lang)` selects tiny → supertonic → mms.
- `supertonic_available()` checks all SUPERTONIC_FILES.
- Disk free: ~98 GB. RAM: ~15.9 GB. No massive downloads performed.