# Human Voice-Quality Evaluation Package (Real-World V2, Phase E)

Purpose: find out what callers actually hear from the 12 Indic Tiny voices.
RTF (speed) is not naturalness — only human listeners can judge that.

**Status: MOS / mean listener ratings are NOT TESTED.** The package below is
built and ready; no listening session has been run. No scores exist, and
none may be invented.

## Contents

| Path | What it is |
|---|---|
| `utterances.json` | The fixed 6-utterance representative set in all 12 languages (DRAFT translations — native review required before sessions), 10 rating dimensions, 5-point scale anchors |
| `prepare_samples.py` | Synthesizes the set with the production TTS voices, anonymizes (random hex codes), shuffles, adds 2 repeated samples per language, writes forms |
| `package.json` | Public listener package: codes + instructions + scale. No language, no text |
| `audio/<code>.wav` | The samples (git-ignored; distribute via access-controlled channel) |
| `private/sample_map.json` | Answer key code→(lang, utterance, repeat_of). **Never show to listeners** (git-ignored) |
| `private/preparation_report.json` | Build report (also copied to `benchmarks/results/realworld_v2/human_eval_package_v2.json`) |
| `forms/rating_form.csv` | Offline paper-style form, one row per sample |
| `listening.html` | Browser listening interface: play → rate 10 dimensions → optional feedback → export response JSON |
| `score_responses.py` | Aggregates responses: per-language mean/SD/n-listeners/n-utterances per dimension, repeat-consistency, qualitative feedback; NOT TESTED when empty |
| `responses/` | Listener response JSONs go here (git-ignored; pseudonymous IDs only) |

## Running a session (coordinator)

1. Native-review the translations in `utterances.json`; fix and re-run
   preparation if anything changes.
2. Regenerate if needed:
   `.venv313/Scripts/python.exe evaluation/human_voice_quality/prepare_samples.py --seed <new>`
3. Serve the folder: `python -m http.server 8020 --directory evaluation/human_voice_quality`
   and give the listener `http://127.0.0.1:8020/listening.html` (or host the
   folder on any static server; only `package.json`, `listening.html` and
   `audio/` are needed — never `private/`).
4. Listener enters a pseudonymous ID, rates every sample (all 10 dimensions
   required), exports the JSON. Collect into `responses/`.
5. Score:
   `.venv313/Scripts/python.exe evaluation/human_voice_quality/score_responses.py`
   → `benchmarks/results/realworld_v2/human_eval_v2.json` + `.md`.

Full methodology, scale anchors, listener requirements and reporting rules:
`docs/INDICVOICE_HUMAN_EVALUATION.md`.