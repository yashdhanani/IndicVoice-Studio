# IndicVoice evaluation corpus — recording guide (V2)

Goal: **240 genuine human utterances — 20 per language × 12 languages**
(hi, gu, mr, bn, ta, te, kn, ml, pa, or, as, en), diverse enough to support
real-world CER/WER claims. This guide is the protocol; the tooling enforces it.

**Hard rules**
- Genuine human speech only. TTS audio, voice conversion, or generated
  placeholders are never accepted and never counted.
- Informed, recorded consent before any recording (`--consent` asserts it).
- Pseudonymous speaker IDs only (`spk_<lang>_<NN>`). No names, contacts, or
  other PII in audio references, metadata, or filenames.
- No customer calls without documented authorization and privacy safeguards.
- Reference transcripts are human-written and human-verified. **An ASR
  hypothesis is never its own reference.**
- Recordings stay local: `evaluation/dataset/audio/` and
  `evaluation/dataset/originals/` are git-ignored. No silent uploads.

## Canonical audio format

| Property | Value |
|---|---|
| Container | WAV (PCM) |
| Channels | 1 (mono) |
| Sample rate | 16,000 Hz |
| Bit depth | 16-bit signed |
| Duration | 0.5–60 s per utterance |
| Boundaries | ~0.3 s leading/trailing silence; one utterance per file |

Record at the device's native rate (phones: 44.1/48 kHz) and let the ingest
tool convert (`--convert`); the untouched original is preserved under
`evaluation/dataset/originals/`. Manual alternative:
`ffmpeg -i in.m4a -ar 16000 -ac 1 -sample_fmt s16 out.wav`.

## Per-language content plan (20 slots)

Slots are pre-defined in `evaluation/dataset_manifest.jsonl` with `domain`
and `prompt_hint`. Prompts are guidance — speakers say something natural in
that category, in their own words. Each language must cover:

1. Short conversational questions (greetings, status checks)
2. Longer natural utterances (multi-clause, 8–20 s)
3. Natural pauses (real 0.3–0.8 s hesitations, not edited silence)
4. Questions with numbers (order IDs, amounts, dates, times)
5. Names and places (common local names, cities — fictitious if personal)
6. English loanwords ("WhatsApp", "OTP", "delivery", "booking")
7. Mixed-language expressions (natural code-switching, verbatim reference)
8. Questions and statements (rising vs flat intonation)
9. Low-volume speech (quiet but natural; not whispered acting)
10. Challenging natural speech (fast rate, regional accent, disfluencies)

Noise plan: slots 1–14 clean, 15–17 office babble, 18–20 street/traffic.
Record in the actual environment where possible; otherwise play calibrated
noise at ~55–65 dB and note it in `environment`.

## Speaker diversity

- **≥5 distinct speakers per language** (`target_speaker_group` 1–5 spreads
  the 20 slots: each group records ~4 utterances).
- Mix gender/age where feasible; include at least one regional-accent
  speaker per language; mix phone mic and laptop/headset mic.
- One person may coordinate, but may not be the only voice.

## Consent procedure

1. Explain: purpose (speech-recognition evaluation), what is stored
   (audio + transcript + pseudonymous metadata), where (local, access-
   controlled), retention, and the right to withdraw before publication.
2. Record the speaker stating consent (separate file, kept with originals,
   never committed), or a signed form scanned to the same location.
3. Note the consent form/version in the entry's `notes` if used.
4. Withdrawal: set the slot to `REJECTED` with notes, delete the audio and
   original, re-run the validator.

## Recording session procedure

1. Quiet check: listen to 5 s of room tone; note the environment.
2. Record one utterance per file at natural volume; also capture the
   low-volume slot at the speaker's quiet-but-normal level.
3. Watch levels: peaks below full scale (the ingest tool rejects >1%
   clipped samples); avoid phone AGC pumping where possible.
4. Write the verbatim reference immediately, in the native script
   (English in Latin script), including code-mixed words, in the speaker's
   actual wording — not the prompt wording.
5. Ingest:
   ```bash
   .venv313/Scripts/python.exe benchmarks/ingest_dataset.py \
     --audio rec.wav --lang hi --speaker spk_hi_01 \
     --reference "<verbatim text>" --noise clean --device phone \
     --consent --convert --environment "quiet room, laptop mic"
   ```
   The tool checks: missing/empty/corrupted audio, sample rate, channels,
   clipping, silence, duration bounds, duplicate PCM (SHA-256), missing
   reference, invalid language, metadata enums, consent completeness.
   Rejections print every reason; nothing is written on rejection.
   Use `--dry-run` to pre-check without writing.
6. Verification: a second native/fluent speaker listens and checks the
   reference, then:
   ```bash
   .venv313/Scripts/python.exe benchmarks/ingest_dataset.py verify \
     --id hi_001 --verifier spk_hi_02
   ```

## Status and gates

```bash
.venv313/Scripts/python.exe benchmarks/dataset_report.py \
  --out benchmarks/results/realworld_v2/dataset_report_v2.json
.venv313/Scripts/python.exe benchmarks/validate_dataset.py --require-complete
```

- Report **actual counts** (e.g. 120/240), never plans as progress.
- The completeness gate passes only at 240 valid COLLECTED entries.
- Until then, every accuracy number from `eval_data/` stays labeled
  **synthetic-corpus**.