# IndicVoice — Phase 0 + Phase 3 audit (2026-11-18)

Status vocabulary: **PASS (automated)** / **PASS — manually verified** / PARTIAL /
FAIL / **NOT TESTED** / NOT APPLICABLE. Human naturalness is **NOT TESTED** in
this document; nothing here is a listening result.

## Phase 0 — baseline

* HEAD `fe143f3d2` (branch `main`), working tree carries uncommitted V3 work.
* Report: `benchmarks/results/human_voice_quality/baseline/20261118-094001/`
  (`baseline.json`, `baseline.md`).
* Regression suite: `.venv313/Scripts/python.exe -m unittest discover -s tests`
  → **176 tests, OK** (146 s). Log:
  `benchmarks/results/human_voice_quality/regression/20261118/tests.log`.
  `pytest` is not installed in either venv; the suite is stdlib `unittest`.
* Human dataset: **0 / 240 slots collected** — HUMAN DATASET: NOT TESTED.
* Blind listening package exists (96 samples, 10 dimensions); **0 listener
  responses on disk** — MOS: NOT TESTED.
* Port 8000: no listener at audit time; nothing was started, stopped or
  reconfigured by this audit.

## Phase 3 — defect found and fixed

### Defect: the voice is female, the words were masculine

Production renders through `TTSEngine(sid=0)`, the female voice of every tiny
model. Hindi, Marathi and Punjabi mark the speaker's own gender in the verb, and
the system prompt said nothing about it.

Measured before the fix (`conversational_prefixed/20261118-094528/report.md`):

| lang | reply to "can you help me?" | verdict |
|---|---|---|
| hi | «…मैं आपकी कैसे सहायता **कर सकता** हूँ?» | FAIL — masculine, female voice |
| pa | «…ਮੈਂ ਤੁਹਾਡੀ ਕਿਵੇਂ ਮਦਦ **ਕਰ ਸਕਦਾ** ਹਾਂ?» | FAIL — masculine, female voice |
| mr | «कशात मदत हवी आहे?» | unmarked |

Fix (`src/config.py`, `src/sts_pipeline.py`): `config.VOICE_GENDER`
(default `female`, override `INDICVOICE_VOICE_GENDER`), and a `{gender_rule}`
line in `SYSTEM_PROMPT` that reaches both `DEFAULT_SYSTEM` and the per-turn
`system_prompt(lang)` used by the server.

After (`conversational_postfix/20261118-094800/report.md`):

| lang | reply | verdict |
|---|---|---|
| hi | feminine form used | PASS (automated) |
| pa | «…ਮੈਂ ਤੁਹਾਡੀ ਕਿਵੇਂ ਮਦਦ **ਕਰ ਸਕਦੀ** ਹਾਂ?» | PASS (automated) |
| mr | unmarked | PASS (automated) |

### Defect: the mixed-language rule covered only Hindi and Gujarati

The prompt promised code-switching only for "Hinglish / Gujlish", so other
languages translated the caller's English word instead of keeping it. The rule
now covers any Indian language. Assamese dropped "order" in the pre-fix run;
after the change it keeps it.

A second, measurement-side defect was found and fixed here: the audit's
term-matcher used exact spelling, so it scored Assamese `অর্ডাৰৰ` ("order's") as
lost. It now accepts a token within 40 % edit distance. Re-scoring the stored
replies changed exactly one verdict (as: lost → kept) and no others.

## Current automated verdict (no human input)

`conversational_postfix/20261118-094800/report.md`, re-scored for code-switching:

| lang | gender | code-switch | repetition | script | length | verdict |
|---|---|---|---|---|---|---|
| hi | feminine (voice is female) | kept | varied | ok | ok | PASS (automated) |
| gu | N/A | kept | varied | ok | ok | PASS (automated) |
| mr | unmarked | kept | varied | ok | ok | PASS (automated) |
| bn | N/A | kept | varied | ok | ok | PASS (automated) |
| ta | N/A | kept | varied | ok | ok | PASS (automated) |
| te | N/A | kept | varied | ok | ok | PASS (automated) |
| kn | N/A | kept | varied | ok | ok | PASS (automated) |
| ml | N/A | kept | varied | ok | ok | PASS (automated) |
| pa | feminine (voice is female) | kept | varied | ok | ok | PASS (automated) |
| or | N/A | kept | varied | ok | ok | PASS (automated) |
| as | N/A | kept | varied | ok | ok | PASS (automated) |
| en | N/A | kept | varied | ok | ok | PASS (automated) |

N/A reasons are recorded per language in `audit_conversational.py`
(`NA_GENDER`): Gujarati, Bengali, Tamil, Telugu, Kannada, Malayalam, Odia,
Assamese and English do not mark the speaker's own gender in the first person.

Note on `unmarked` (mr): the model avoided a gendered verb rather than using the
feminine one. Acceptable, but it is not evidence that the rule was obeyed.

## What this does NOT establish

* **MOS, naturalness, prosody, pronunciation** — NOT TESTED. No listener has
  rated anything; 0 responses exist.
* **Real-caller accuracy** — every audio measurement in this repository is
  synthesised, which flatters the recogniser.
* **Microphone, phone, telephony acoustics** — NOT TESTED by this audit.
* The new prompt takes effect when the server next starts; nothing was
  restarted here.

## Recommended next

1. Run the 240-slot human dataset collection (needs native speakers + consent) —
   this is the only thing that can lift MOS from NOT TESTED.
2. Re-run `eval/speak_check.py` to confirm the six known pronunciation
   candidates against native ears (Malayalam എന്റെ, Assamese mapping).
3. Export a dedicated Assamese ASR model to remove the Bengali alias confound.
