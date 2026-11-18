# IndicVoice — does the voice speak? (local measured check)

Run: `speak_check_20261117-173007` · generated 2026-11-17 17:30:14 · 1 renders (1 takes × 1 languages × 3 corpus sentences) · CPU-only, no cloud inference, no LLM, no playback on this machine.

**Headline: 1/1 renders passed every gate.** Per-language status below; human listening and MOS are NOT TESTED.

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
| mr | 1 | tiny | indic | 0.000 | 0.000 | 0.000 | 0.000 | 1/1 (100%) | 0 | 3.43 | 0.14 | yes | PASS (automated) |

## Per-sentence detail (every take)

### mr — PASS (automated)

* sentence 1: माझा ऑर्डर नंबर एक दोन तीन आहे.
  * clean takes 1/1, CER clean mean 0.000, max 0.000
  * `audio/mr_01_r1.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 3.43s, RMS -23.39 dBFS, peak -6.4 dBFS, clipped 0.000%, voiced 61%, voice-band 98.4%, telephone-band 79%, hf_share 1.90% (diag), centroid 736 Hz; render 495 ms, ASR 2299 ms
    * heard: माझा ऑर्डर नंबर एक दोन तीन आहे

## Caveats (read before quoting any number)

* Audio is **TTS-synthesised**, not real recordings. The round-trip shares the synthesis domain and a clean channel, so it flatters the recogniser. These CER/WER values are an intelligibility proxy for the voice, not production ASR accuracy, and they add 0 to the real-recording count.
* Assamese is decoded with the Bengali Conformer (no Assamese ONNX export exists), so Bengali orthography (`ৰ`→`র`, `ৱ`→`ব`) scores as errors. The Assamese round-trip is confounded: it cannot separate a TTS pronunciation problem from a recogniser orthography problem. Native listening is the only way to resolve it.
* A low CER proves the recogniser recovered the words; it does not prove naturalness, prosody, or absence of artefacts. Only human listening can judge those: NOT TESTED.
* One speaker (sid 0), default speed, 3 corpus sentences per language. This is a 108-render sample of a fixed corpus, not a population estimate for arbitrary text.
* Run-to-run thermal variance on this 15 W laptop affects the millisecond columns, not the audio. The renders themselves vary because synthesis is stochastic.
