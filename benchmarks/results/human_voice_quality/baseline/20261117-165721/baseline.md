# Phase 0 baseline audit — IndicVoice human voice-quality project

Generated 2026-11-17 16:57:21 · HEAD `fc6d0b3bd` (main) · read-only audit, new directory `benchmarks\results\human_voice_quality\baseline\20261117-165721`

## Repository inventory

* src modules: 13 · tests: 14 · benchmark harnesses: 13 · docs: 26
* dataset slots: 240 ({'NOT_COLLECTED': 240})
* blind listening package: 96 samples, 10 dimensions; listener responses on disk: 0
* historical result trees: ab_full.json, ab_full.md, ab_mr_gu.json, ab_mr_gu.md, human_voice_quality, production_v1, realworld_v2, smoke_live_hi.md

## Working tree at audit time

```
M eval/speak_check.py
 M src/config.py
 M src/streaming_stt.py
 M src/tts_engine.py
?? benchmarks/quality_baseline.py
?? benchmarks/run_thread_sweep.py
?? eval/speak_check_20261117-162153.zip
?? eval/speak_check_20261117-162153/
?? eval/speak_check_20261117-162833.zip
?? eval/speak_check_20261117-162833/
?? eval/speak_check_20261117-163551.zip
?? eval/speak_check_20261117-163551/
```

## Providers and language configuration

| lang | TTS selected | tiny | mms | supertonic eligible | local ASR | endpoint s |
|---|---|---|---|---|---|---|
| hi | tiny | yes | yes | yes | asr-hi | 0.26 |
| gu | tiny | yes | yes | no | asr-gu | 0.26 |
| mr | tiny | yes | yes | no | asr-mr | 0.26 |
| bn | tiny | yes | yes | no | asr-bn | 0.26 |
| ta | tiny | yes | yes | no | asr-ta | 0.26 |
| te | tiny | yes | yes | no | asr-te | 0.26 |
| kn | tiny | yes | yes | no | asr-kn | 0.26 |
| ml | tiny | yes | yes | no | asr-ml | 0.26 |
| pa | tiny | yes | yes | no | asr-pa | 0.26 |
| or | tiny | yes | yes | no | asr-or | 0.26 |
| as | tiny | yes | yes | no | asr-bn (bn alias) | 0.26 |
| en | tiny | yes | yes | yes | whisper | 0.45 |

LLM primary: `openai/gpt-oss-20b` (reasoning low); not exercised here.

## Live server (client-side probe only)

* /health → 200 · /metrics → 404
* running process predates HEAD: /metrics exists in source but returns 404 live

## Automated tests (current run)

* status: PASS (automated) · tests run: 161 · skipped: 0

## Latest speak-check evidence (synthetic round-trip, not human)

Run `speak_check_20261117-163551` (3 takes/sentence):

| lang | renders | clean | CER clean mean | worst | status |
|---|---|---|---|---|---|
| hi | 9 | 8 | 0.106 | 0.955 | PARTIAL |
| gu | 9 | 8 | 0.021 | 0.111 | PARTIAL |
| mr | 9 | 9 | 0.0 | 0.0 | PASS (automated) |
| bn | 9 | 9 | 0.0 | 0.0 | PASS (automated) |
| ta | 9 | 9 | 0.004 | 0.034 | PASS (automated) |
| te | 9 | 9 | 0.0 | 0.0 | PASS (automated) |
| kn | 9 | 9 | 0.0 | 0.0 | PASS (automated) |
| ml | 9 | 5 | 0.035 | 0.087 | PARTIAL |
| pa | 9 | 9 | 0.018 | 0.074 | PASS (automated) |
| or | 9 | 8 | 0.027 | 0.048 | PARTIAL |
| as | 9 | 0 | 0.258 | 0.3 | PARTIAL |
| en | 9 | 6 | 0.141 | 0.423 | PARTIAL |

## Known defects carried into this project

* Malayalam `എന്റെ` heard as `എറെ` in 3/3 takes (repeatable pronunciation candidate).
* Hindi: 1/9 renders decoded to a single character by the production Conformer while a second recogniser heard the full sentence (decode instability, audio healthy).
* Assamese round-trip confounded: decoded by the Bengali Conformer (no Assamese export).
* English local whisper writes digits ('1-2-3'); digit-expanded CER 0.000 (formatting, not speech).
* Synthesis is non-deterministic: identical text renders different audio each take.
* Human dataset: 0/240 collected. MOS / mean listener ratings: NOT TESTED.

## Safety attestation

* Historical V1/V2 results read only; nothing overwritten.
* Port 8000 process untouched; probed as a client.
* No cloud inference, no paid API, `.env` never read.
