# ASR Comparison (research + local evidence)

See `research_review.md` §A. Published claims separated from our measurements.

## Candidate summary table

| Candidate | Type | Streaming | Indic langs | Windows CPU | License | Our measured? |
|---|---|---|---|---|---|---|
| IndicConformer (sherpa exports) | local ONNX | unverified per export | 22 | yes (sherpa) | MIT | partial (local, 12 langs) |
| Whisper.cpp (quantized) | local GGML | rolling window | multilingual | yes | MIT | no (not installed) |
| Faster-Whisper (INT8) | local CTranslate2 | segment-yielding | multilingual | yes | MIT | no |
| Nemotron (NeMo-Speech.cpp) | local GGUF | native streaming | 40 locales (incl hi) | yes | OpenMDW-1.1 + Apache-2.0 | no (not installed) |
| Sarvam Saaras v4 | hosted API | WebSocket partials | 22 + English | n/a (client) | proprietary | no (no key authorized) |
| Deepgram Nova-3 | hosted API | streaming | bn,gu,hi,kn,mr,ta,te | n/a | proprietary | no |
| AWS Transcribe | hosted API | streaming | feature-specific | n/a | proprietary | no |
| Azure Speech | hosted API | streaming | many; en-Latn-IN limited | n/a | proprietary | no |

## Our existing ASR measurements (synthetic, stage bench + prior A/B)

- Round-trip CER (synthetic): hi 0.000, gu 0.000, mr 0.037, bn 0.000, ta 0.000, en 0.216 (2 repeats, this run).
- ASR decode p50: hi 192.8, gu 1876.8, mr 1913.4, bn 1319.5, ta 1221.7, en 592.5 ms.
- Synthetic-corpus CER (n=3/lang, prior): hi 0.047, gu 0.025, mr 0.000, bn 0.044, ta 0.000, te 0.000, kn 0.012, ml 0.029, pa 0.042, or 0.088, as 0.268, en 0.141.
- Streaming vs block parity: 12/12 languages (synthetic, prior).
- E2E: only hi + en measured (p50 1.13/1.26 s).

## Key gaps

- No real human speech WER/CER (0/240 recordings).
- No Nemotron/Whisper.cpp/Faster-Whisper/Sarvam measured locally.
- Assamese weak (0.268 synthetic CER, Bengali alias).
- English ASR (Groq Whisper) CER 0.141 driven by one clip.

## Recommendation (evidence-limited)

- Keep current IndicConformer local + Groq Whisper for en as the baseline.
- Investigate Nemotron (NeMo-Speech.cpp) on Windows CPU for English/Hindi streaming with a measured Hindi benchmark before any switch.
- Do not replace IndicConformer for the 10 Indic languages without measured evidence (per project rules).