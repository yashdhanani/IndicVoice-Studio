# Defect fixes — final outcomes (2026-11-18)

Two S-level defects were worked to conclusion. **One is fixed with measured
evidence; the other is conclusively not fixable in code.** Details below so
every claim can be re-checked.

## 1. Assamese recognition (S1) — FIXED

### What was wrong
Assamese had no model of its own; audio was decoded with the Bengali
Conformer. Corpus CER **0.344**, and speak_check could not get a single clean
render (**0/9**), because the transcript came back in Bengali orthography
(`অর্ডার` for `অৰ্ডাৰ`).

### What was tried first (both rejected, measured)
| recogniser | CER |
|---|---|
| local Bengali alias (baseline) | 0.344 |
| Groq `whisper-large-v3-turbo` | 1.770 — invented an unrelated sentence |
| Groq `whisper-large-v3` | 0.778 |

Cloud was worse at both settings, so no routing change.

### The actual fix
A sherpa-onnx-ready Assamese export now exists
(`parismitaglobalsolutions/indicconformer-sherpa-onnx`, MIT source model,
validated end-to-end by its publisher). Downloaded `as/model.int8.onnx`
(197.6 MB) and the shared `tokens.txt` into `models/asr-as/`, and pointed
`config.INDIC_ASR["as"]` at it. The Bengali alias is retained as
`fallback_dir`, so installs that never download the model behave exactly as
before.

### Measured result

| metric | before | after |
|---|---|---|
| corpus CER (3 utterances) | 0.344 | **0.055** |
| speak_check round trip | 0.258 | **0.014** |
| clean renders | 0/9 | **9/9 (100 %)** |
| speak_check status | PARTIAL/FAIL | **PASS (automated)** |
| transcript orthography | Bengali | **Assamese** (`মোৰ`, `কাইলৈ`, `ডেলিভাৰী`) |

Evidence: `eval/accuracy_as_new.json`, `eval/speak_check_20261118-100912/`.

## 2. Malayalam "എന്റെ" → "എറെ" (S2) — NOT fixable in code

Hypothesis was that the voice cannot say the conjunct ന്റ, so spell it the
other way. Three spellings, 10 takes each, through the production render path:

| spelling | correct | mean CER |
|---|---|---|
| ന്റ (na + virama + rra) — original | **0/10** | 0.087 |
| ൻറ (chillu n + rra) | **0/10** | 0.087 |

Identical, so the text transform was **reverted** — `git diff src/translit.py`
is empty. This one needs a native ear (is the clip actually wrong?) and, if it
is, a different Malayalam voice.

### Caution recorded from this investigation
Mid-investigation the same clip scored 6/6, then 5/5, then 3/5 across runs and
speeds. At production settings with 10 takes it is 0/10 both ways. Those small
samples were noise; only the 10-take A/B is reported as evidence.

## Regression status

`unittest` (176 tests): **OK** after the final state, 143 s.
`src` and `benchmarks` compile on Python 3.15 and 3.13.
