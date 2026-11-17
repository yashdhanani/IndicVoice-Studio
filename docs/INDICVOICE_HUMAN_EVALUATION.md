# IndicVoice — Human Speech-Quality Evaluation (Real-World V2, Phase E)

Date: 2026-11-17
Status vocabulary: PASS (automated) / PASS — manually verified / PARTIAL / FAIL / NOT TESTED / NOT APPLICABLE.

**Bottom line: human listening quality is NOT TESTED.** No listener has
rated anything. The complete evaluation package is built, synthesized and
UI-verified, ready to run the moment native/fluent listeners are available.
No scores are reported anywhere, and none may be invented. TTS RTF
(0.11–0.20, V1 Phase E) measures speed, not naturalness — it is not evidence
for any quality claim in this document.

## 1. What is being evaluated

All 12 production voices (Indic Tiny TTS; `as` shares the Bengali voice —
a documented workaround, listeners will hear exactly what callers hear).
The same six representative utterance types in every language
(`evaluation/human_voice_quality/utterances.json`):

| Key | Purpose |
|---|---|
| greeting | conversational opening, question intonation |
| statement | declarative sentence ending |
| question | sentence-final rising intonation |
| digits_currency | digit strings + currency amount clarity |
| code_mixed | English loanwords inside native speech |
| long_sentence | multi-clause rhythm, pauses, breath groups |

**Translation status: DRAFT.** The 12-language texts were authored for this
package and must be reviewed by a native/fluent speaker per language before
sessions start. One defect was already caught mechanically: the draft
Malayalam "nine" contained Tamil codepoints (U+0BA9/U+0BCD/U+0BAA); the TTS
engine warned `unsupported characters skipped: 'னப்'`, the text was fixed
to Malayalam മ്പ and the package re-synthesized clean (verified with
warnings-as-errors). A full foreign-script scan of all 72 texts now passes.
This is exactly why native review remains mandatory — script checks cannot
catch grammar or word-choice errors.

## 2. Rating instrument

Ten dimensions, each rated independently on a documented 5-point scale:

pronunciation, intelligibility, naturalness, prosody, rhythm, pauses,
sentence_endings, question_intonation, conversational_feel, overall.

| Point | Anchor |
|---|---|
| 5 | Excellent — no noticeable problem in this dimension |
| 4 | Good — minor issue, does not interfere |
| 3 | Fair — noticeable issue, still acceptable |
| 2 | Poor — distracting issue, interferes with the message |
| 1 | Bad — severe issue, breaks understanding or comfort |

`question_intonation` is rated on every sample: for questions, whether the
rise is right; for non-questions, whether the declarative ending sounds
correct. Listeners are told this explicitly so the dimension is never
silently skipped. Qualitative free-text feedback is collected per sample
and overall.

## 3. Methodology

- **Listeners**: native or fluent speakers of the language they rate.
  Target ≥ 3 listeners per language (minimum 1 for a pilot read, flagged as
  low-n). Pseudonymous IDs only; native language and fluency list are
  collected *after* all ratings, so they cannot anchor the ratings.
- **Anonymization**: samples carry random 6-hex codes. The public package
  (`package.json`) contains no language labels, no texts, no voice names.
  The answer key (`private/sample_map.json`) is git-ignored and never shown
  to listeners. Regression tests assert the public package leaks neither
  texts nor language fields.
- **Randomization**: presentation order is a seeded shuffle across all 96
  samples (12 languages interleaved), so no listener hears a language block
  that could induce contrast effects. Seed recorded for reproducibility.
- **Repeated samples**: 2 per language (24 total) are byte-identical
  re-presentations under fresh codes, shuffled into the sequence. Listeners
  are told repeats exist and to rate each presentation independently.
  Per-listener |Δ| between repeat pairs measures rating consistency;
  large deltas flag unreliable raters or unstable perception.
- **Environment**: headphones in a quiet room recommended; setup recorded.
  Samples may be replayed before rating; all 10 dimensions are required to
  advance (enforced by the interface).
- **No leading**: instructions never name a preferred voice, model, or
  expected quality. The interface shows only the code and the audio.

### Why this is NOT an industry-standard MOS

ITU-T P.800 MOS requires controlled listening conditions, screened
non-expert listeners, reference/baseline conditions, balanced presentation
design and standardized procedures. This package is a structured
in-house listening test with fluent speakers. Its outputs are labeled
**"mean listener rating (5-point scale) — NOT ITU-T MOS"** everywhere
(`score_responses.py` hard-codes the label). Reporting these numbers as
"MOS" in any external material would be a methodology misrepresentation.

## 4. Reporting

`score_responses.py` produces, per language and per dimension:

- mean listener rating, sample standard deviation,
- n_listeners, n_utterances, n_ratings (all reported separately — never
  collapsed into a single headline number),
- repeat-consistency (pairs rated, mean |Δ|, max |Δ|),
- qualitative feedback verbatim (pseudonymous),
- data problems (out-of-range ratings, unknown codes/dimensions) listed,
  not silently dropped.

With zero responses the report status is **NOT TESTED** and contains no
numbers (current state: `benchmarks/results/realworld_v2/human_eval_v2.json`).

## 5. What was executed in this environment

| Step | Evidence | Status |
|---|---|---|
| Package synthesis, all 12 voices, 72 unique + 24 repeat = 96 WAVs | `human_eval_package_v2.json` (failures: {}), seed 20261117 | PASS (automated) |
| ml script defect found → fixed → re-synthesized warning-free | warnings-as-errors verification run | PASS (automated) |
| Foreign-script scan of all 72 texts | scan output: only the ml defect, now fixed | PASS (automated) |
| Tooling regression tests (anonymization, seeded order, repeats, failure reporting, WAV clipping, aggregation math, NOT TESTED gate, invalid-rating flagging) | `tests/test_human_eval.py`, 9 tests | PASS (automated) |
| Listening interface UI smoke test: package loads, 10 dims render, Next gated until fully rated, audio decodes (269 KB WAV), all 96 samples traversed, export JSON well-formed (96×10 ratings) | embedded Chromium session 2026-11-17; synthetic output **discarded**, never written to `responses/` | PASS (automated, UI only — not a listening test) |
| Scorer with zero responses → NOT TESTED, no fabricated numbers | `human_eval_v2.json` / `.md` | PASS (automated) |
| Actual human listening sessions | none available in this environment | **NOT TESTED** |

## 6. How to run a real session

1. Native-review `utterances.json` translations (mandatory; fix + re-prepare
   if changed).
2. Serve the package folder:
   `python -m http.server 8020 --directory evaluation/human_voice_quality`
   Listener opens `http://127.0.0.1:8020/listening.html` (or any static
   host). Distribute only `listening.html`, `package.json`, `audio/` —
   never `private/`. For remote listeners use an access-controlled channel;
   the audio is synthetic system output, but keep the answer key private.
3. Listener: pseudonymous ID → rate all 96 samples (~25–35 min) → export
   JSON → coordinator files it under `responses/`.
4. Score:
   `.venv313/Scripts/python.exe evaluation/human_voice_quality/score_responses.py`
5. File results under `benchmarks/results/realworld_v2/` and update this
   document's status table with dates, listener counts and observations.

## 7. Completion gate

Phase E is complete only when ≥ 3 native/fluent listeners per language have
rated the package, `score_responses.py` reports COLLECTED with per-language
mean/SD/n, repeat-consistency is reviewed, and this document is updated.
Until then every quality statement about the voices remains **NOT TESTED**,
and the V1 readiness score's TTS-quality component stays evidence-limited.