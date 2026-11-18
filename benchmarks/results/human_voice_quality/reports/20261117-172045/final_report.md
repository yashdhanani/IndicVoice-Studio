# IndicVoice human voice-quality — final report (20261117-172045)

Status vocabulary: PASS (automated) / PASS — manually verified / PARTIAL / FAIL / NOT TESTED / NOT APPLICABLE.

## 1. Overall language quality matrix

| lang | round-trip | clean/n | CER clean mean | human naturalness | production readiness |
|---|---|---|---|---|---|
| hi | NOT TESTED | None/None | None | NOT TESTED | NOT TESTED — no human evidence |
| gu | NOT TESTED | None/None | None | NOT TESTED | NOT TESTED — no human evidence |
| mr | PASS (automated) | 1/1 | 0.0 | NOT TESTED | NOT TESTED — no human evidence |
| bn | NOT TESTED | None/None | None | NOT TESTED | NOT TESTED — no human evidence |
| ta | NOT TESTED | None/None | None | NOT TESTED | NOT TESTED — no human evidence |
| te | NOT TESTED | None/None | None | NOT TESTED | NOT TESTED — no human evidence |
| kn | NOT TESTED | None/None | None | NOT TESTED | NOT TESTED — no human evidence |
| ml | NOT TESTED | None/None | None | NOT TESTED | NOT TESTED — no human evidence |
| pa | NOT TESTED | None/None | None | NOT TESTED | NOT TESTED — no human evidence |
| or | NOT TESTED | None/None | None | NOT TESTED | NOT TESTED — no human evidence |
| as | NOT TESTED | None/None | None | NOT TESTED | NOT TESTED — no human evidence |
| en | NOT TESTED | None/None | None | NOT TESTED | NOT TESTED — no human evidence |

## 2. ASR results (synthetic round-trip, local only)

- mr: backend indic, CER clean mean 0.0, worst 0.0, word-miss renders 0.

## 3. TTS results

- mr: backend tiny, 1 renders, audible_all=True, mean duration 3.431 s, render RTF 0.171.

## 4. Pronunciation defects (measured candidates, not native-speaker verdicts)

- None measured in the latest run.

## 5. Prosody and naturalness defects

- NOT TESTED — no human prosody ratings exist. Automated signal gates (audibility, clipping, voice-band coverage) are not naturalness measurements.

## 6. Human evaluation results

- HUMAN DATASET: NOT TESTED (0/240 slots collected, 0 transcripts independently verified).
- Listening responses: 1 files, 1 listeners → PARTIAL.

## 7. MOS

- NOT TESTED. No ITU-T MOS protocol has been run. Listener means, when collected, are labelled 'mean listener rating', never MOS.

## 8. Provider and voice comparison

| lang | selected TTS | tiny | MMS fallback | supertonic eligible | local ASR |
|---|---|---|---|---|---|
| hi | tiny | True | True | True | asr-hi |
| gu | tiny | True | True | False | asr-gu |
| mr | tiny | True | True | False | asr-mr |
| bn | tiny | True | True | False | asr-bn |
| ta | tiny | True | True | False | asr-ta |
| te | tiny | True | True | False | asr-te |
| kn | tiny | True | True | False | asr-kn |
| ml | tiny | True | True | False | asr-ml |
| pa | tiny | True | True | False | asr-pa |
| or | tiny | True | True | False | asr-or |
| as | tiny | True | True | False | asr-bn (bn alias) |
| en | tiny | True | True | True | None |

Selection is unchanged from the frozen V2 configuration; no provider was swapped without measured evidence.

## 9. Latency comparison

- mr: render RTF mean 0.171 (render time / audio duration).
- End-to-end conversational latency: see historical realworld_v2 artifacts; not re-measured against the live port-8000 process by this console.

## 10. CPU and RAM

- Console process RSS: None MB · logical CPUs: 8.
- Configured STT threads: 4; TTS threads knob: 2 (0 = ORT default).
- Historical capacity evidence: benchmarks/results/realworld_v2 (read-only).

## 11. Regression tests

- PASS (automated) — 161 tests, 0 skipped (log: eval\_regression_now.log).

## 12. Known limitations

- Malayalam എന്റെ heard as എറെ in 3/3 takes (repeatable pronunciation candidate).
- Hindi: 1/9 renders decoded to a single character by the Conformer (decode instability).
- Assamese round-trip confounded by the Bengali Conformer alias.
- English local whisper digit formatting inflates raw CER (digit-expanded CER 0.000).
- Synthesis is non-deterministic across takes.
- Assamese ASR uses the Bengali Conformer alias; round-trip CER is confounded.
- Synthesis is non-deterministic; single-render claims are invalid.

## 13. Recommended next improvements

1. Collect the 240-slot human dataset with consented native speakers (≥5/language).
2. Run blind listening sessions with the prepared packages; score with score_responses.
3. Native-speaker review of the Malayalam എന്റെ pronunciation candidate.
4. Investigate the Hindi Conformer single-character decode collapse.
5. Export a dedicated Assamese ASR model to remove the Bengali alias confound.

## 14. Production readiness by language

- hi (Hindi): automated speech generation partially verified; pronunciation partially validated; human naturalness NOT TESTED; production-ready NOT TESTED.
- gu (Gujarati): automated speech generation partially verified; pronunciation partially validated; human naturalness NOT TESTED; production-ready NOT TESTED.
- mr (Marathi): automated speech generation verified; pronunciation partially validated; human naturalness NOT TESTED; production-ready NOT TESTED.
- bn (Bengali): automated speech generation partially verified; pronunciation partially validated; human naturalness NOT TESTED; production-ready NOT TESTED.
- ta (Tamil): automated speech generation partially verified; pronunciation partially validated; human naturalness NOT TESTED; production-ready NOT TESTED.
- te (Telugu): automated speech generation partially verified; pronunciation partially validated; human naturalness NOT TESTED; production-ready NOT TESTED.
- kn (Kannada): automated speech generation partially verified; pronunciation partially validated; human naturalness NOT TESTED; production-ready NOT TESTED.
- ml (Malayalam): automated speech generation partially verified; pronunciation partially validated; human naturalness NOT TESTED; production-ready NOT TESTED.
- pa (Punjabi): automated speech generation partially verified; pronunciation partially validated; human naturalness NOT TESTED; production-ready NOT TESTED.
- or (Odia): automated speech generation partially verified; pronunciation partially validated; human naturalness NOT TESTED; production-ready NOT TESTED.
- as (Assamese): automated speech generation partially verified; pronunciation partially validated; human naturalness NOT TESTED; production-ready NOT TESTED.
- en (English): automated speech generation partially verified; pronunciation partially validated; human naturalness NOT TESTED; production-ready NOT TESTED.

No language is marked production-ready: that claim requires human evidence which does not yet exist.
