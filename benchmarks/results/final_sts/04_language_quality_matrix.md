# 04 — Language Quality Matrix (all 12)

Status vocabulary: PASS — Automated / PASS — Manually verified / PARTIAL / FAIL / NOT TESTED / NOT APPLICABLE. One status per language. Synthetic round-trip only; real human speech accuracy is NOT TESTED for all languages (0/240 real recordings).

## ASR (synthetic round-trip CER from latest stage bench, 2 repeats)

| Code | Language | TTS backend | TTS ms p50 | ASR ms p50 | Round-trip CER | VAD splits | Stage-bench status | Human speech ASR |
|---|---|---|---|---|---|---|---|---|
| hi | Hindi | tiny | 318.0 | 192.8 | 0.000 | 0 | PASS — Automated (synthetic) | NOT TESTED |
| gu | Gujarati | tiny | 496.4 | 1876.8 | 0.000 | 1 | PASS — Automated (synthetic) | NOT TESTED |
| mr | Marathi | tiny | 430.0 | 1913.4 | 0.037 | 0 | PASS — Automated (synthetic) | NOT TESTED |
| bn | Bengali | tiny | 324.4 | 1319.5 | 0.000 | 0 | PASS — Automated (synthetic) | NOT TESTED |
| ta | Tamil | tiny | 335.0 | 1221.7 | 0.000 | 0 | PASS — Automated (synthetic) | NOT TESTED |
| te | Telugu | — | — | — | — | — | NOT TESTED (no bench phrase) | NOT TESTED |
| kn | Kannada | — | — | — | — | — | NOT TESTED (no bench phrase) | NOT TESTED |
| ml | Malayalam | — | — | — | — | — | NOT TESTED (no bench phrase) | NOT TESTED |
| pa | Punjabi | — | — | — | — | — | NOT TESTED (no bench phrase) | NOT TESTED |
| or | Odia | — | — | — | — | — | NOT TESTED (no bench phrase) | NOT TESTED |
| as | Assamese | — | — | — | — | — | NOT TESTED (no bench phrase) | NOT TESTED |
| en | English | tiny | 502.5 | 592.5 | 0.216 | 0 | PASS — Automated (synthetic) | NOT TESTED |

Notes:
- Prior docs report ASR-stage A/B parity for all 12 languages (streaming vs block, CER/WER identical) on the synthesized 36-clip corpus. Those measurements are synthetic and not re-run here.
- Prior reported synthetic-corpus CER (n=3/lang): hi 0.047, gu 0.025, mr 0.000, bn 0.044, ta 0.000, te 0.000, kn 0.012, ml 0.029, pa 0.042, or 0.088, as 0.268 (Bengali-model alias), en 0.141.
- Assamese (`as`) rides the Bengali Conformer unless `asr-as` model present; CER 0.268 is a mapping artifact.
- E2E latency measured only for hi and en (2×40 live turns). Other 10 languages: NOT TESTED for E2E.
- TTS naturalness (MOS): NOT TESTED for all languages (no human listeners).
- VAD false positives on 5 s silence: 0 for all measured languages.

## Conclusion

No language is validated on real human speech. Synthetic round-trip evidence is strong for hi/gu/mr/bn/ta/en; te/kn/ml/pa/or/as lack even synthetic stage-bench coverage in this run (tooling gap, not necessarily engine failure). Production readiness for any language is NOT established.