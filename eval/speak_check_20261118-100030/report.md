# IndicVoice — does the voice speak? (local measured check)

Run: `speak_check_20261118-100030` · generated 2026-11-18 10:00:59 · 9 renders (3 takes × 1 languages × 3 corpus sentences) · CPU-only, no cloud inference, no LLM, no playback on this machine.

**Headline: 5/9 renders passed every gate.** Per-language status below; human listening and MOS are NOT TESTED.

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
| ml | 9 | tiny | indic | 0.035 | 0.035 | 0.087 | 0.167 | 5/9 (56%) | 4 | 2.23 | 0.21 | yes | PARTIAL |

## Per-sentence detail (every take)

### ml — PARTIAL

* sentence 1: എന്റെ ഓർഡർ നമ്പർ ഒന്ന് രണ്ട് മൂന്ന്.
  * clean takes 3/3, CER clean mean 0.000, max 0.000
  * `audio/ml_01_r1.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.49s, RMS -23.5 dBFS, peak -7.4 dBFS, clipped 0.000%, voiced 75%, voice-band 99.9%, telephone-band 53%, hf_share 0.24% (diag), centroid 483 Hz; render 484 ms, ASR 1694 ms
    * heard: എന്റെ ഓർഡർ നമ്പർ ഒന്ന് രണ്ട് മൂന്ന്
  * `audio/ml_01_r2.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.51s, RMS -23.5 dBFS, peak -9.46 dBFS, clipped 0.000%, voiced 76%, voice-band 99.9%, telephone-band 66%, hf_share 0.28% (diag), centroid 516 Hz; render 391 ms, ASR 3209 ms
    * heard: എന്റെ ഓർഡർ നമ്പർ ഒന്ന് രണ്ട് മൂന്ന്
  * `audio/ml_01_r3.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.44s, RMS -23.51 dBFS, peak -8.6 dBFS, clipped 0.000%, voiced 78%, voice-band 99.9%, telephone-band 56%, hf_share 0.28% (diag), centroid 486 Hz; render 834 ms, ASR 1965 ms
    * heard: എന്റെ ഓർഡർ നമ്പർ ഒന്ന് രണ്ട് മൂന്ന്
* sentence 2: നാളെ വൈകുന്നേരത്തിനുള്ളിൽ ഡെലിവറി ആകും.
  * clean takes 2/3, CER clean mean 0.019, max 0.057
  * `audio/ml_02_r1.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.64s, RMS -23.48 dBFS, peak -7.57 dBFS, clipped 0.000%, voiced 76%, voice-band 99.8%, telephone-band 61%, hf_share 0.41% (diag), centroid 645 Hz; render 360 ms, ASR 2029 ms
    * heard: നാളെ വൈകുന്നേരത്തിനുള്ളിൽ ഡെലിവറി ആകും
  * `audio/ml_02_r2.wav` — PARTIAL; CER raw 0.057 / clean 0.057, WER clean 0.500; 2.58s, RMS -23.49 dBFS, peak -9.05 dBFS, clipped 0.000%, voiced 77%, voice-band 99.8%, telephone-band 54%, hf_share 0.47% (diag), centroid 560 Hz; render 498 ms, ASR 2110 ms
    * heard: നാളെ വൈകുന്നേരത്തിനുള്ളിൽ ഡെലിവറിിയകും
    * note: words lost or altered in this render
  * `audio/ml_02_r3.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.60s, RMS -23.48 dBFS, peak -6.51 dBFS, clipped 0.000%, voiced 75%, voice-band 99.8%, telephone-band 63%, hf_share 0.47% (diag), centroid 631 Hz; render 602 ms, ASR 3667 ms
    * heard: നാളെ വൈകുന്നേരത്തിനുള്ളിൽ ഡെലിവറി ആകും
* sentence 3: എന്റെ വിലാസം കൊച്ചിയിലാണ്.
  * clean takes 0/3, CER clean mean 0.087, max 0.087
  * `audio/ml_03_r1.wav` — PARTIAL; CER raw 0.087 / clean 0.087, WER clean 0.333; 1.60s, RMS -23.74 dBFS, peak -8.51 dBFS, clipped 0.000%, voiced 77%, voice-band 99.4%, telephone-band 51%, hf_share 0.82% (diag), centroid 553 Hz; render 348 ms, ASR 1446 ms
    * heard: എറെ വിലാസം കൊച്ചിയിലാണ്
    * note: words lost or altered in this render
  * `audio/ml_03_r2.wav` — PARTIAL; CER raw 0.087 / clean 0.087, WER clean 0.333; 1.56s, RMS -23.76 dBFS, peak -8.33 dBFS, clipped 0.000%, voiced 76%, voice-band 99.0%, telephone-band 47%, hf_share 1.18% (diag), centroid 562 Hz; render 299 ms, ASR 1494 ms
    * heard: എറെ വിലാസം കൊച്ചിയിലാണ്
    * note: words lost or altered in this render
  * `audio/ml_03_r3.wav` — PARTIAL; CER raw 0.087 / clean 0.087, WER clean 0.333; 1.61s, RMS -23.74 dBFS, peak -9.46 dBFS, clipped 0.000%, voiced 78%, voice-band 99.5%, telephone-band 53%, hf_share 0.78% (diag), centroid 524 Hz; render 444 ms, ASR 2709 ms
    * heard: എറെ വിലാസം കൊച്ചിയിലാണ്
    * note: words lost or altered in this render

## Caveats (read before quoting any number)

* Audio is **TTS-synthesised**, not real recordings. The round-trip shares the synthesis domain and a clean channel, so it flatters the recogniser. These CER/WER values are an intelligibility proxy for the voice, not production ASR accuracy, and they add 0 to the real-recording count.
* Assamese is decoded with the Bengali Conformer (no Assamese ONNX export exists), so Bengali orthography (`ৰ`→`র`, `ৱ`→`ব`) scores as errors. The Assamese round-trip is confounded: it cannot separate a TTS pronunciation problem from a recogniser orthography problem. Native listening is the only way to resolve it.
* A low CER proves the recogniser recovered the words; it does not prove naturalness, prosody, or absence of artefacts. Only human listening can judge those: NOT TESTED.
* One speaker (sid 0), default speed, 3 corpus sentences per language. This is a 108-render sample of a fixed corpus, not a population estimate for arbitrary text.
* Run-to-run thermal variance on this 15 W laptop affects the millisecond columns, not the audio. The renders themselves vary because synthesis is stochastic.
