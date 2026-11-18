# 02 — Actual Architecture

## Classification

IndicVoice is a **modular cascaded Speech-to-Speech system**: separate ASR → LLM → TTS stages orchestrated over WebSockets. It is **not** a native end-to-end speech-to-speech model and not a hybrid native model. No jointly trained STS foundation model is involved.

## Stage map (file → class/function)

| Stage | File | Symbol |
|---|---|---|
| Audio capture / framing | `src/call_server.py` | `CallSession.feed`, `sender()` |
| VAD | `src/call_server.py` | Silero VAD via sherpa-onnx (`build_vad` in bench) |
| Endpointing | `src/call_server.py` / `config.endpoint_for` | `ENDPOINT_SILENCE`, `ENDPOINT_SILENCE_BY_LANG` |
| Streaming ASR | `src/streaming_stt.py` | `StreamingSTT` (speculative + authoritative) |
| Language ID | `src/sts_pipeline.py` | `maybe_switch_language`, `config.detect_lang/detect_script` |
| Transcript cleanup | `src/sts_pipeline.py` | `_clean_transcript` |
| Conversation / LLM | `src/sts_pipeline.py` | `VoiceAgent.start_response`, `LLMClient.stream_chat` |
| Text normalization | `src/text_normalizer.py`, `src/translit.py`, `src/humanizer.py` | normalize / localize / humanize |
| TTS | `src/tts_engine.py` | `TTSEngine`, `TTSPool`, `AudioPlayer`, `AudioSink` |
| Audio encoding | `src/call_server.py` | `resample`, PCM16/μ-law |
| Playback | browser `web/app.js` / phone gateway | client-side |
| Interruption | `src/call_server.py`, `src/tts_engine.py` | barge-in 0.45 s sustained VAD, cancel_event |
| Fallback | `src/call_server.py` | `--no-streaming` kill switch, block mode |

## Network dependencies

- LLM: Groq (openai/gpt-oss-20b) — required for response generation.
- ASR: local IndicConformer (11 langs) + Groq Whisper for `en` (configurable via STT_BACKEND_BY_LANG).
- TTS: fully local (tiny/supertonic/MMS).
- VAD: fully local (Silero).

## Audio formats

- Internal: 16 kHz mono float32/PCM16.
- Telephony: 8 kHz μ-law.
- TTS backends: tiny 24 kHz, supertonic 44.1 kHz, MMS 16 kHz; resampled to 16 kHz on output.

## Threading model

- ASR decode pool: dedicated executor, size `ASR_WORKERS` (default 2).
- TTS: worker threads per sentence via `TTSPool`.
- Outbound audio: event-driven sender (V3 Phase B); bounded queue `MAX_OUTBOUND_QUEUE` (4096).
- LLM SSE: keep-alive socket, reasoning effort low.

## Honest statement

No claim of native STS is made. The system is a cascaded pipeline; latency floor is dominated by endpoint silence + LLM TTFT + TTS TTFB. See `08_latency_analysis.md`.