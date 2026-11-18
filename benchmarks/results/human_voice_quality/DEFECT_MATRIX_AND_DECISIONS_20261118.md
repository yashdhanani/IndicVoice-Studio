# IndicVoice — defect matrix and decisions (2026-11-18, Phase 2/7/9 pass)

Consolidated from stored measurements by
`benchmarks/language_matrix.py` → `language_audits/20261118-095644/matrix.{md,json}`.
Nothing was re-measured to produce the matrix; the two new experiments are
labelled below.

## Matrix (current)

| lang | TTS | ASR | round-trip CER | clean renders | corpus CER | latency p50 | conversational | worst |
|---|---|---|---|---|---|---|---|---|
| hi | tiny | indic | 0.106 | 8/9 | 0.082 | 1251 ms | PASS | S2 render |
| gu | tiny | indic | 0.021 | 8/9 | 0.000 | 1946 ms | PASS | S2 render |
| mr | tiny | indic | 0.000 | 9/9 | 0.000 | 1840 ms | PASS | — |
| bn | tiny | indic | 0.000 | 9/9 | 0.067 | 1780 ms | PASS | — |
| ta | tiny | indic | 0.004 | 9/9 | 0.000 | 1467 ms | PASS | — |
| te | tiny | indic | 0.000 | 9/9 | 0.000 | 1020 ms | PASS | — |
| kn | tiny | indic | 0.000 | 9/9 | 0.000 | 1912 ms | PASS | — |
| ml | tiny | indic | 0.035 | 5/9 | 0.081 | 1804 ms | PASS | S2 render |
| pa | tiny | indic | 0.018 | 9/9 | 0.056 | 1674 ms | PASS | — |
| or | tiny | indic | 0.027 | 8/9 | 0.133 | 1747 ms | PASS | S2 render |
| **as** | tiny | indic (bn alias) | **0.258** | **0/9** | **0.344** | 1656 ms | PASS | **S1** |
| en | tiny | whisper | 0.141 | 6/9 | 0.141 | 1350 ms | PASS | S2 render |

## Priority 1 — Assamese recognition (S1). **FIXED** on 2026-11-18

> Update: the search for a published export succeeded after this section was
> first written. `parismitaglobalsolutions/indicconformer-sherpa-onnx` ships a
> sherpa-onnx-ready Assamese model; installing it took corpus CER 0.344 → 0.055
> and clean renders 0/9 → 9/9 (PASS automated). The Bengali alias remains only
> as the fallback for installs without the download. See
> `FIX_ATTEMPTS_20261118.md` for the measurements. The historical notes below
> record why the first two attempts failed.

Two experiments:

1. **Is the routing wrong?** Measured cloud Whisper for Assamese against the same
   corpus: **CER 1.770** (vs 0.344 local), with a hallucinated sentence of
   unrelated words (`eval/as_groq.json`). Cloud is far worse — so the current
   routing stays.
2. **Is the text pipeline damaging Assamese?** `TTSEngine.prepare()` returns the
   input string byte-identical for as/ml/hi/or. No transliteration damage.

Conclusion: the S1 is the known Bengali-model alias for a language with no
published Assamese ONNX export. Fixing it needs the export that
`colab/assamese_asr_export.ipynb` was written for — a **user boundary**
(Colab run), not a code change. Recorded as FAIL, model-limited.

## Priority 2 — render misses (S2), explained, not code defects

* **ml 5/9** — the `എന്റെ → എറെ` pattern, stable across all three takes. The text
  fed to the model is correct, so this is the voice's chillu-ന realisation, not
  a normaliser bug. Needs a native ear to confirm before any change.
* **en 6/9** — `one two three → 123` / `1-2-3`: Whisper's number formatting, five
  of nine renders. Semantically harmless, inflates CER.
* **hi one miss** — a single-character decode (`«म»`); a recogniser collapse, not
  missing audio.
* **gu / or one miss each** — minor word-boundary merges (`સુધીમાંડીલીવરી`).

None of these justify a code change without listening evidence, so none was made.

## Phase 9 — resources (measured, existing runs)

| run | peak RSS | final RSS | CPUs |
|---|---|---|---|
| `realworld_v3/latency_v3.json` (hi+en warm, 20 turns each) | 875.6 MB | 838.8 MB | 8 |
| `production_v1/concurrency_v1.json` (sustained load, 100 s) | 732.5 MB | 731.8 MB | 8 |

The concurrency series rises 470 → 732 MB over 90 s and then stays flat, which is
allocation settling, not an unbounded leak. Both are well inside 16 GB.

## Claim status per language (kept separate, never merged)

| claim | status for all 12 |
|---|---|
| Automated speech generation | PASS except **as** (FAIL, S1) |
| Pronunciation | **PARTIAL — automated candidates only**; no native verdict exists |
| Human naturalness (MOS) | **NOT TESTED** — 0 listener responses |
| Production ready | **NOT TESTED** — requires the two above |

## Boundary — what only you can unlock

1. A Colab run of `colab/assamese_asr_export.ipynb` → `models/asr-as-ctc/`,
   which is the only path to fixing the S1.
2. Native listeners for the Malayalam `എന്റെ` candidate and the Assamese mapping.
3. The 240-slot human dataset (`src/quality_console.py`, port 8010) — the only
   route from NOT TESTED to a naturalness claim.
