# IndicVoice — language defect matrix

Generated 2026-11-18 09:55:56 from stored measurements (nothing re-measured here).

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
| hi | - | - | - | -/- | 0.082 | 1251 ms | PASS | none |
| gu | - | - | - | -/- | 0.000 | 1946 ms | PASS | none |
| mr | tiny | indic | 0.000 | 1/1 | 0.000 | 1840 ms | PASS | none |
| bn | - | - | - | -/- | 0.067 | 1780 ms | PASS | none |
| ta | - | - | - | -/- | 0.000 | 1467 ms | PASS | none |
| te | - | - | - | -/- | 0.000 | 1020 ms | PASS | none |
| kn | - | - | - | -/- | 0.000 | 1912 ms | PASS | none |
| ml | - | - | - | -/- | 0.081 | 1804 ms | PASS | none |
| pa | - | - | - | -/- | 0.056 | 1674 ms | PASS | none |
| or | - | - | - | -/- | 0.133 | 1747 ms | PASS | none |
| as | - | - | - | -/- | 0.344 | 1656 ms | FAIL | S1 asr_accuracy_corpus |
| en | - | - | - | -/- | 0.141 | 1350 ms | PASS | none |

## Defects by severity

- **S1 as · asr_accuracy_corpus** — corpus CER 0.344 > 0.15 (`eval\accuracy.json`)
- **S2 as · code_switch** — caller's English term not preserved (`benchmarks\results\human_voice_quality\conversational_postfix\20261118-094800\report.json`)

## Phase 9 — CPU and memory (measured, from existing runs)

- latency_run: peak RSS 875.6 MB, final 838.8 MB, 8 logical CPUs (`benchmarks\results\realworld_v3\latency_v3.json`)
- concurrency_run: peak RSS 732.5 MB, final 731.8 MB, 8 logical CPUs (`benchmarks\results\production_v1\concurrency_v1.json`)

## What is still unmeasured

- MOS, naturalness, prosody and pronunciation by native listeners: **NOT TESTED**.
- Real-caller recognition accuracy: every audio measurement here is synthesised.
- Physical microphone, phone and telephony acoustics: **NOT TESTED**.
