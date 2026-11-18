# 05 — ASR Validation

## Providers implemented

- Local IndicConformer (sherpa-onnx, INT8) for hi (verified export) and gu/mr/bn/ta/te/kn/ml/pa/or/as (OpenVoiceOS exports; as falls back to bn).
- Whisper INT8 (sherpa) for `en` fallback.
- Groq-hosted Whisper large-v3-turbo for `en` (config STT_BACKEND_BY_LANG = {"en": "groq"}); GROQ_STT_LANGS includes 11 codes but only `en` is routed to cloud by default.
- Optional streaming Zipformer (`TRANSDUCER_DIR`) if downloaded.
- Optional CTC export for Assamese (`ASR_CTC_DIR`).

## Verification

- Provider registry / backend selection: exercised by tests + config.
- Streaming vs block accuracy parity: reported for all 12 languages (synthetic corpus, counterbalanced re-runs) — see docs/INDICVOICE_TECHNICAL_AUDIT.md §3.
- Error survival: D1 fixed (ASR exception no longer kills the call) + regression test in tests/test_ws_server.
- Speculative decode staleness guard + post-miss suppression: tested (tests/test_streaming_stt).

## Measured (synthetic, this run)

- Round-trip CER: hi 0.000, gu 0.000, mr 0.037, bn 0.000, ta 0.000, en 0.216.
- ASR decode p50: hi 192.8 ms, gu 1876.8 ms, mr 1913.4 ms, bn 1319.5 ms, ta 1221.7 ms, en 592.5 ms (Groq).
- en CER 0.216 driven by digit formatting ("one two three"→"123"), not word errors.

## Not tested

- Real human speech WER/CER (0/240 recordings).
- Noise/reverb/μ-law robustness on real audio (synthetic noise matrix exists for hi/gu/kn only, relative degradation).
- Multi-speaker, accents, speeds, code-switching on real speech.
- Physical microphone path.

## Conclusion

ASR engineering pipeline is sound and tested on synthetic audio. Real-world accuracy claims are NOT supported. Assamese remains a known weak point (0.268 synthetic CER on Bengali alias).