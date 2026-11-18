# IndicVoice — language defect matrix

Generated 2026-11-18 09:56:44 from stored measurements (nothing re-measured here).

## Claims are separate on purpose

| claim | meaning |
|---|---|
| automated speech generation | voice produced non-empty, correct-script, round-trip-intelligible audio |
| pronunciation | NOT native-verified unless stated |
| human naturalness | needs listener ratings (MOS) |
| production ready | needs both of the above |

Human dataset: **0/240 collected** (0 transcript-verified), listener responses: **0** → `HUMAN DATASET: NOT TESTED`

## Matrix

| lang | TTS | ASR backend | round-trip CER | clean renders | corpus CER | latency p50 | conversational | worst defect |
|---|---|---|---|---|---|---|---|---|
| hi | tiny | indic | 0.106 | 8/9 | 0.082 | 1251 ms | PASS | S2 tts_render |
| gu | tiny | indic | 0.021 | 8/9 | 0.000 | 1946 ms | PASS | S2 tts_render |
| mr | tiny | indic | 0.000 | 1/1 | 0.000 | 1840 ms | PASS | none |
| bn | tiny | indic | 0.000 | 9/9 | 0.067 | 1780 ms | PASS | none |
| ta | tiny | indic | 0.004 | 9/9 | 0.000 | 1467 ms | PASS | none |
| te | tiny | indic | 0.000 | 9/9 | 0.000 | 1020 ms | PASS | none |
| kn | tiny | indic | 0.000 | 9/9 | 0.000 | 1912 ms | PASS | none |
| ml | tiny | indic | 0.035 | 5/9 | 0.081 | 1804 ms | PASS | S2 tts_render |
| pa | tiny | indic | 0.018 | 9/9 | 0.056 | 1674 ms | PASS | none |
| or | tiny | indic | 0.027 | 8/9 | 0.133 | 1747 ms | PASS | S2 tts_render |
| as | tiny | indic | 0.258 | 0/9 | 0.344 | 1656 ms | FAIL | S1 asr_accuracy |
| en | tiny | whisper | 0.141 | 6/9 | 0.141 | 1350 ms | PASS | S2 tts_render |

## Defects by severity

- **S1 as · asr_accuracy** — round-trip CER 0.258 > 0.15 (`eval\speak_check_20261117-163551\results.json`)
- **S1 as · tts_render** — 0/9 clean renders (`eval\speak_check_20261117-163551\results.json`)
- **S1 as · asr_accuracy_corpus** — corpus CER 0.344 > 0.15 (`eval\accuracy.json`)
- **S2 en · tts_render** — 6/9 clean renders (`eval\speak_check_20261117-163551\results.json`)
- **S2 gu · tts_render** — 8/9 clean renders (`eval\speak_check_20261117-163551\results.json`)
- **S2 hi · tts_render** — 8/9 clean renders (`eval\speak_check_20261117-163551\results.json`)
- **S2 ml · tts_render** — 5/9 clean renders (`eval\speak_check_20261117-163551\results.json`)
- **S2 or · tts_render** — 8/9 clean renders (`eval\speak_check_20261117-163551\results.json`)
- **S3 en · asr_accuracy** — round-trip CER 0.141 > 0.05 (`eval\speak_check_20261117-163551\results.json`)
- **S3 hi · asr_accuracy** — round-trip CER 0.106 > 0.05 (`eval\speak_check_20261117-163551\results.json`)

## Phase 9 — CPU and memory (measured, from existing runs)

- latency_run: peak RSS 875.6 MB, final 838.8 MB, 8 logical CPUs (`benchmarks\results\realworld_v3\latency_v3.json`)
- concurrency_run: peak RSS 732.5 MB, final 731.8 MB, 8 logical CPUs (`benchmarks\results\production_v1\concurrency_v1.json`)

## What is still unmeasured

- MOS, naturalness, prosody and pronunciation by native listeners: **NOT TESTED**.
- Real-caller recognition accuracy: every audio measurement here is synthesised.
- Physical microphone, phone and telephony acoustics: **NOT TESTED**.
