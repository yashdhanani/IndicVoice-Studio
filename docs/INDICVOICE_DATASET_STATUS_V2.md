# IndicVoice — Dataset Status V2 (Phase B)

Date: 2026-11-17 · Manifest: `evaluation/dataset_manifest.jsonl` (240 slots) ·
Schema: `evaluation/dataset_schema.json` · Protocol: `evaluation/recording_guide.md`.

## Actual recording counts (not plans)

| Language | Collected | Target | Speakers (target ≥5) | Verified transcripts |
|---|---|---|---|---|
| hi | 0 | 20 | 0 | 0 |
| gu | 0 | 20 | 0 | 0 |
| mr | 0 | 20 | 0 | 0 |
| bn | 0 | 20 | 0 | 0 |
| ta | 0 | 20 | 0 | 0 |
| te | 0 | 20 | 0 | 0 |
| kn | 0 | 20 | 0 | 0 |
| ml | 0 | 20 | 0 | 0 |
| pa | 0 | 20 | 0 | 0 |
| or | 0 | 20 | 0 | 0 |
| as | 0 | 20 | 0 | 0 |
| en | 0 | 20 | 0 | 0 |
| **Total** | **0** | **240** | 0 | 0 |

**Status: NOT COLLECTED.** No human recordings exist in this environment;
collecting them requires consented volunteer speakers across 12 languages —
a human-participant task that cannot be executed by this session. No
synthetic audio, TTS clip, or placeholder has been or will be counted toward
the 240. If a future session collects 120, the report must say 120/240.

Raw evidence: `benchmarks/results/realworld_v2/dataset_validation_v2.json`
(0 invalid entries), `dataset_report_v2.json` / `.md`.

## What IS delivered and verified (tooling)

| Item | Verification | Status |
|---|---|---|
| `evaluation/dataset_schema.json` — full JSON Schema incl. V2 fields (script, sample_rate, environment, transcript_verified, audio_sha256), conditional rules per status | reviewed against manifest + validator | PASS (automated consistency via tests) |
| `benchmarks/ingest_dataset.py` — CLI ingestion with all required detections: missing file, empty audio, corrupted audio, wrong sample rate, unexpected channels, clipping (>1% full-scale), silence, duplicate PCM (SHA-256), missing reference, invalid language, metadata enums, incomplete consent; optional conversion preserving originals; dry-run; human verification subcommand | 17 regression tests (`tests/test_dataset_tools.py`) + CLI smoke (accept + consent-reject paths) | PASS (automated) |
| `benchmarks/dataset_report.py` — actual-count reporting: per-language collected/speakers/noise/domain/duration/verification | exercised on the real manifest (0/240) + test | PASS (automated) |
| `benchmarks/validate_dataset.py` — extended for V2 metadata; default path updated to the moved manifest | full validation run: 0 invalid; prior 6/6 self-tests still valid | PASS (automated) |
| `evaluation/recording_guide.md` — consent procedure, 10 content categories, ≥5 speakers/language, noise plan, canonical format, ingest + verify commands | protocol document | delivered |
| Git exclusions — `evaluation/dataset/audio/`, `evaluation/dataset/originals/` (plus human-eval audio/responses for Phase E) | `.gitignore` inspected; no recordings tracked | PASS (automated: `git ls-files` shows no audio) |

## Design guarantees

- **Reference integrity**: the ingest tool only accepts human-supplied
  `--reference` text; it never transcribes audio. `transcript_verified`
  starts `false` and can only be set by the explicit `verify` subcommand with
  a second pseudonymous speaker (self-verification is rejected).
- **Consent gate**: `--consent` is a human assertion; without it ingestion is
  rejected. The guide requires recorded/signed consent kept with originals.
- **No silent mutation**: rejection writes nothing; dry-run writes nothing;
  manifest updates are atomic (temp file + replace); originals are preserved
  on conversion.
- **Privacy**: pseudonymous IDs only; audio and originals git-ignored; no
  upload path exists in any tool.

## Acceptance condition (unchanged, honest)

The dataset milestone is met only when
`python benchmarks/validate_dataset.py --require-complete` exits 0 with 240
genuine, valid, consented recordings. Today that command exits 2. Every
accuracy metric in this repository remains labeled **synthetic-corpus** until
then, and real-corpus CER/WER is **NOT TESTED**.