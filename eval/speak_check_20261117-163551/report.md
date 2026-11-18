# IndicVoice — does the voice speak? (local measured check)

Run: `speak_check_20261117-163551` · generated 2026-11-17 16:39:48 · 108 renders (3 takes × 12 languages × 3 corpus sentences) · CPU-only, no cloud inference, no LLM, no playback on this machine.

**Headline: 89/108 renders passed every gate.** Per-language status below; human listening and MOS are NOT TESTED.

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
| hi | 9 | tiny | indic | 0.149 | 0.106 | 0.955 | 0.111 | 8/9 (89%) | 1 | 2.16 | 0.17 | yes | PARTIAL |
| gu | 9 | tiny | indic | 0.021 | 0.021 | 0.111 | 0.093 | 8/9 (89%) | 1 | 2.63 | 0.19 | yes | PARTIAL |
| mr | 9 | tiny | indic | 0.000 | 0.000 | 0.000 | 0.000 | 9/9 (100%) | 0 | 2.88 | 0.16 | yes | PASS (automated) |
| bn | 9 | tiny | indic | 0.044 | 0.000 | 0.000 | 0.000 | 9/9 (100%) | 0 | 2.15 | 0.17 | yes | PASS (automated) |
| ta | 9 | tiny | indic | 0.004 | 0.004 | 0.034 | 0.019 | 9/9 (100%) | 0 | 2.21 | 0.17 | yes | PASS (automated) |
| te | 9 | tiny | indic | 0.000 | 0.000 | 0.000 | 0.000 | 9/9 (100%) | 0 | 2.59 | 0.14 | yes | PASS (automated) |
| kn | 9 | tiny | indic | 0.000 | 0.000 | 0.000 | 0.000 | 9/9 (100%) | 0 | 2.88 | 0.14 | yes | PASS (automated) |
| ml | 9 | tiny | indic | 0.035 | 0.035 | 0.087 | 0.167 | 5/9 (56%) | 4 | 2.22 | 0.18 | yes | PARTIAL |
| pa | 9 | tiny | indic | 0.059 | 0.018 | 0.074 | 0.066 | 9/9 (100%) | 0 | 2.72 | 0.13 | yes | PASS (automated) |
| or | 9 | tiny | indic | 0.068 | 0.027 | 0.048 | 0.139 | 8/9 (89%) | 1 | 2.64 | 0.18 | yes | PARTIAL |
| as | 9 | tiny | indic | 0.288 | 0.258 | 0.300 | 0.806 | 0/9 (0%) | 9 | 2.29 | 0.18 | yes | PARTIAL |
| en | 9 | tiny | whisper | 0.141 | 0.141 | 0.423 | 0.143 | 6/9 (67%) | 3 | 2.39 | 0.17 | yes | PARTIAL |

## Per-sentence detail (every take)

### hi — PARTIAL

* sentence 1: मेरा ऑर्डर नंबर एक दो तीन है।
  * clean takes 2/3, CER clean mean 0.318, max 0.955
  * `audio/hi_01_r1.wav` — PARTIAL; CER raw 0.957 / clean 0.955, WER clean 1.000; 2.45s, RMS -23.51 dBFS, peak -8.12 dBFS, clipped 0.000%, voiced 67%, voice-band 99.6%, telephone-band 80%, hf_share 0.53% (diag), centroid 651 Hz; render 327 ms, ASR 341 ms
    * heard: म
    * note: words lost or altered in this render
  * `audio/hi_01_r2.wav` — PASS (automated); CER raw 0.043 / clean 0.000, WER clean 0.000; 2.47s, RMS -23.5 dBFS, peak -7.07 dBFS, clipped 0.000%, voiced 68%, voice-band 99.7%, telephone-band 80%, hf_share 0.45% (diag), centroid 659 Hz; render 324 ms, ASR 267 ms
    * heard: मेरा ऑर्डर नंबर एक दो तीन है
    * note: raw-harness error is punctuation only (danda counted as a character)
  * `audio/hi_01_r3.wav` — PASS (automated); CER raw 0.043 / clean 0.000, WER clean 0.000; 2.40s, RMS -23.52 dBFS, peak -6.42 dBFS, clipped 0.000%, voiced 66%, voice-band 99.8%, telephone-band 84%, hf_share 0.34% (diag), centroid 631 Hz; render 379 ms, ASR 303 ms
    * heard: मेरा ऑर्डर नंबर एक दो तीन है
    * note: raw-harness error is punctuation only (danda counted as a character)
* sentence 2: कल शाम तक डिलीवरी हो जाएगी।
  * clean takes 3/3, CER clean mean 0.000, max 0.000
  * `audio/hi_02_r1.wav` — PASS (automated); CER raw 0.045 / clean 0.000, WER clean 0.000; 2.25s, RMS -23.54 dBFS, peak -5.11 dBFS, clipped 0.000%, voiced 65%, voice-band 99.1%, telephone-band 90%, hf_share 2.11% (diag), centroid 835 Hz; render 337 ms, ASR 398 ms
    * heard: कल शाम तक डिलीवरी हो जाएगी
    * note: raw-harness error is punctuation only (danda counted as a character)
  * `audio/hi_02_r2.wav` — PASS (automated); CER raw 0.045 / clean 0.000, WER clean 0.000; 2.19s, RMS -23.56 dBFS, peak -6.69 dBFS, clipped 0.000%, voiced 62%, voice-band 99.4%, telephone-band 88%, hf_share 1.36% (diag), centroid 737 Hz; render 310 ms, ASR 185 ms
    * heard: कल शाम तक डिलीवरी हो जाएगी
    * note: raw-harness error is punctuation only (danda counted as a character)
  * `audio/hi_02_r3.wav` — PASS (automated); CER raw 0.045 / clean 0.000, WER clean 0.000; 2.21s, RMS -23.55 dBFS, peak -6.21 dBFS, clipped 0.000%, voiced 68%, voice-band 99.1%, telephone-band 86%, hf_share 1.60% (diag), centroid 781 Hz; render 440 ms, ASR 344 ms
    * heard: कल शाम तक डिलीवरी हो जाएगी
    * note: raw-harness error is punctuation only (danda counted as a character)
* sentence 3: मेरा पता दिल्ली में है।
  * clean takes 3/3, CER clean mean 0.000, max 0.000
  * `audio/hi_03_r1.wav` — PASS (automated); CER raw 0.053 / clean 0.000, WER clean 0.000; 1.84s, RMS -23.65 dBFS, peak -8.36 dBFS, clipped 0.000%, voiced 60%, voice-band 99.7%, telephone-band 76%, hf_share 0.48% (diag), centroid 596 Hz; render 398 ms, ASR 384 ms
    * heard: मेरा पता दिल्ली में है
    * note: raw-harness error is punctuation only (danda counted as a character)
  * `audio/hi_03_r2.wav` — PASS (automated); CER raw 0.053 / clean 0.000, WER clean 0.000; 1.80s, RMS -23.66 dBFS, peak -8.48 dBFS, clipped 0.000%, voiced 61%, voice-band 99.7%, telephone-band 75%, hf_share 0.40% (diag), centroid 596 Hz; render 351 ms, ASR 431 ms
    * heard: मेरा पता दिल्ली में है
    * note: raw-harness error is punctuation only (danda counted as a character)
  * `audio/hi_03_r3.wav` — PASS (automated); CER raw 0.053 / clean 0.000, WER clean 0.000; 1.84s, RMS -23.65 dBFS, peak -7.09 dBFS, clipped 0.000%, voiced 62%, voice-band 99.7%, telephone-band 79%, hf_share 0.40% (diag), centroid 618 Hz; render 401 ms, ASR 378 ms
    * heard: मेरा पता दिल्ली में है
    * note: raw-harness error is punctuation only (danda counted as a character)

### gu — PARTIAL

* sentence 1: મારો ઓર્ડર નંબર એક બે ત્રણ છે.
  * clean takes 3/3, CER clean mean 0.000, max 0.000
  * `audio/gu_01_r1.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 3.19s, RMS -23.41 dBFS, peak -5.32 dBFS, clipped 0.000%, voiced 57%, voice-band 99.5%, telephone-band 75%, hf_share 0.54% (diag), centroid 688 Hz; render 427 ms, ASR 1898 ms
    * heard: મારો ઓર્ડર નંબર એક બે ત્રણ છે
  * `audio/gu_01_r2.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 3.21s, RMS -23.41 dBFS, peak -4.53 dBFS, clipped 0.000%, voiced 56%, voice-band 99.5%, telephone-band 80%, hf_share 0.52% (diag), centroid 754 Hz; render 586 ms, ASR 2643 ms
    * heard: મારો ઓર્ડર નંબર એક બે ત્રણ છે
  * `audio/gu_01_r3.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 3.12s, RMS -23.41 dBFS, peak -5.61 dBFS, clipped 0.000%, voiced 55%, voice-band 99.6%, telephone-band 82%, hf_share 0.43% (diag), centroid 764 Hz; render 753 ms, ASR 1299 ms
    * heard: મારો ઓર્ડર નંબર એક બે ત્રણ છે
* sentence 2: કાલે સાંજ સુધીમાં ડિલિવરી થઈ જશે.
  * clean takes 2/3, CER clean mean 0.062, max 0.111
  * `audio/gu_02_r1.wav` — PASS (automated); CER raw 0.037 / clean 0.037, WER clean 0.167; 2.56s, RMS -23.49 dBFS, peak -4.06 dBFS, clipped 0.000%, voiced 80%, voice-band 97.7%, telephone-band 86%, hf_share 2.55% (diag), centroid 1014 Hz; render 391 ms, ASR 2123 ms
    * heard: કાલે સાંજ સુધીમાં ડિલીિવરી થઈ જશે
  * `audio/gu_02_r2.wav` — PARTIAL; CER raw 0.111 / clean 0.111, WER clean 0.500; 2.49s, RMS -23.5 dBFS, peak -5.93 dBFS, clipped 0.000%, voiced 81%, voice-band 97.6%, telephone-band 85%, hf_share 2.54% (diag), centroid 950 Hz; render 761 ms, ASR 1807 ms
    * heard: કાલે સાંજ સુધીમાંડીલીવરી થાઈ જશે
    * note: words lost or altered in this render
  * `audio/gu_02_r3.wav` — PASS (automated); CER raw 0.037 / clean 0.037, WER clean 0.167; 2.51s, RMS -23.5 dBFS, peak -4.15 dBFS, clipped 0.000%, voiced 78%, voice-band 97.8%, telephone-band 87%, hf_share 2.33% (diag), centroid 1011 Hz; render 439 ms, ASR 1546 ms
    * heard: કાલે સાંજ સુધીમાં ડિલીિવરી થઈ જશે
* sentence 3: મારું સરનામું અમદાવાદમાં છે.
  * clean takes 3/3, CER clean mean 0.000, max 0.000
  * `audio/gu_03_r1.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.23s, RMS -23.55 dBFS, peak -8.21 dBFS, clipped 0.000%, voiced 81%, voice-band 98.6%, telephone-band 79%, hf_share 1.62% (diag), centroid 833 Hz; render 405 ms, ASR 1603 ms
    * heard: મારું સરનામું અમદાવાદમાં છે
  * `audio/gu_03_r2.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.17s, RMS -23.56 dBFS, peak -7.71 dBFS, clipped 0.000%, voiced 82%, voice-band 98.6%, telephone-band 76%, hf_share 1.55% (diag), centroid 802 Hz; render 373 ms, ASR 1259 ms
    * heard: મારું સરનામું અમદાવાદમાં છે
  * `audio/gu_03_r3.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.23s, RMS -23.55 dBFS, peak -7.0 dBFS, clipped 0.000%, voiced 80%, voice-band 99.1%, telephone-band 82%, hf_share 1.01% (diag), centroid 836 Hz; render 370 ms, ASR 1155 ms
    * heard: મારું સરનામું અમદાવાદમાં છે

### mr — PASS (automated)

* sentence 1: माझा ऑर्डर नंबर एक दोन तीन आहे.
  * clean takes 3/3, CER clean mean 0.000, max 0.000
  * `audio/mr_01_r1.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 3.43s, RMS -23.39 dBFS, peak -6.72 dBFS, clipped 0.000%, voiced 61%, voice-band 98.8%, telephone-band 81%, hf_share 1.50% (diag), centroid 710 Hz; render 450 ms, ASR 1823 ms
    * heard: माझा ऑर्डर नंबर एक दोन तीन आहे
  * `audio/mr_01_r2.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 3.46s, RMS -23.38 dBFS, peak -7.24 dBFS, clipped 0.000%, voiced 65%, voice-band 98.4%, telephone-band 74%, hf_share 1.95% (diag), centroid 744 Hz; render 500 ms, ASR 1949 ms
    * heard: माझा ऑर्डर नंबर एक दोन तीन आहे
  * `audio/mr_01_r3.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 3.37s, RMS -23.39 dBFS, peak -7.18 dBFS, clipped 0.000%, voiced 64%, voice-band 98.4%, telephone-band 77%, hf_share 1.73% (diag), centroid 716 Hz; render 516 ms, ASR 3413 ms
    * heard: माझा ऑर्डर नंबर एक दोन तीन आहे
* sentence 2: उद्या संध्याकाळपर्यंत डिलिव्हरी होईल.
  * clean takes 3/3, CER clean mean 0.000, max 0.000
  * `audio/mr_02_r1.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 3.14s, RMS -23.41 dBFS, peak -7.57 dBFS, clipped 0.000%, voiced 73%, voice-band 98.2%, telephone-band 62%, hf_share 1.49% (diag), centroid 597 Hz; render 555 ms, ASR 1474 ms
    * heard: उद्या संध्याकाळपर्यंत डिलिव्हरी होईल
  * `audio/mr_02_r2.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 3.06s, RMS -23.42 dBFS, peak -7.68 dBFS, clipped 0.000%, voiced 72%, voice-band 98.1%, telephone-band 69%, hf_share 1.55% (diag), centroid 615 Hz; render 421 ms, ASR 1551 ms
    * heard: उद्या संध्याकाळपर्यंत डिलिव्हरी होईल
  * `audio/mr_02_r3.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 3.09s, RMS -23.42 dBFS, peak -7.49 dBFS, clipped 0.000%, voiced 73%, voice-band 98.2%, telephone-band 63%, hf_share 1.46% (diag), centroid 571 Hz; render 399 ms, ASR 2079 ms
    * heard: उद्या संध्याकाळपर्यंत डिलिव्हरी होईल
* sentence 3: माझा पत्ता पुण्यात आहे.
  * clean takes 3/3, CER clean mean 0.000, max 0.000
  * `audio/mr_03_r1.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.14s, RMS -23.57 dBFS, peak -7.51 dBFS, clipped 0.000%, voiced 59%, voice-band 97.9%, telephone-band 69%, hf_share 1.52% (diag), centroid 767 Hz; render 463 ms, ASR 1100 ms
    * heard: माझा पत्ता पुण्यात आहे
  * `audio/mr_03_r2.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.09s, RMS -23.58 dBFS, peak -6.65 dBFS, clipped 0.000%, voiced 60%, voice-band 97.8%, telephone-band 71%, hf_share 1.37% (diag), centroid 771 Hz; render 333 ms, ASR 983 ms
    * heard: माझा पत्ता पुण्यात आहे
  * `audio/mr_03_r3.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.14s, RMS -23.57 dBFS, peak -8.1 dBFS, clipped 0.000%, voiced 61%, voice-band 97.7%, telephone-band 68%, hf_share 1.63% (diag), centroid 770 Hz; render 327 ms, ASR 980 ms
    * heard: माझा पत्ता पुण्यात आहे

### bn — PASS (automated)

* sentence 1: আমার অর্ডার নম্বর এক দুই তিন।
  * clean takes 3/3, CER clean mean 0.000, max 0.000
  * `audio/bn_01_r1.wav` — PASS (automated); CER raw 0.042 / clean 0.000, WER clean 0.000; 2.46s, RMS -23.51 dBFS, peak -4.92 dBFS, clipped 0.000%, voiced 62%, voice-band 99.6%, telephone-band 90%, hf_share 1.34% (diag), centroid 906 Hz; render 221 ms, ASR 1522 ms
    * heard: আমার অর্ডার নম্বর এক দুই তিন
    * note: raw-harness error is punctuation only (danda counted as a character)
  * `audio/bn_01_r2.wav` — PASS (automated); CER raw 0.042 / clean 0.000, WER clean 0.000; 2.48s, RMS -23.5 dBFS, peak -4.61 dBFS, clipped 0.000%, voiced 60%, voice-band 99.4%, telephone-band 89%, hf_share 1.63% (diag), centroid 897 Hz; render 421 ms, ASR 1336 ms
    * heard: আমার অর্ডার নম্বর এক দুই তিন
    * note: raw-harness error is punctuation only (danda counted as a character)
  * `audio/bn_01_r3.wav` — PASS (automated); CER raw 0.042 / clean 0.000, WER clean 0.000; 2.41s, RMS -23.51 dBFS, peak -5.48 dBFS, clipped 0.000%, voiced 62%, voice-band 99.5%, telephone-band 86%, hf_share 1.70% (diag), centroid 857 Hz; render 425 ms, ASR 1351 ms
    * heard: আমার অর্ডার নম্বর এক দুই তিন
    * note: raw-harness error is punctuation only (danda counted as a character)
* sentence 2: কাল সন্ধ্যার মধ্যে ডেলিভারি হবে।
  * clean takes 3/3, CER clean mean 0.000, max 0.000
  * `audio/bn_02_r1.wav` — PASS (automated); CER raw 0.036 / clean 0.000, WER clean 0.000; 2.28s, RMS -23.54 dBFS, peak -2.7 dBFS, clipped 0.000%, voiced 74%, voice-band 98.2%, telephone-band 76%, hf_share 2.39% (diag), centroid 791 Hz; render 469 ms, ASR 1168 ms
    * heard: কাল সন্ধ্যার মধ্যে ডেলিভারি হবে
    * note: raw-harness error is punctuation only (danda counted as a character)
  * `audio/bn_02_r2.wav` — PASS (automated); CER raw 0.036 / clean 0.000, WER clean 0.000; 2.23s, RMS -23.55 dBFS, peak -2.15 dBFS, clipped 0.000%, voiced 72%, voice-band 98.6%, telephone-band 76%, hf_share 1.92% (diag), centroid 741 Hz; render 352 ms, ASR 1057 ms
    * heard: কাল সন্ধ্যার মধ্যে ডেলিভারি হবে
    * note: raw-harness error is punctuation only (danda counted as a character)
  * `audio/bn_02_r3.wav` — PASS (automated); CER raw 0.036 / clean 0.000, WER clean 0.000; 2.25s, RMS -23.55 dBFS, peak -1.94 dBFS, clipped 0.000%, voiced 72%, voice-band 98.7%, telephone-band 73%, hf_share 2.74% (diag), centroid 843 Hz; render 328 ms, ASR 1194 ms
    * heard: কাল সন্ধ্যার মধ্যে ডেলিভারি হবে
    * note: raw-harness error is punctuation only (danda counted as a character)
* sentence 3: আমার ঠিকানা কলকাতায়।
  * clean takes 3/3, CER clean mean 0.000, max 0.000
  * `audio/bn_03_r1.wav` — PASS (automated); CER raw 0.053 / clean 0.000, WER clean 0.000; 1.77s, RMS -23.68 dBFS, peak -4.22 dBFS, clipped 0.000%, voiced 57%, voice-band 98.7%, telephone-band 85%, hf_share 2.54% (diag), centroid 906 Hz; render 339 ms, ASR 797 ms
    * heard: আমার ঠিকানা কলকাতায়
    * note: raw-harness error is punctuation only (danda counted as a character)
  * `audio/bn_03_r2.wav` — PASS (automated); CER raw 0.053 / clean 0.000, WER clean 0.000; 1.72s, RMS -23.69 dBFS, peak -4.72 dBFS, clipped 0.000%, voiced 51%, voice-band 99.3%, telephone-band 91%, hf_share 2.61% (diag), centroid 1049 Hz; render 351 ms, ASR 1124 ms
    * heard: আমার ঠিকানা কলকাতায়
    * note: raw-harness error is punctuation only (danda counted as a character)
  * `audio/bn_03_r3.wav` — PASS (automated); CER raw 0.053 / clean 0.000, WER clean 0.000; 1.77s, RMS -23.67 dBFS, peak -2.72 dBFS, clipped 0.000%, voiced 51%, voice-band 99.3%, telephone-band 94%, hf_share 1.57% (diag), centroid 1000 Hz; render 320 ms, ASR 1934 ms
    * heard: আমার ঠিকানা কলকাতায়
    * note: raw-harness error is punctuation only (danda counted as a character)

### ta — PASS (automated)

* sentence 1: என் ஆர்டர் எண் ஒன்று இரண்டு மூன்று.
  * clean takes 3/3, CER clean mean 0.011, max 0.034
  * `audio/ta_01_r1.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.43s, RMS -23.51 dBFS, peak -5.86 dBFS, clipped 0.000%, voiced 70%, voice-band 98.6%, telephone-band 63%, hf_share 0.72% (diag), centroid 504 Hz; render 254 ms, ASR 1217 ms
    * heard: என் ஆர்டர் எண் ஒன்று இரண்டு மூன்று
  * `audio/ta_01_r2.wav` — PASS (automated); CER raw 0.034 / clean 0.034, WER clean 0.167; 2.45s, RMS -23.51 dBFS, peak -6.94 dBFS, clipped 0.000%, voiced 73%, voice-band 98.8%, telephone-band 66%, hf_share 0.86% (diag), centroid 510 Hz; render 428 ms, ASR 1844 ms
    * heard: என் ஆ்டர் எண் ஒன்று இரண்டு மூன்று
  * `audio/ta_01_r3.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.38s, RMS -23.52 dBFS, peak -7.56 dBFS, clipped 0.000%, voiced 72%, voice-band 98.8%, telephone-band 71%, hf_share 0.85% (diag), centroid 558 Hz; render 483 ms, ASR 1231 ms
    * heard: என் ஆர்டர் எண் ஒன்று இரண்டு மூன்று
* sentence 2: நாளை மாலைக்குள் டெலிவரி ஆகும்.
  * clean takes 3/3, CER clean mean 0.000, max 0.000
  * `audio/ta_02_r1.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.25s, RMS -23.54 dBFS, peak -6.65 dBFS, clipped 0.000%, voiced 68%, voice-band 99.5%, telephone-band 81%, hf_share 0.59% (diag), centroid 670 Hz; render 352 ms, ASR 1072 ms
    * heard: நாளை மாலைக்குள் டெலிவரி ஆகும்
  * `audio/ta_02_r2.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.18s, RMS -23.56 dBFS, peak -6.22 dBFS, clipped 0.000%, voiced 68%, voice-band 99.5%, telephone-band 82%, hf_share 0.62% (diag), centroid 674 Hz; render 349 ms, ASR 1620 ms
    * heard: நாளை மாலைக்குள் டெலிவரி ஆகும்
  * `audio/ta_02_r3.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.20s, RMS -23.55 dBFS, peak -5.1 dBFS, clipped 0.000%, voiced 66%, voice-band 99.4%, telephone-band 78%, hf_share 0.67% (diag), centroid 672 Hz; render 465 ms, ASR 1307 ms
    * heard: நாளை மாலைக்குள் டெலிவரி ஆகும்
* sentence 3: என் முகவரி சென்னையில் உள்ளது.
  * clean takes 3/3, CER clean mean 0.000, max 0.000
  * `audio/ta_03_r1.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.01s, RMS -23.6 dBFS, peak -5.94 dBFS, clipped 0.000%, voiced 71%, voice-band 98.8%, telephone-band 71%, hf_share 1.50% (diag), centroid 540 Hz; render 333 ms, ASR 1097 ms
    * heard: என் முகவரி சென்னையில் உள்ளது
  * `audio/ta_03_r2.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 1.97s, RMS -23.61 dBFS, peak -7.14 dBFS, clipped 0.000%, voiced 70%, voice-band 98.9%, telephone-band 75%, hf_share 1.03% (diag), centroid 511 Hz; render 323 ms, ASR 1158 ms
    * heard: என் முகவரி சென்னையில் உள்ளது
  * `audio/ta_03_r3.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.01s, RMS -23.6 dBFS, peak -6.87 dBFS, clipped 0.000%, voiced 70%, voice-band 99.2%, telephone-band 73%, hf_share 0.93% (diag), centroid 508 Hz; render 360 ms, ASR 1004 ms
    * heard: என் முகவரி சென்னையில் உள்ளது

### te — PASS (automated)

* sentence 1: నా ఆర్డర్ నంబర్ ఒకటి రెండు మూడు.
  * clean takes 3/3, CER clean mean 0.000, max 0.000
  * `audio/te_01_r1.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 3.00s, RMS -23.43 dBFS, peak -5.72 dBFS, clipped 0.000%, voiced 54%, voice-band 99.3%, telephone-band 87%, hf_share 0.94% (diag), centroid 693 Hz; render 239 ms, ASR 1078 ms
    * heard: నా ఆర్డర్ నంబర్ ఒకటి రెండు మూడు
  * `audio/te_01_r2.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 3.02s, RMS -23.43 dBFS, peak -2.94 dBFS, clipped 0.000%, voiced 53%, voice-band 99.3%, telephone-band 87%, hf_share 1.04% (diag), centroid 736 Hz; render 427 ms, ASR 1212 ms
    * heard: నా ఆర్డర్ నంబర్ ఒకటి రెండు మూడు
  * `audio/te_01_r3.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.95s, RMS -23.43 dBFS, peak -3.92 dBFS, clipped 0.000%, voiced 50%, voice-band 99.2%, telephone-band 88%, hf_share 0.98% (diag), centroid 741 Hz; render 381 ms, ASR 1444 ms
    * heard: నా ఆర్డర్ నంబర్ ఒకటి రెండు మూడు
* sentence 2: రేపు సాయంత్రం వరకు డెలివరీ అవుతుంది.
  * clean takes 3/3, CER clean mean 0.000, max 0.000
  * `audio/te_02_r1.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.54s, RMS -23.49 dBFS, peak -4.12 dBFS, clipped 0.000%, voiced 68%, voice-band 96.2%, telephone-band 88%, hf_share 4.91% (diag), centroid 950 Hz; render 333 ms, ASR 1127 ms
    * heard: రేపు సాయంత్రం వరకు డెలివరీ అవుతుంది
  * `audio/te_02_r2.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.48s, RMS -23.5 dBFS, peak -3.32 dBFS, clipped 0.000%, voiced 69%, voice-band 92.9%, telephone-band 84%, hf_share 9.75% (diag), centroid 1212 Hz; render 357 ms, ASR 1320 ms
    * heard: రేపు సాయంత్రం వరకు డెలివరీ అవుతుంది
  * `audio/te_02_r3.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.50s, RMS -23.5 dBFS, peak -6.12 dBFS, clipped 0.000%, voiced 71%, voice-band 97.2%, telephone-band 89%, hf_share 4.09% (diag), centroid 886 Hz; render 344 ms, ASR 2195 ms
    * heard: రేపు సాయంత్రం వరకు డెలివరీ అవుతుంది
* sentence 3: నా చిరునామా హైదరాబాద్‌లో ఉంది.
  * clean takes 3/3, CER clean mean 0.000, max 0.000
  * `audio/te_03_r1.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.29s, RMS -23.54 dBFS, peak -2.78 dBFS, clipped 0.000%, voiced 69%, voice-band 97.5%, telephone-band 91%, hf_share 3.30% (diag), centroid 1026 Hz; render 397 ms, ASR 1332 ms
    * heard: నా చిరునామా హైదరాబాద్ లో ఉంది
  * `audio/te_03_r2.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.24s, RMS -23.55 dBFS, peak -4.8 dBFS, clipped 0.000%, voiced 68%, voice-band 98.0%, telephone-band 91%, hf_share 2.58% (diag), centroid 900 Hz; render 424 ms, ASR 1391 ms
    * heard: నా చిరునామా హైదరాబాద్ లో ఉంది
  * `audio/te_03_r3.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.29s, RMS -23.54 dBFS, peak -3.25 dBFS, clipped 0.000%, voiced 66%, voice-band 97.7%, telephone-band 92%, hf_share 3.23% (diag), centroid 973 Hz; render 377 ms, ASR 1258 ms
    * heard: నా చిరునామా హైదరాబాద్ లో ఉంది

### kn — PASS (automated)

* sentence 1: ನನ್ನ ಆರ್ಡರ್ ನಂಬರ್ ಒಂದು ಎರಡು ಮೂರು.
  * clean takes 3/3, CER clean mean 0.000, max 0.000
  * `audio/kn_01_r1.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 3.02s, RMS -23.43 dBFS, peak -10.6 dBFS, clipped 0.000%, voiced 75%, voice-band 99.6%, telephone-band 50%, hf_share 0.43% (diag), centroid 425 Hz; render 251 ms, ASR 1434 ms
    * heard: ನನ್ನ ಆರ್ಡರ್ ನಂಬರ್ ಒಂದು ಎರಡು ಮೂರು
  * `audio/kn_01_r2.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 3.06s, RMS -23.42 dBFS, peak -10.62 dBFS, clipped 0.000%, voiced 76%, voice-band 99.7%, telephone-band 55%, hf_share 0.35% (diag), centroid 418 Hz; render 379 ms, ASR 1519 ms
    * heard: ನನ್ನ ಆರ್ಡರ್ ನಂಬರ್ ಒಂದು ಎರಡು ಮೂರು
  * `audio/kn_01_r3.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.97s, RMS -23.43 dBFS, peak -10.56 dBFS, clipped 0.000%, voiced 74%, voice-band 99.7%, telephone-band 48%, hf_share 0.35% (diag), centroid 404 Hz; render 408 ms, ASR 1518 ms
    * heard: ನನ್ನ ಆರ್ಡರ್ ನಂಬರ್ ಒಂದು ಎರಡು ಮೂರು
* sentence 2: ನಾಳೆ ಸಂಜೆಯೊಳಗೆ ಡೆಲಿವರಿ ಆಗುತ್ತದೆ.
  * clean takes 3/3, CER clean mean 0.000, max 0.000
  * `audio/kn_02_r1.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 3.07s, RMS -23.42 dBFS, peak -9.52 dBFS, clipped 0.000%, voiced 74%, voice-band 99.1%, telephone-band 62%, hf_share 0.91% (diag), centroid 466 Hz; render 494 ms, ASR 1870 ms
    * heard: ನಾಳೆ ಸಂಜೆಯೊಳಗೆ ಡೆಲಿವರಿ ಆಗುತ್ತದೆ
  * `audio/kn_02_r2.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.98s, RMS -23.43 dBFS, peak -10.44 dBFS, clipped 0.000%, voiced 74%, voice-band 99.0%, telephone-band 59%, hf_share 1.03% (diag), centroid 476 Hz; render 496 ms, ASR 1939 ms
    * heard: ನಾಳೆ ಸಂಜೆಯೊಳಗೆ ಡೆಲಿವರಿ ಆಗುತ್ತದೆ
  * `audio/kn_02_r3.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 3.02s, RMS -23.43 dBFS, peak -9.13 dBFS, clipped 0.000%, voiced 75%, voice-band 99.0%, telephone-band 61%, hf_share 1.04% (diag), centroid 480 Hz; render 423 ms, ASR 1712 ms
    * heard: ನಾಳೆ ಸಂಜೆಯೊಳಗೆ ಡೆಲಿವರಿ ಆಗುತ್ತದೆ
* sentence 3: ನನ್ನ ವಿಳಾಸ ಬೆಂಗಳೂರಿನಲ್ಲಿದೆ.
  * clean takes 3/3, CER clean mean 0.000, max 0.000
  * `audio/kn_03_r1.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.62s, RMS -23.48 dBFS, peak -10.71 dBFS, clipped 0.000%, voiced 77%, voice-band 99.4%, telephone-band 45%, hf_share 0.63% (diag), centroid 410 Hz; render 464 ms, ASR 1454 ms
    * heard: ನನ್ನ ವಿಳಾಸ ಬೆಂಗಳೂರಿನಲ್ಲಿದೆ
  * `audio/kn_03_r2.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.56s, RMS -23.49 dBFS, peak -10.65 dBFS, clipped 0.000%, voiced 77%, voice-band 99.3%, telephone-band 45%, hf_share 0.68% (diag), centroid 425 Hz; render 386 ms, ASR 1250 ms
    * heard: ನನ್ನ ವಿಳಾಸ ಬೆಂಗಳೂರಿನಲ್ಲಿದೆ
  * `audio/kn_03_r3.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.63s, RMS -23.48 dBFS, peak -10.32 dBFS, clipped 0.000%, voiced 77%, voice-band 99.2%, telephone-band 46%, hf_share 0.82% (diag), centroid 430 Hz; render 382 ms, ASR 1200 ms
    * heard: ನನ್ನ ವಿಳಾಸ ಬೆಂಗಳೂರಿನಲ್ಲಿದೆ

### ml — PARTIAL

* sentence 1: എന്റെ ഓർഡർ നമ്പർ ഒന്ന് രണ്ട് മൂന്ന്.
  * clean takes 3/3, CER clean mean 0.000, max 0.000
  * `audio/ml_01_r1.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.47s, RMS -23.5 dBFS, peak -7.12 dBFS, clipped 0.000%, voiced 75%, voice-band 99.9%, telephone-band 56%, hf_share 0.26% (diag), centroid 474 Hz; render 633 ms, ASR 1667 ms
    * heard: എന്റെ ഓർഡർ നമ്പർ ഒന്ന് രണ്ട് മൂന്ന്
  * `audio/ml_01_r2.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.49s, RMS -23.5 dBFS, peak -9.58 dBFS, clipped 0.000%, voiced 75%, voice-band 99.9%, telephone-band 57%, hf_share 0.27% (diag), centroid 478 Hz; render 379 ms, ASR 1405 ms
    * heard: എന്റെ ഓർഡർ നമ്പർ ഒന്ന് രണ്ട് മൂന്ന്
  * `audio/ml_01_r3.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.43s, RMS -23.51 dBFS, peak -9.55 dBFS, clipped 0.000%, voiced 74%, voice-band 99.9%, telephone-band 50%, hf_share 0.17% (diag), centroid 439 Hz; render 379 ms, ASR 1482 ms
    * heard: എന്റെ ഓർഡർ നമ്പർ ഒന്ന് രണ്ട് മൂന്ന്
* sentence 2: നാളെ വൈകുന്നേരത്തിനുള്ളിൽ ഡെലിവറി ആകും.
  * clean takes 2/3, CER clean mean 0.019, max 0.057
  * `audio/ml_02_r1.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.64s, RMS -23.48 dBFS, peak -7.41 dBFS, clipped 0.000%, voiced 77%, voice-band 99.8%, telephone-band 61%, hf_share 0.46% (diag), centroid 639 Hz; render 329 ms, ASR 1479 ms
    * heard: നാളെ വൈകുന്നേരത്തിനുള്ളിൽ ഡെലിവറി ആകും
  * `audio/ml_02_r2.wav` — PARTIAL; CER raw 0.057 / clean 0.057, WER clean 0.500; 2.58s, RMS -23.49 dBFS, peak -7.83 dBFS, clipped 0.000%, voiced 76%, voice-band 99.8%, telephone-band 63%, hf_share 0.47% (diag), centroid 639 Hz; render 438 ms, ASR 1451 ms
    * heard: നാളെ വൈകുന്നേരത്തിനുള്ളിൽ ഡെലിവറിിയകും
    * note: words lost or altered in this render
  * `audio/ml_02_r3.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.60s, RMS -23.48 dBFS, peak -7.89 dBFS, clipped 0.000%, voiced 76%, voice-band 99.8%, telephone-band 62%, hf_share 0.54% (diag), centroid 641 Hz; render 355 ms, ASR 1406 ms
    * heard: നാളെ വൈകുന്നേരത്തിനുള്ളിൽ ഡെലിവറി ആകും
* sentence 3: എന്റെ വിലാസം കൊച്ചിയിലാണ്.
  * clean takes 0/3, CER clean mean 0.087, max 0.087
  * `audio/ml_03_r1.wav` — PARTIAL; CER raw 0.087 / clean 0.087, WER clean 0.333; 1.58s, RMS -23.75 dBFS, peak -8.81 dBFS, clipped 0.000%, voiced 76%, voice-band 99.3%, telephone-band 37%, hf_share 0.85% (diag), centroid 438 Hz; render 286 ms, ASR 927 ms
    * heard: എറെ വിലാസം കൊച്ചിയിലാണ്
    * note: words lost or altered in this render
  * `audio/ml_03_r2.wav` — PARTIAL; CER raw 0.087 / clean 0.087, WER clean 0.333; 1.55s, RMS -23.76 dBFS, peak -8.42 dBFS, clipped 0.000%, voiced 77%, voice-band 99.2%, telephone-band 50%, hf_share 1.11% (diag), centroid 493 Hz; render 292 ms, ASR 856 ms
    * heard: എറെ വിലാസം കൊച്ചിയിലാണ്
    * note: words lost or altered in this render
  * `audio/ml_03_r3.wav` — PARTIAL; CER raw 0.087 / clean 0.087, WER clean 0.333; 1.60s, RMS -23.74 dBFS, peak -7.49 dBFS, clipped 0.000%, voiced 76%, voice-band 99.3%, telephone-band 44%, hf_share 0.85% (diag), centroid 485 Hz; render 346 ms, ASR 1154 ms
    * heard: എറെ വിലാസം കൊച്ചിയിലാണ്
    * note: words lost or altered in this render

### pa — PASS (automated)

* sentence 1: ਮੇਰਾ ਆਰਡਰ ਨੰਬਰ ਇੱਕ ਦੋ ਤਿੰਨ ਹੈ।
  * clean takes 3/3, CER clean mean 0.029, max 0.043
  * `audio/pa_01_r1.wav` — PASS (automated); CER raw 0.042 / clean 0.000, WER clean 0.000; 3.19s, RMS -23.41 dBFS, peak -4.49 dBFS, clipped 0.000%, voiced 57%, voice-band 99.7%, telephone-band 90%, hf_share 0.34% (diag), centroid 678 Hz; render 261 ms, ASR 1348 ms
    * heard: ਮੇਰਾ ਆਰਡਰ ਨੰਬਰ ਇੱਕ ਦੋ ਤਿੰਨ ਹੈ
    * note: raw-harness error is punctuation only (danda counted as a character)
  * `audio/pa_01_r2.wav` — PASS (automated); CER raw 0.083 / clean 0.043, WER clean 0.143; 3.22s, RMS -23.41 dBFS, peak -5.46 dBFS, clipped 0.000%, voiced 56%, voice-band 99.5%, telephone-band 88%, hf_share 0.53% (diag), centroid 697 Hz; render 377 ms, ASR 1415 ms
    * heard: ਮੇਰਾ ਓਰਡਰ ਨੰਬਰ ਇੱਕ ਦੋ ਤਿੰਨ ਹੈ
  * `audio/pa_01_r3.wav` — PASS (automated); CER raw 0.083 / clean 0.043, WER clean 0.286; 3.12s, RMS -23.42 dBFS, peak -5.0 dBFS, clipped 0.000%, voiced 58%, voice-band 99.5%, telephone-band 84%, hf_share 0.42% (diag), centroid 663 Hz; render 400 ms, ASR 1264 ms
    * heard: ਮੇਰਾਓਰਡਰ ਨੰਬਰ ਇੱਕ ਦੋ ਤਿੰਨ ਹੈ
* sentence 2: ਕੱਲ੍ਹ ਸ਼ਾਮ ਤੱਕ ਡਿਲੀਵਰੀ ਹੋ ਜਾਵੇਗੀ।
  * clean takes 3/3, CER clean mean 0.025, max 0.074
  * `audio/pa_02_r1.wav` — PASS (automated); CER raw 0.107 / clean 0.074, WER clean 0.167; 2.46s, RMS -23.5 dBFS, peak -4.64 dBFS, clipped 0.000%, voiced 68%, voice-band 97.6%, telephone-band 86%, hf_share 2.70% (diag), centroid 960 Hz; render 343 ms, ASR 1342 ms
    * heard: ਕੱਲ ਸ਼ਾਮ ਤੱਕ ਡਿਲੀਵਰੀ ਹੋ ਜਾਵੇਗੀ
  * `audio/pa_02_r2.wav` — PASS (automated); CER raw 0.036 / clean 0.000, WER clean 0.000; 2.40s, RMS -23.52 dBFS, peak -4.18 dBFS, clipped 0.000%, voiced 62%, voice-band 97.0%, telephone-band 89%, hf_share 3.39% (diag), centroid 988 Hz; render 379 ms, ASR 1215 ms
    * heard: ਕੱਲ੍ਹ ਸ਼ਾਮ ਤੱਕ ਡਿਲੀਵਰੀ ਹੋ ਜਾਵੇਗੀ
    * note: raw-harness error is punctuation only (danda counted as a character)
  * `audio/pa_02_r3.wav` — PASS (automated); CER raw 0.036 / clean 0.000, WER clean 0.000; 2.42s, RMS -23.51 dBFS, peak -3.44 dBFS, clipped 0.000%, voiced 66%, voice-band 98.4%, telephone-band 87%, hf_share 1.92% (diag), centroid 939 Hz; render 340 ms, ASR 1096 ms
    * heard: ਕੱਲ੍ਹ ਸ਼ਾਮ ਤੱਕ ਡਿਲੀਵਰੀ ਹੋ ਜਾਵੇਗੀ
    * note: raw-harness error is punctuation only (danda counted as a character)
* sentence 3: ਮੇਰਾ ਪਤਾ ਲੁਧਿਆਣਾ ਵਿੱਚ ਹੈ।
  * clean takes 3/3, CER clean mean 0.000, max 0.000
  * `audio/pa_03_r1.wav` — PASS (automated); CER raw 0.048 / clean 0.000, WER clean 0.000; 2.58s, RMS -23.49 dBFS, peak -2.48 dBFS, clipped 0.000%, voiced 49%, voice-band 99.0%, telephone-band 79%, hf_share 0.82% (diag), centroid 727 Hz; render 338 ms, ASR 811 ms
    * heard: ਮੇਰਾ ਪਤਾ ਲੁਧਿਆਣਾ ਵਿੱਚ ਹੈ
    * note: raw-harness error is punctuation only (danda counted as a character)
  * `audio/pa_03_r2.wav` — PASS (automated); CER raw 0.048 / clean 0.000, WER clean 0.000; 2.51s, RMS -23.5 dBFS, peak -4.43 dBFS, clipped 0.000%, voiced 51%, voice-band 98.8%, telephone-band 84%, hf_share 1.09% (diag), centroid 738 Hz; render 372 ms, ASR 1161 ms
    * heard: ਮੇਰਾ ਪਤਾ ਲੁਧਿਆਣਾ ਵਿੱਚ ਹੈ
    * note: raw-harness error is punctuation only (danda counted as a character)
  * `audio/pa_03_r3.wav` — PASS (automated); CER raw 0.048 / clean 0.000, WER clean 0.000; 2.58s, RMS -23.49 dBFS, peak -5.95 dBFS, clipped 0.000%, voiced 52%, voice-band 98.5%, telephone-band 83%, hf_share 1.30% (diag), centroid 734 Hz; render 372 ms, ASR 1065 ms
    * heard: ਮੇਰਾ ਪਤਾ ਲੁਧਿਆਣਾ ਵਿੱਚ ਹੈ
    * note: raw-harness error is punctuation only (danda counted as a character)

### or — PARTIAL

* sentence 1: ମୋ ଅର୍ଡର ନମ୍ବର ଏକ ଦୁଇ ତିନି।
  * clean takes 3/3, CER clean mean 0.048, max 0.048
  * `audio/or_01_r1.wav` — PASS (automated); CER raw 0.091 / clean 0.048, WER clean 0.167; 2.77s, RMS -23.46 dBFS, peak -6.73 dBFS, clipped 0.000%, voiced 55%, voice-band 99.7%, telephone-band 86%, hf_share 0.34% (diag), centroid 632 Hz; render 249 ms, ASR 1179 ms
    * heard: ମୋ ଓର୍ଡର ନମ୍ବର ଏକ ଦୁଇ ତିନି
  * `audio/or_01_r2.wav` — PASS (automated); CER raw 0.091 / clean 0.048, WER clean 0.167; 2.79s, RMS -23.45 dBFS, peak -4.48 dBFS, clipped 0.000%, voiced 57%, voice-band 99.5%, telephone-band 89%, hf_share 0.50% (diag), centroid 672 Hz; render 374 ms, ASR 1204 ms
    * heard: ମୋ ଓର୍ଡର ନମ୍ବର ଏକ ଦୁଇ ତିନି
  * `audio/or_01_r3.wav` — PASS (automated); CER raw 0.091 / clean 0.048, WER clean 0.167; 2.72s, RMS -23.46 dBFS, peak -7.25 dBFS, clipped 0.000%, voiced 56%, voice-band 99.5%, telephone-band 90%, hf_share 0.41% (diag), centroid 631 Hz; render 390 ms, ASR 1371 ms
    * heard: ମୋ ଅର୍ଡ଼ର ନମ୍ବର ଏକ ଦୁଇ ତିନି
* sentence 2: କାଲି ସନ୍ଧ୍ୟା ସୁଦ୍ଧା ଡେଲିଭରି ହେବ।
  * clean takes 3/3, CER clean mean 0.000, max 0.000
  * `audio/or_02_r1.wav` — PASS (automated); CER raw 0.036 / clean 0.000, WER clean 0.000; 2.40s, RMS -23.52 dBFS, peak -7.03 dBFS, clipped 0.000%, voiced 71%, voice-band 98.6%, telephone-band 77%, hf_share 1.47% (diag), centroid 641 Hz; render 692 ms, ASR 2748 ms
    * heard: କାଲି ସନ୍ଧ୍ୟା ସୁଦ୍ଧା ଡେଲିଭରି ହେବ
    * note: raw-harness error is punctuation only (danda counted as a character)
  * `audio/or_02_r2.wav` — PASS (automated); CER raw 0.036 / clean 0.000, WER clean 0.000; 2.34s, RMS -23.53 dBFS, peak -3.11 dBFS, clipped 0.000%, voiced 71%, voice-band 98.7%, telephone-band 80%, hf_share 1.56% (diag), centroid 713 Hz; render 798 ms, ASR 2336 ms
    * heard: କାଲି ସନ୍ଧ୍ୟା ସୁଦ୍ଧା ଡେଲିଭରି ହେବ
    * note: raw-harness error is punctuation only (danda counted as a character)
  * `audio/or_02_r3.wav` — PASS (automated); CER raw 0.036 / clean 0.000, WER clean 0.000; 2.36s, RMS -23.52 dBFS, peak -5.98 dBFS, clipped 0.000%, voiced 64%, voice-band 99.1%, telephone-band 79%, hf_share 0.99% (diag), centroid 605 Hz; render 459 ms, ASR 1612 ms
    * heard: କାଲି ସନ୍ଧ୍ୟା ସୁଦ୍ଧା ଡେଲିଭରି ହେବ
    * note: raw-harness error is punctuation only (danda counted as a character)
* sentence 3: ମୋ ଠିକଣା ଭୁବନେଶ୍ୱରରେ ଅଛି।
  * clean takes 2/3, CER clean mean 0.032, max 0.048
  * `audio/or_03_r1.wav` — PARTIAL; CER raw 0.091 / clean 0.048, WER clean 0.500; 2.82s, RMS -23.45 dBFS, peak -6.92 dBFS, clipped 0.000%, voiced 56%, voice-band 98.0%, telephone-band 89%, hf_share 1.24% (diag), centroid 684 Hz; render 440 ms, ASR 1349 ms
    * heard: ମୋଠି କଣ ଭୁବନେଶ୍ୱରରେ ଅଛି
    * note: words lost or altered in this render
  * `audio/or_03_r2.wav` — PASS (automated); CER raw 0.091 / clean 0.048, WER clean 0.250; 2.75s, RMS -23.46 dBFS, peak -5.55 dBFS, clipped 0.000%, voiced 57%, voice-band 97.3%, telephone-band 82%, hf_share 1.01% (diag), centroid 660 Hz; render 391 ms, ASR 1342 ms
    * heard: ମୋ ଠିକଣ ଭୁବନେଶ୍ୱରରେ ଅଛି
  * `audio/or_03_r3.wav` — PASS (automated); CER raw 0.045 / clean 0.000, WER clean 0.000; 2.82s, RMS -23.45 dBFS, peak -5.81 dBFS, clipped 0.000%, voiced 54%, voice-band 97.8%, telephone-band 83%, hf_share 0.87% (diag), centroid 645 Hz; render 482 ms, ASR 1372 ms
    * heard: ମୋ ଠିକଣା ଭୁବନେଶ୍ୱରରେ ଅଛି
    * note: raw-harness error is punctuation only (danda counted as a character)

### as — PARTIAL

* sentence 1: মোৰ অৰ্ডাৰ নম্বৰ এক দুই তিনি।
  * clean takes 0/3, CER clean mean 0.232, max 0.261
  * `audio/as_01_r1.wav` — PARTIAL; CER raw 0.250 / clean 0.217, WER clean 0.667; 2.59s, RMS -23.48 dBFS, peak -7.6 dBFS, clipped 0.000%, voiced 64%, voice-band 99.6%, telephone-band 72%, hf_share 0.47% (diag), centroid 632 Hz; render 244 ms, ASR 2199 ms
    * heard: মোর অর্ডার নম্বর এক দুই তিন
    * note: words lost or altered in this render
  * `audio/as_01_r2.wav` — PARTIAL; CER raw 0.250 / clean 0.217, WER clean 0.667; 2.61s, RMS -23.48 dBFS, peak -6.61 dBFS, clipped 0.000%, voiced 65%, voice-band 99.5%, telephone-band 68%, hf_share 0.49% (diag), centroid 624 Hz; render 809 ms, ASR 1337 ms
    * heard: মোর অর্ডার নম্বর এক দুই তিনই
    * note: words lost or altered in this render
  * `audio/as_01_r3.wav` — PARTIAL; CER raw 0.292 / clean 0.261, WER clean 0.667; 2.54s, RMS -23.49 dBFS, peak -5.87 dBFS, clipped 0.000%, voiced 65%, voice-band 99.6%, telephone-band 67%, hf_share 0.47% (diag), centroid 595 Hz; render 338 ms, ASR 1187 ms
    * heard: মোর অর্ডার নম্বার এক দুই তিনই
    * note: words lost or altered in this render
* sentence 2: কাইলৈ সন্ধিয়াৰ ভিতৰত ডেলিভাৰী হ'ব।
  * clean takes 0/3, CER clean mean 0.241, max 0.241
  * `audio/as_02_r1.wav` — PARTIAL; CER raw 0.267 / clean 0.241, WER clean 1.000; 2.40s, RMS -23.52 dBFS, peak -3.91 dBFS, clipped 0.000%, voiced 76%, voice-band 97.9%, telephone-band 71%, hf_share 0.80% (diag), centroid 630 Hz; render 357 ms, ASR 1203 ms
    * heard: কাইল সন্ধ্যিয়ার ভিতরত ডেলিভারি হব
    * note: words lost or altered in this render
  * `audio/as_02_r2.wav` — PARTIAL; CER raw 0.267 / clean 0.241, WER clean 1.000; 2.33s, RMS -23.53 dBFS, peak -5.75 dBFS, clipped 0.000%, voiced 75%, voice-band 98.6%, telephone-band 64%, hf_share 1.08% (diag), centroid 650 Hz; render 327 ms, ASR 1101 ms
    * heard: কাইল সন্ধ্যিার ভিতরত ডেলিভারি হব
    * note: words lost or altered in this render
  * `audio/as_02_r3.wav` — PARTIAL; CER raw 0.267 / clean 0.241, WER clean 1.000; 2.35s, RMS -23.52 dBFS, peak -3.84 dBFS, clipped 0.000%, voiced 74%, voice-band 98.9%, telephone-band 66%, hf_share 1.03% (diag), centroid 634 Hz; render 638 ms, ASR 1619 ms
    * heard: কাইল সন্ধ্যিার ভিতরত ডেলিভারি হব
    * note: words lost or altered in this render
* sentence 3: মোৰ ঠিকনা গুৱাহাটীত আছে।
  * clean takes 0/3, CER clean mean 0.300, max 0.300
  * `audio/as_03_r1.wav` — PARTIAL; CER raw 0.333 / clean 0.300, WER clean 0.750; 1.95s, RMS -23.62 dBFS, peak -7.61 dBFS, clipped 0.000%, voiced 64%, voice-band 96.3%, telephone-band 62%, hf_share 3.69% (diag), centroid 794 Hz; render 339 ms, ASR 838 ms
    * heard: মোর ঠিকোনা গয়াহাটি আছে
    * note: words lost or altered in this render
  * `audio/as_03_r2.wav` — PARTIAL; CER raw 0.333 / clean 0.300, WER clean 0.750; 1.91s, RMS -23.63 dBFS, peak -6.37 dBFS, clipped 0.000%, voiced 66%, voice-band 95.5%, telephone-band 55%, hf_share 4.39% (diag), centroid 811 Hz; render 322 ms, ASR 1021 ms
    * heard: মোর ঠিকোন গুয়াহাটিত আছে
    * note: words lost or altered in this render
  * `audio/as_03_r3.wav` — PARTIAL; CER raw 0.333 / clean 0.300, WER clean 0.750; 1.95s, RMS -23.62 dBFS, peak -6.55 dBFS, clipped 0.000%, voiced 65%, voice-band 94.4%, telephone-band 56%, hf_share 5.53% (diag), centroid 940 Hz; render 356 ms, ASR 1464 ms
    * heard: মোর ঠিকোনা গয়াহাটি আছে
    * note: words lost or altered in this render

### en — PARTIAL

* sentence 1: My order number is one two three.
  * clean takes 0/3, CER clean mean 0.423, max 0.423
  * `audio/en_01_r1.wav` — PARTIAL; CER raw 0.423 / clean 0.423, cer_itn 0.000, WER clean 0.429; 2.45s, RMS -23.51 dBFS, peak -7.99 dBFS, clipped 0.000%, voiced 67%, voice-band 98.7%, telephone-band 73%, hf_share 1.09% (diag), centroid 678 Hz; render 193 ms, ASR 900 ms
    * heard: My order number is 123.
    * note: miss is whisper digit formatting ('1-2-3' for 'one two three'), not missing speech
    * note: words lost or altered in this render
  * `audio/en_01_r2.wav` — PARTIAL; CER raw 0.423 / clean 0.423, cer_itn 0.000, WER clean 0.429; 2.47s, RMS -23.5 dBFS, peak -7.53 dBFS, clipped 0.000%, voiced 68%, voice-band 98.7%, telephone-band 71%, hf_share 1.17% (diag), centroid 643 Hz; render 386 ms, ASR 1222 ms
    * heard: My order number is 1-2-3.
    * note: miss is whisper digit formatting ('1-2-3' for 'one two three'), not missing speech
    * note: words lost or altered in this render
  * `audio/en_01_r3.wav` — PARTIAL; CER raw 0.423 / clean 0.423, cer_itn 0.000, WER clean 0.429; 2.41s, RMS -23.51 dBFS, peak -7.75 dBFS, clipped 0.000%, voiced 68%, voice-band 98.8%, telephone-band 70%, hf_share 1.00% (diag), centroid 638 Hz; render 370 ms, ASR 976 ms
    * heard: My order number is 123.
    * note: miss is whisper digit formatting ('1-2-3' for 'one two three'), not missing speech
    * note: words lost or altered in this render
* sentence 2: Delivery will happen before tomorrow evening.
  * clean takes 3/3, CER clean mean 0.000, max 0.000
  * `audio/en_02_r1.wav` — PASS (automated); CER raw 0.000 / clean 0.000, cer_itn 0.000, WER clean 0.000; 2.83s, RMS -23.45 dBFS, peak -6.68 dBFS, clipped 0.000%, voiced 69%, voice-band 99.3%, telephone-band 79%, hf_share 0.49% (diag), centroid 497 Hz; render 404 ms, ASR 1134 ms
    * heard: Delivery will happen before tomorrow evening.
  * `audio/en_02_r2.wav` — PASS (automated); CER raw 0.000 / clean 0.000, cer_itn 0.000, WER clean 0.000; 2.76s, RMS -23.46 dBFS, peak -6.05 dBFS, clipped 0.000%, voiced 67%, voice-band 99.0%, telephone-band 75%, hf_share 0.70% (diag), centroid 500 Hz; render 410 ms, ASR 1086 ms
    * heard: Delivery will happen before tomorrow evening.
  * `audio/en_02_r3.wav` — PASS (automated); CER raw 0.000 / clean 0.000, cer_itn 0.000, WER clean 0.000; 2.79s, RMS -23.45 dBFS, peak -6.5 dBFS, clipped 0.000%, voiced 70%, voice-band 99.2%, telephone-band 73%, hf_share 0.55% (diag), centroid 490 Hz; render 387 ms, ASR 1144 ms
    * heard: Delivery will happen before tomorrow evening.
* sentence 3: My address is in Delhi.
  * clean takes 3/3, CER clean mean 0.000, max 0.000
  * `audio/en_03_r1.wav` — PASS (automated); CER raw 0.000 / clean 0.000, cer_itn 0.000, WER clean 0.000; 1.95s, RMS -23.62 dBFS, peak -6.85 dBFS, clipped 0.000%, voiced 68%, voice-band 90.3%, telephone-band 70%, hf_share 9.27% (diag), centroid 1366 Hz; render 329 ms, ASR 1080 ms
    * heard: My address is in Delhi.
  * `audio/en_03_r2.wav` — PASS (automated); CER raw 0.000 / clean 0.000, cer_itn 0.000, WER clean 0.000; 1.90s, RMS -23.63 dBFS, peak -7.96 dBFS, clipped 0.000%, voiced 66%, voice-band 89.0%, telephone-band 66%, hf_share 10.41% (diag), centroid 1416 Hz; render 552 ms, ASR 1895 ms
    * heard: My address is in Delhi.
  * `audio/en_03_r3.wav` — PASS (automated); CER raw 0.000 / clean 0.000, cer_itn 0.000, WER clean 0.000; 1.95s, RMS -23.62 dBFS, peak -6.52 dBFS, clipped 0.000%, voiced 67%, voice-band 89.5%, telephone-band 66%, hf_share 9.97% (diag), centroid 1425 Hz; render 544 ms, ASR 1554 ms
    * heard: My address is in Delhi.

## Caveats (read before quoting any number)

* Audio is **TTS-synthesised**, not real recordings. The round-trip shares the synthesis domain and a clean channel, so it flatters the recogniser. These CER/WER values are an intelligibility proxy for the voice, not production ASR accuracy, and they add 0 to the real-recording count.
* Assamese is decoded with the Bengali Conformer (no Assamese ONNX export exists), so Bengali orthography (`ৰ`→`র`, `ৱ`→`ব`) scores as errors. The Assamese round-trip is confounded: it cannot separate a TTS pronunciation problem from a recogniser orthography problem. Native listening is the only way to resolve it.
* A low CER proves the recogniser recovered the words; it does not prove naturalness, prosody, or absence of artefacts. Only human listening can judge those: NOT TESTED.
* One speaker (sid 0), default speed, 3 corpus sentences per language. This is a 108-render sample of a fixed corpus, not a population estimate for arbitrary text.
* Run-to-run thermal variance on this 15 W laptop affects the millisecond columns, not the audio. The renders themselves vary because synthesis is stochastic.
