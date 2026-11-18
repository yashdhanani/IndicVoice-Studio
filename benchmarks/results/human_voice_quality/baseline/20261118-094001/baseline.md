# Phase 0 baseline audit — IndicVoice human voice-quality project

Generated 2026-11-18 09:40:05 · HEAD `fe143f3d2` (main) · read-only audit, new directory `benchmarks\results\human_voice_quality\baseline\20261118-094001`

## Repository inventory

* src modules: 14 · tests: 15 · benchmark harnesses: 14 · docs: 27
* dataset slots: 240 ({'NOT_COLLECTED': 240})
* blind listening package: 96 samples, 10 dimensions; listener responses on disk: 0
* historical result trees: ab_full.json, ab_full.md, ab_mr_gu.json, ab_mr_gu.md, human_voice_quality, production_v1, realworld_v2, realworld_v3, smoke_live_hi.md

## Working tree at audit time

```
M eval/speak_check.py
 M src/call_server.py
 M src/sts_pipeline.py
 M tests/test_v3_performance.py
 M tests/test_ws_server.py
?? benchmarks/quality_baseline.py
?? benchmarks/results/human_voice_quality/
?? benchmarks/results/realworld_v3/latency_v3.json
?? benchmarks/results/realworld_v3/latency_v3_hi_ep200.json
?? benchmarks/run_latency_v3.py
?? eval/_quality_qa.mjs
?? eval/quality_shots/
?? eval/speak_check_20261117-162153.zip
?? eval/speak_check_20261117-162153/
?? eval/speak_check_20261117-162833.zip
?? eval/speak_check_20261117-162833/
?? eval/speak_check_20261117-163551.zip
?? eval/speak_check_20261117-163551/
?? eval/speak_check_20261117-172031/
?? eval/speak_check_20261117-172419/
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

* /health → None · /metrics → None
* live process matches source routes probed

## Automated tests (current run)

* status: NOT TESTED · tests run: None · skipped: None

## Latest speak-check evidence (synthetic round-trip, not human)

Run `speak_check_20261117-173526` (1 takes/sentence):

| lang | renders | clean | CER clean mean | worst | status |
|---|---|---|---|---|---|
| mr | 1 | 1 | 0.0 | 0.0 | PASS (automated) |

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
