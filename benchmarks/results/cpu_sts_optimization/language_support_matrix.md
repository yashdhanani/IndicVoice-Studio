# Language Support Matrix (12 languages)

Status: PASS — Automated / PASS — Human verified / PARTIAL / FAIL / NOT TESTED / NOT APPLICABLE.

| Code | Lang | ASR backend | TTS backend | Synthetic CER | Stage bench | E2E | Human ASR | Human TTS MOS | Status |
|---|---|---|---|---|---|---|---|---|---|
| hi | Hindi | IndicConformer | tiny/supertonic | 0.047 (prior) / 0.000 (round-trip) | measured | measured (p50 1.13s) | NOT TESTED | NOT TESTED | PARTIAL |
| gu | Gujarati | IndicConformer | tiny | 0.025 / 0.000 | measured (1 VAD split) | NOT TESTED | NOT TESTED | NOT TESTED | PARTIAL |
| mr | Marathi | IndicConformer | tiny | 0.000 / 0.037 | measured | NOT TESTED | NOT TESTED | NOT TESTED | PARTIAL |
| bn | Bengali | IndicConformer | tiny | 0.044 / 0.000 | measured | NOT TESTED | NOT TESTED | NOT TESTED | PARTIAL |
| ta | Tamil | IndicConformer | tiny | 0.000 / 0.000 | measured | NOT TESTED | NOT TESTED | NOT TESTED | PARTIAL |
| te | Telugu | IndicConformer | tiny | 0.000 (prior) | NOT TESTED (no bench phrase) | NOT TESTED | NOT TESTED | NOT TESTED | NOT TESTED |
| kn | Kannada | IndicConformer | tiny | 0.012 (prior) | NOT TESTED | NOT TESTED | NOT TESTED | NOT TESTED | NOT TESTED |
| ml | Malayalam | IndicConformer | tiny | 0.029 (prior) | NOT TESTED | NOT TESTED | NOT TESTED | NOT TESTED | NOT TESTED |
| pa | Punjabi | IndicConformer | tiny | 0.042 (prior) | NOT TESTED | NOT TESTED | NOT TESTED | NOT TESTED | NOT TESTED |
| or | Odia | IndicConformer | tiny | 0.088 (prior) | NOT TESTED | NOT TESTED | NOT TESTED | NOT TESTED | NOT TESTED |
| as | Assamese | IndicConformer (bn alias) | tiny | 0.268 (prior) | NOT TESTED | NOT TESTED | NOT TESTED | NOT TESTED | NOT TESTED |
| en | English | Groq Whisper | tiny/supertonic | 0.141 (prior) / 0.216 (round-trip) | measured | measured (p50 1.26s) | NOT TESTED | NOT TESTED | PARTIAL |

No language is human-verified. te/kn/ml/pa/or/as lack even synthetic stage-bench coverage in this run (tooling gap).