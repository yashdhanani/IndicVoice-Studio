# Research Review — CPU-Efficient Multilingual STS (IndicVoice)

Date: 2026-11-18 · Sources: web research (official docs, model cards, papers, repos) + local code inspection. Published claims separated from measured results.

## A. Streaming ASR candidates

See `asr_comparison.md` for full table. Summary:

- **NVIDIA Nemotron Speech Streaming via NeMo-Speech.cpp**: best-documented local streaming CPU candidate. 0.6B model, Q8_0, 160 ms chunks → 27.0 ms avg compute (i7-11700K, 8 threads). Windows CPU builds supported. Original checkpoint English-only; newer Nemotron 3.5 ASR Streaming covers 40 locales incl. Hindi, but CPU benchmark is English. No Hindi CER/WER on cited CPU setup. License: OpenMDW-1.1 model, Apache-2.0 runtime.
- **AI4Bharat IndicConformer**: 600M multilingual + 30M real-time model (separate checkpoints). 22 Indian languages. No first-party sherpa-onnx streaming release verified; community INT8 ONNX exports exist but are not equivalent to upstream streaming support. MIT license. Independent benchmark (Sthānika): 22.02% pooled WER on IndicVoices (not vendor claim).
- **Whisper.cpp (quantized)**: practical offline CPU. tiny 273 MB, base 388 MB, small 852 MB, large-v3 Q5_0 1.1 GiB, turbo Q5_0 547 MiB. Rolling-window example (0.5 s steps) — not native streaming. MIT. Windows MSVC/MinGW.
- **Faster-Whisper (INT8)**: small model 1,477 MB / 1m42s for 13 min (i7-12700K, 8 threads). Segment-yielding, not first-party live streaming. MIT (model weights separately attributed).
- **Sarvam Saaras v4**: hosted API, 3B decoder, 22 Indian langs + English, `codemix` mode, <150 ms TTFT claimed. No local model/RAM/CPU. No per-language WER table extractable.
- **Deepgram streaming**: hosted, Nova-3 multilingual includes bn/gu/hi/kn/mr/ta/te; multilingual code-switching via `language=multi`. Streaming latency typically ≤300 ms (server-side). Proprietary.
- **AWS Transcribe streaming**: hosted, feature/language-specific coverage; Hindi & Bengali streaming; Gujarati marked with limitations. Partial-result stabilization. Proprietary.
- **Azure Speech streaming**: hosted; `en-Latn-IN` multilingual route limited to en/hi/bn/kn/mr/ta/te and returns romanized text. Embedded Speech is separate/restricted.

Conclusion: For local CPU streaming, Nemotron (NeMo-Speech.cpp) is the best-documented candidate but Hindi accuracy must be measured locally. IndicConformer is the Indic-specialized option but streaming support must be verified per export. Whisper.cpp/Faster-Whisper are practical offline fallbacks. Cloud options (Sarvam/Deepgram) offer code-mix and Indic coverage but add network dependency and cost.

## B. Streaming TTS candidates

See `tts_comparison.md`. Summary:

- **Sarvam Bulbul v4 Flash**: managed, 8/12 target langs (no ml, or), HTTP stream + WebSocket, native-script required. No numeric first-audio latency/RTF. Proprietary API.
- **Sarvam Bulbul v3**: 10/12 target langs (no as, Kashmiri), code-mixing documented. Proprietary.
- **ElevenLabs Flash v2.5**: ~100 ms median server-side latency (excludes network), streaming, Hindi+Tamil of 12. Commercial license plan-dependent.
- **ElevenLabs Turbo v2.5**: ~250–300 ms model latency, higher quality. Same coverage.
- **AI4Bharat IndicF5**: 0.4B F32 (~1.6 GB), 11/12 (no Kashmiri), reference-prompted synthesis, MIT. No streaming endpoint/first-audio measured. Windows support unclear.
- **AI4Bharat Indic-TTS**: older FastPitch+HiFi-GAN per language, ICASSP 2023, MOS evidence at project level, GPU-oriented, 8/12 target langs. MIT.
- **Indic-Speak (Bodhan AI × AI4Bharat)**: 3.78B BF16 (6.6 GB), 12/12 target langs (Kashmiri preview), code-mixing focus, ~200 ms claimed (unverified), automated NORESQA MOS 4.46 (not human). Indic Open Model License v1.0 (restrictive).
- **Indic Parler-TTS**: ~0.9B, 23 Indian langs, expressive, Apache 2.0. No streaming/first-audio measured.
- **Piper via sherpa-onnx**: lightweight local Hindi; CPU-only Windows wheels; voice licenses vary. Not a unified 12-lang engine.

Conclusion: No single TTS covers all 12 languages well locally. Sarvam/ElevenLabs (hosted) offer streaming and Indic coverage but cost/latency/network. Local options (Piper, IndicF5, Indic-Speak) lack streaming verification or are heavy. Current project already uses tiny/supertonic/MMS locally (RTF 0.07–0.12 measured).

## C. CPU inference optimization

See `cpu_profile.md`. Summary:

- ONNX Runtime CPU EP: graph optimization `ORT_ENABLE_ALL`; sweep intra-op threads 1/2/3/4, keep inter-op sequential for single stream. Dynamic INT8 (higher accuracy, adds cost) vs static INT8 (calibration needed, faster). INT4 limited to MatMul/Gather weight-only. OpenVINO: LATENCY hint for interactive, THROUGHPUT for multi-request; INT8 needs calibration. sherpa-onnx: C/C++ runtime, streaming + non-streaming ASR, thread-count setting; INT8 encoder/joiner recommended, INT8 decoder not. Warm-up sessions; reuse sessions; bounded queues with backpressure. i7-8565U: 4 cores/8 threads, AVX2, no VNNI → don't assume INT8 speedup. Starting point: 1–2 threads for single stream.

## D. Architecture recommendation

- Keep **hybrid (Architecture A)** as primary: local VAD + preprocessing, streaming cloud/local ASR where measured advantage, local or hosted TTS per language, LLM via Groq (existing). This matches the current design.
- Fully local (B) is a fallback/low-connectivity mode; not forced given CPU constraints.
- Adaptive (C) only if per-language routing proves useful; implement as a configurable registry, not mid-conversation switching.

## E. What is NOT verified

- No model download/install performed in this pass (no authorization, no massive downloads).
- No new benchmarks run beyond existing baselines.
- No human MOS collected.
- No paid API calls triggered.
- Published claims (Sarvam/Deepgram/Azure latency, model sizes) are vendor claims, not our measurements.