# TTS Comparison (research + local evidence)

See `research_review.md` §B.

## Candidate summary table

| Candidate | Type | Streaming | Target langs covered | Windows CPU | License | Our measured? |
|---|---|---|---|---|---|---|
| Sarvam Bulbul v4 Flash | hosted API | HTTP stream + WS | 8/12 (no ml, or, as, Kashmiri) | n/a (client) | proprietary | no |
| Sarvam Bulbul v3 | hosted API | HTTP stream + WS | 10/12 (no as, Kashmiri) | n/a | proprietary | no |
| ElevenLabs Flash v2.5 | hosted API | HTTP stream + WS | 2/12 (hi, ta) | n/a | plan-dependent | no |
| ElevenLabs Turbo v2.5 | hosted API | streaming | 2/12 | n/a | plan-dependent | no |
| IndicF5 | local (0.4B F32) | no native streaming | 11/12 | unclear | MIT | no |
| Indic-TTS | local (per-lang) | no | 8/12 | unclear (GPU-oriented) | MIT | no |
| Indic-Speak | local (3.78B BF16) | no native streaming | 12/12 (Kashmiri preview) | unclear | Indic Open Model v1.0 | no |
| Indic Parler-TTS | local (~0.9B) | no | 23 Indian langs | unclear | Apache 2.0 | no |
| Piper via sherpa-onnx | local (per voice) | offline only | Hindi verified; others separate | yes (CPU wheels) | per-voice | no |

## Our existing TTS measurements (this run, synthetic)

- TTS RTF p50: hi 0.08, gu 0.09, mr 0.09, bn 0.09, ta 0.10, en 0.12 (tiny backend).
- TTS ms p50: hi 318.0, gu 496.4, mr 430.0, bn 324.4, ta 335.0, en 502.5.
- All measured clips intelligible to ASR (round-trip CER ≤0.037 except en digit formatting).
- Backends: tiny (24 kHz) primary, supertonic (44.1 kHz, hi/en), MMS (16 kHz) fallback.

## Key gaps

- No human MOS / naturalness study (NOT TESTED).
- No Sarvam/ElevenLabs evaluated (no authorization/keys).
- No local candidate (IndicF5/Indic-Speak/Parler) downloaded or benchmarked.
- Tiny TTS mid-generation cancel not implemented (D10).
- Backend-availability checks MMS-only (D11).

## Recommendation (evidence-limited)

- Keep current tiny/supertonic/MMS stack (measured RTF 0.07–0.12, CPU-stable).
- If human-quality upgrade is authorized and budget allows, evaluate Sarvam Bulbul v3/v4 Flash and ElevenLabs Flash v2.5 on identical text with native listeners before any switch.
- Do not download Indic-Speak (6.6 GB) or IndicF5 without disk/RAM/licensing review and authorization.<|end|><|start|>write_file to=assistant<|channel|>analysis<|message|>{"file":"benchmarks\\results\\cpu_sts_optimization\\tts_comparison.md","message":"Created file successfully."}