# IndicVoice Evaluation Dataset V1

Target: **240 real human utterances — 20 per language × 12 languages**
(hi, bn, ta, te, kn, ml, mr, gu, pa, or, as, en).

Status today: **0 / 240 collected.** Every slot in
`evaluation/dataset_manifest.jsonl` (moved to the V2 canonical location;
schema: `evaluation/dataset_schema.json`) is `NOT_COLLECTED`. The existing
`eval_data/*.wav` clips are TTS-synthesized starters and must **never** be
counted toward this dataset or reported as real-recording results.

Full recording protocol: `evaluation/recording_guide.md`. Ingestion is
automated by `benchmarks/ingest_dataset.py` (validation, optional format
conversion with original preservation, duplicate/clipping/silence detection,
manifest update); status reporting by `benchmarks/dataset_report.py`.

## Privacy and consent (non-negotiable)

- Record only volunteers who have given explicit, recorded permission
  (`consent: true` in the manifest). Note the consent form/version in `notes`.
- Use pseudonymous `speaker_id` values (e.g. `spk_hi_01`). Never store real
  names, phone numbers, or other PII in the manifest or reference texts.
- **Never use actual customer calls** as evaluation data without documented
  authorization and privacy safeguards.
- Reference texts must not contain real personal data; if a speaker says a
  real phone number, replace it with a fictitious one in the reference and
  note the substitution, or re-record.
- Audio files stay local. `evaluation/dataset/audio/` should be git-ignored
  or shared only through an access-controlled channel.

## Diversity targets (per language)

| Axis | Target |
|---|---|
| Speakers | ≥ 5 distinct speakers (manifest `target_speaker_group` 1–5 spreads the 20 slots) |
| Gender / age | Mixed where possible; note in `notes` if relevant |
| Accent | Include at least one regional-accent speaker |
| Noise | 14 clean, 3 office babble, 3 street/traffic (slots 15–20) |
| Device | Mix of phone mic and laptop/headset mic |
| Style | Natural conversational speech, not read-aloud only; `pause_heavy` slots must contain real 0.3–0.8 s pauses |

The `domain` / `prompt_hint` fields guide content: conversation, questions,
commands, digits/currency, dates/times, phone/OTP, names/places, code-mixed
speech, pause-heavy speech, and read speech. Prompts are guidance — the
speaker should say something natural in that category, in their own words.

## Recording procedure

1. Record at **16 kHz, mono, PCM16 WAV** (phone apps often record 44.1/48 kHz
   stereo — convert, e.g. with ffmpeg:
   `ffmpeg -i in.m4a -ar 16000 -ac 1 -sample_fmt s16 out.wav`).
2. One utterance per file, 0.5–60 s, with ~0.3 s of leading/trailing silence.
3. For noise slots, record in the actual environment (or play calibrated
   office/street noise at ~55–65 dB while speaking); note the condition.
4. Ingest with the tool (validates, converts if needed, fills the slot):
   ```bash
   .venv313/Scripts/python.exe benchmarks/ingest_dataset.py \
     --audio rec.wav --lang hi --speaker spk_hi_01 \
     --reference "मेरा ऑर्डर कहाँ तक पहुँचा?" \
     --noise clean --device phone --consent --convert
   ```
   Manual alternative: save to `evaluation/dataset/audio/<lang>/<id>.wav`
   exactly as the manifest's `audio_path` specifies.
5. Transcribe **verbatim** in the native script (English in Latin script),
   including code-mixed English words. Do not normalize numbers or punctuation
   beyond standard orthography — the metrics pipeline normalizes separately.
   **Never use an ASR hypothesis as the reference.** A second native/fluent
   speaker verifies it, then record the assertion:
   `python benchmarks/ingest_dataset.py verify --id hi_001 --verifier spk_hi_02`.
6. The ingest tool updates the manifest entry (`status: "COLLECTED"`,
   reference, speaker, consent, device, duration, date, script, sample rate,
   `transcript_verified: false` until step 5, audio SHA-256).

## Schema (one JSON object per line)

| Field | Type | Rules |
|---|---|---|
| `id` | string | `<lang>_<NNN>`, unique |
| `lang` | string | one of the 12 language codes |
| `audio_path` | string | repo-relative path to the WAV |
| `status` | string | `NOT_COLLECTED` / `COLLECTED` / `REJECTED` |
| `reference_text` | string\|null | verbatim transcript; null until collected |
| `speaker_id` | string\|null | pseudonymous; required when collected |
| `consent` | bool\|null | must be `true` when collected |
| `noise_condition` | string | `clean` / `office` / `street` |
| `device` | string\|null | `phone` / `laptop` / `headset` / `other` when collected |
| `duration_s` | number\|null | must match the WAV header (±0.1 s) |
| `domain`, `prompt_hint` | string | content guidance (pre-filled) |
| `target_speaker_group` | int | 1–5, spreads slots across speakers |
| `collected_at` | string\|null | ISO date when collected |
| `notes` | string\|null | required for `REJECTED` entries |
| `script` | string\|null | writing system of the reference (V2) |
| `sample_rate` | int\|null | 16000 for canonical audio (V2) |
| `environment` | string\|null | free-text recording environment (V2) |
| `transcript_verified` | bool\|null | human verification assertion (V2) |
| `transcript_verified_by` | string\|null | pseudonymous verifier (V2) |
| `audio_sha256` | string\|null | canonical PCM hash, duplicate detection (V2) |

## Validation

```bash
.venv313/Scripts/python.exe benchmarks/validate_dataset.py
.venv313/Scripts/python.exe benchmarks/validate_dataset.py --require-complete
.venv313/Scripts/python.exe benchmarks/validate_dataset.py --out benchmarks/results/production_v1/dataset_validation.json
```

The validator checks schema, WAV format (16 kHz mono PCM16), duration,
consent, and reference presence for every `COLLECTED` entry, and reports
per-language completeness. Exit codes: 0 = valid, 1 = invalid entries,
2 = incomplete under `--require-complete`. It never creates or modifies
audio or reference texts.

## Completion gate (Hardening V1)

The dataset milestone is met only when `--require-complete` exits 0:
240 collected, all valid, ≥ 5 speakers per language. Until then, any
ASR accuracy number measured on `eval_data/` must be labeled
**synthetic-corpus**, not real-world.