# IndicVoice — does the voice speak? (local measured check)

Run: `speak_check_20261118-100912` · generated 2026-11-18 10:09:20 · 9 renders (3 takes × 1 languages × 3 corpus sentences) · CPU-only, no cloud inference, no LLM, no playback on this machine.

**Headline: 9/9 renders passed every gate.** Per-language status below; human listening and MOS are NOT TESTED.

## What was measured

Each corpus sentence was rendered through the production playback path (`TTSEngine.render_sentence`, humanised — the same audio the server pushes to the speaker), saved as a mono PCM16 wav, then per render:

* objective signal health of the saved wav (duration, RMS/peak, clipping, voiced fraction, voice-band 100–4000 Hz energy share, spectral centroid);
* round-trip through the local production recogniser, CER/WER vs the reference;
* script check on the transcript.

## Why repeats

The voice is **non-deterministic**: rendering the same sentence twice produces different audio (verified — all 12 sampled wav hashes differed between two runs of this check). Word-level results move with it: one Hindi render recovered `मेरा पता दिल्ली में है` exactly, another lost the first word (`म पता दिल्ली में है`, CER 0.167). A single render per sentence therefore cannot support a claim about the voice, so every sentence is rendered multiple times and the distribution is reported, including the worst take.

## Two CER/WER columns, and why

* `cer` / `wer` — exactly what `src.evaluate` computes, comparable with earlier eval runs. Its `normalise` keeps U+0964 (danda) because that codepoint sits inside the Devanagari block it preserves, so a *perfect* Hindi transcript still scores about 1/len ≈ 0.04. That is a scoring artifact, not speech error.
* `cer_clean` / `wer_clean` — punctuation, symbols and zero-width characters removed by Unicode category before scoring (zero-width joiners otherwise split Telugu words). **The gates use this column.** The production harness was not modified.
* `cer_itn` (English only) — clean CER after expanding whisper's digits back to words (`1-2-3` → `one two three`). Diagnostic only, never used by a gate.

## Gates (engineering thresholds chosen for this check)

```json
{
  "min_duration_s": 0.4,
  "min_rms_dbfs": -35.0,
  "min_voiced_frac": 0.3,
  "max_clip_frac": 0.002,
  "min_voice_band_ratio": 0.7,
  "max_cer_clean": 0.15,
  "max_wer_clean": 0.3
}
```

Severity mapping: **FAIL** = a render is not audible speech (duration, level, voiced fraction, clipping or voice-band gate). **PARTIAL** = every render is audible, but at least one loses/alters words or answers in the wrong script. **PASS (automated)** = every render audible, intelligible and in the right script.

**Human listening and MOS: NOT TESTED.** Nobody listened to these clips as part of this run; the wavs are packaged so that listening can happen.

## Gate calibration (measured corrections, earlier runs preserved)

* An earlier run gated on the 300–3400 Hz telephone band and reported kn/ml FAIL. Sub-band measurement of those wavs: kn_01 52.6% of energy in 100–300 Hz, 47.0% in 300–3400 Hz, 0.5% above 3400 Hz (f0 ≈ 268 Hz); ml_03 57.7% / 41.3% / 1.0% (f0 ≈ 226 Hz). The 300 Hz cut discarded the fundamental of those voices. The gate now uses 100–4000 Hz coverage; the telephone-band share stays as a diagnostic column.
* High-frequency energy is **not** gated. Frame analysis showed the HF bursts are brief fricatives (en_03 `My address is in Delhi`: 12 of 94 frames HF-dominant, clustered on /s/) and the humanizer's room tone during silence (hi_01: 21 HF-dominant frames, none voiced). A clip-level HF share cannot distinguish hiss from normal speech, so `hf_share` and `hf_dominant_voiced_frac` are diagnostics only. **Objective hiss/artifact detection: NOT TESTED** — it requires listening.

## Per-language result

| lang | renders | TTS | ASR | CER raw | CER clean | worst CER clean | WER clean | clean renders | word-miss renders | mean s | render RTF | audible | status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| as | 9 | tiny | indic | 0.055 | 0.014 | 0.043 | 0.056 | 9/9 (100%) | 0 | 2.29 | 0.15 | yes | PASS (automated) |

## Per-sentence detail (every take)

### as — PASS (automated)

* sentence 1: মোৰ অৰ্ডাৰ নম্বৰ এক দুই তিনি।
  * clean takes 3/3, CER clean mean 0.043, max 0.043
  * `audio/as_01_r1.wav` — PASS (automated); CER raw 0.083 / clean 0.043, WER clean 0.167; 2.59s, RMS -23.48 dBFS, peak -5.41 dBFS, clipped 0.000%, voiced 66%, voice-band 99.6%, telephone-band 64%, hf_share 0.56% (diag), centroid 583 Hz; render 371 ms, ASR 222 ms
    * heard: মোৰ অর্ডাৰ নম্বৰ এক দুই তিনি
  * `audio/as_01_r2.wav` — PASS (automated); CER raw 0.083 / clean 0.043, WER clean 0.167; 2.61s, RMS -23.48 dBFS, peak -5.63 dBFS, clipped 0.000%, voiced 65%, voice-band 99.5%, telephone-band 65%, hf_share 0.59% (diag), centroid 601 Hz; render 432 ms, ASR 270 ms
    * heard: মোৰ অর্ডাৰ নম্বৰ এক দুই তিনি
  * `audio/as_01_r3.wav` — PASS (automated); CER raw 0.083 / clean 0.043, WER clean 0.167; 2.54s, RMS -23.49 dBFS, peak -6.12 dBFS, clipped 0.000%, voiced 65%, voice-band 99.6%, telephone-band 66%, hf_share 0.46% (diag), centroid 627 Hz; render 383 ms, ASR 241 ms
    * heard: মোৰ অর্ডাৰ নম্বৰ এক দুই তিনি
* sentence 2: কাইলৈ সন্ধিয়াৰ ভিতৰত ডেলিভাৰী হ'ব।
  * clean takes 3/3, CER clean mean 0.000, max 0.000
  * `audio/as_02_r1.wav` — PASS (automated); CER raw 0.033 / clean 0.000, WER clean 0.000; 2.40s, RMS -23.52 dBFS, peak -2.94 dBFS, clipped 0.000%, voiced 76%, voice-band 98.5%, telephone-band 67%, hf_share 0.93% (diag), centroid 628 Hz; render 348 ms, ASR 243 ms
    * heard: কাইলৈ সন্ধিয়াৰ ভিতৰত ডেলিভাৰী হ ব
    * note: raw-harness error is punctuation only (danda counted as a character)
  * `audio/as_02_r2.wav` — PASS (automated); CER raw 0.033 / clean 0.000, WER clean 0.000; 2.33s, RMS -23.53 dBFS, peak -4.13 dBFS, clipped 0.000%, voiced 75%, voice-band 99.0%, telephone-band 66%, hf_share 0.79% (diag), centroid 643 Hz; render 328 ms, ASR 386 ms
    * heard: কাইলৈ সন্ধিয়াৰ ভিতৰত ডেলিভাৰী হ ব
    * note: raw-harness error is punctuation only (danda counted as a character)
  * `audio/as_02_r3.wav` — PASS (automated); CER raw 0.033 / clean 0.000, WER clean 0.000; 2.35s, RMS -23.52 dBFS, peak -5.48 dBFS, clipped 0.000%, voiced 75%, voice-band 98.8%, telephone-band 70%, hf_share 0.98% (diag), centroid 672 Hz; render 348 ms, ASR 243 ms
    * heard: কাইলৈ সন্ধিয়াৰ ভিতৰত ডেলিভাৰী হ ব
    * note: raw-harness error is punctuation only (danda counted as a character)
* sentence 3: মোৰ ঠিকনা গুৱাহাটীত আছে।
  * clean takes 3/3, CER clean mean 0.000, max 0.000
  * `audio/as_03_r1.wav` — PASS (automated); CER raw 0.048 / clean 0.000, WER clean 0.000; 1.95s, RMS -23.62 dBFS, peak -7.14 dBFS, clipped 0.000%, voiced 67%, voice-band 96.4%, telephone-band 55%, hf_share 3.46% (diag), centroid 755 Hz; render 293 ms, ASR 206 ms
    * heard: মোৰ ঠিকনা গুৱাহাটীত আছে
    * note: raw-harness error is punctuation only (danda counted as a character)
  * `audio/as_03_r2.wav` — PASS (automated); CER raw 0.048 / clean 0.000, WER clean 0.000; 1.91s, RMS -23.63 dBFS, peak -4.98 dBFS, clipped 0.000%, voiced 67%, voice-band 96.9%, telephone-band 61%, hf_share 2.46% (diag), centroid 691 Hz; render 272 ms, ASR 200 ms
    * heard: মোৰ ঠিকনা গুৱাহাটীত আছে
    * note: raw-harness error is punctuation only (danda counted as a character)
  * `audio/as_03_r3.wav` — PASS (automated); CER raw 0.048 / clean 0.000, WER clean 0.000; 1.95s, RMS -23.62 dBFS, peak -6.34 dBFS, clipped 0.000%, voiced 66%, voice-band 90.9%, telephone-band 58%, hf_share 8.81% (diag), centroid 1232 Hz; render 277 ms, ASR 208 ms
    * heard: মোৰ ঠিকনা গুৱাহাটীত আছে
    * note: raw-harness error is punctuation only (danda counted as a character)

## Caveats (read before quoting any number)

* Audio is **TTS-synthesised**, not real recordings. The round-trip shares the synthesis domain and a clean channel, so it flatters the recogniser. These CER/WER values are an intelligibility proxy for the voice, not production ASR accuracy, and they add 0 to the real-recording count.
* Assamese is decoded with the Bengali Conformer (no Assamese ONNX export exists), so Bengali orthography (`ৰ`→`র`, `ৱ`→`ব`) scores as errors. The Assamese round-trip is confounded: it cannot separate a TTS pronunciation problem from a recogniser orthography problem. Native listening is the only way to resolve it.
* A low CER proves the recogniser recovered the words; it does not prove naturalness, prosody, or absence of artefacts. Only human listening can judge those: NOT TESTED.
* One speaker (sid 0), default speed, 3 corpus sentences per language. This is a 108-render sample of a fixed corpus, not a population estimate for arbitrary text.
* Run-to-run thermal variance on this 15 W laptop affects the millisecond columns, not the audio. The renders themselves vary because synthesis is stochastic.
