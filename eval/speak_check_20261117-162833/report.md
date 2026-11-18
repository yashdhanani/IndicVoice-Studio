# IndicVoice — does the voice speak? (local measured check)

Run: `speak_check_20261117-162833` · generated 2026-11-17 16:32:27 · host CPU-only, no cloud inference, no LLM, no playback on this machine.

## What was measured

Each corpus sentence was rendered through the production playback path (`TTSEngine.render_sentence`, humanised — the same audio the server pushes to the speaker), saved as a mono PCM16 wav, then:

* objective signal health of the saved wav (duration, RMS/peak, clipping, voiced fraction, voice-band 100–4000 Hz energy share, telephone-band 300–3400 Hz share, energy above 3400 Hz as a hiss indicator, spectral centroid);
* round-trip through the local production recogniser, CER/WER vs the reference;
* script check on the transcript.

## Two CER/WER columns, and why

* `cer` / `wer` — exactly what `src.evaluate` computes, comparable with earlier eval runs. Its `normalise` keeps U+0964 (danda) because that codepoint sits inside the Devanagari block it preserves, so a *perfect* Hindi transcript still scores about 1/len ≈ 0.04. That is a scoring artifact, not speech error.
* `cer_clean` / `wer_clean` — punctuation, symbols and zero-width characters removed by Unicode category before scoring. **The gates use this column.** The production harness was not modified.
* `cer_itn` (English only) — clean CER after expanding whisper's digits back to words (`1-2-3` → `one two three`). Diagnostic only, never used by a gate.

## Gates (engineering thresholds chosen for this check)

```json
{
  "min_duration_s": 0.4,
  "min_rms_dbfs": -35.0,
  "min_voiced_frac": 0.3,
  "max_clip_frac": 0.002,
  "min_voice_band_ratio": 0.7,
  "max_hf_noise_frac": 0.05,
  "max_cer_clean": 0.15,
  "max_wer_clean": 0.3
}
```

Status vocabulary: PASS (automated) / PARTIAL / FAIL. **Human listening and MOS: NOT TESTED** — nobody listened to these clips as part of this run; the wavs are packaged so that listening can happen.

## Gate calibration (measured, and a correction to the first run)

The first run of this check gated on a 300–3400 Hz telephone band and reported kn and ml as FAIL. Sub-band measurement of those same wavs showed why that gate was wrong:

| clip | <100 Hz | 100–300 Hz | 300–3400 Hz | 3400–8000 Hz | >8 kHz | f0 peak |
|---|---|---|---|---|---|---|
| kn_01 | 0.0% | 52.6% | 47.0% | 0.2% | 0.3% | ~268 Hz |
| kn_03 | 0.0% | 52.4% | 47.0% | 0.2% | 0.4% | ~237 Hz |
| ml_03 | 0.0% | 57.7% | 41.3% | 0.8% | 0.2% | ~226 Hz |
| hi_01 | 0.0% | 18.2% | 81.4% | 0.4% | 0.0% | ~187 Hz |

Kannada and Malayalam carry their fundamental and lower harmonics below 300 Hz, so a 300 Hz cut discards half the voice energy; nothing above 3400 Hz suggests hiss. The gate now requires >=70% of energy in 100–4000 Hz (voice band) and <=5% above 3400 Hz (noise ceiling). Both are reported per clip, and the telephone-band share is kept as a diagnostic column. The earlier run directory is preserved unchanged.

Two scoring artifacts were also corrected in this check only (the production harness `src/evaluate.py` was not touched): the danda U+0964 counted as a speech character, and zero-width joiners splitting Telugu words. Both inflate CER/WER on perfect speech.

## Per-language result

| lang | n | TTS | ASR | CER raw | CER clean | CER clean max | WER clean | mean s | render RTF | audible | status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| hi | 3 | tiny | indic | 0.100 | 0.056 | 0.167 | 0.067 | 2.16 | 0.16 | yes | PARTIAL |
| gu | 3 | tiny | indic | 0.012 | 0.012 | 0.037 | 0.056 | 2.63 | 0.22 | yes | PASS (automated) |
| mr | 3 | tiny | indic | 0.000 | 0.000 | 0.000 | 0.000 | 2.87 | 0.21 | yes | PASS (automated) |
| bn | 3 | tiny | indic | 0.099 | 0.058 | 0.174 | 0.111 | 2.15 | 0.58 | yes | PARTIAL |
| ta | 3 | tiny | indic | 0.000 | 0.000 | 0.000 | 0.000 | 2.20 | 0.30 | yes | PASS (automated) |
| te | 3 | tiny | indic | 0.000 | 0.000 | 0.000 | 0.000 | 2.58 | 0.25 | NO | FAIL |
| kn | 3 | tiny | indic | 0.000 | 0.000 | 0.000 | 0.000 | 2.87 | 0.48 | yes | PASS (automated) |
| ml | 3 | tiny | indic | 0.029 | 0.029 | 0.087 | 0.111 | 2.21 | 0.45 | yes | PARTIAL |
| pa | 3 | tiny | indic | 0.042 | 0.000 | 0.000 | 0.000 | 2.71 | 0.67 | yes | PASS (automated) |
| or | 3 | tiny | indic | 0.072 | 0.032 | 0.095 | 0.083 | 2.63 | 0.13 | yes | PASS (automated) |
| as | 3 | tiny | indic | 0.308 | 0.279 | 0.300 | 0.806 | 2.29 | 0.23 | yes | PARTIAL |
| en | 3 | tiny | whisper | 0.141 | 0.141 | 0.423 | 0.143 | 2.38 | 0.15 | NO | FAIL |

## Per-clip detail

### hi — PARTIAL

* `audio/hi_01.wav` — PASS (automated); CER raw 0.043 / clean 0.000, WER clean 0.000; 2.45s, RMS -23.51 dBFS, peak -5.85 dBFS, clipped 0.000%, voiced 68%, voice-band 99.8%, telephone-band 83%, >3.4kHz 0.37%, centroid 636 Hz; render 414 ms, ASR 440 ms
  * ref: मेरा ऑर्डर नंबर एक दो तीन है।
  * heard: मेरा ऑर्डर नंबर एक दो तीन है
  * note: raw-harness error is punctuation only (danda counted as a character)
* `audio/hi_02.wav` — PASS (automated); CER raw 0.045 / clean 0.000, WER clean 0.000; 2.24s, RMS -23.55 dBFS, peak -6.42 dBFS, clipped 0.000%, voiced 64%, voice-band 99.3%, telephone-band 90%, >3.4kHz 1.43%, centroid 800 Hz; render 372 ms, ASR 399 ms
  * ref: कल शाम तक डिलीवरी हो जाएगी।
  * heard: कल शाम तक डिलीवरी हो जाएगी
  * note: raw-harness error is punctuation only (danda counted as a character)
* `audio/hi_03.wav` — PARTIAL; CER raw 0.211 / clean 0.167, WER clean 0.200; 1.79s, RMS -23.67 dBFS, peak -8.45 dBFS, clipped 0.000%, voiced 63%, voice-band 99.7%, telephone-band 76%, >3.4kHz 0.45%, centroid 654 Hz; render 266 ms, ASR 588 ms
  * ref: मेरा पता दिल्ली में है।
  * heard: म पता दिल्ली में है

### gu — PASS (automated)

* `audio/gu_01.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 3.19s, RMS -23.41 dBFS, peak -6.91 dBFS, clipped 0.000%, voiced 56%, voice-band 99.6%, telephone-band 81%, >3.4kHz 0.42%, centroid 735 Hz; render 642 ms, ASR 1926 ms
  * ref: મારો ઓર્ડર નંબર એક બે ત્રણ છે.
  * heard: મારો ઓર્ડર નંબર એક બે ત્રણ છે
* `audio/gu_02.wav` — PASS (automated); CER raw 0.037 / clean 0.037, WER clean 0.167; 2.54s, RMS -23.49 dBFS, peak -5.46 dBFS, clipped 0.000%, voiced 78%, voice-band 97.5%, telephone-band 86%, >3.4kHz 2.67%, centroid 1017 Hz; render 762 ms, ASR 1768 ms
  * ref: કાલે સાંજ સુધીમાં ડિલિવરી થઈ જશે.
  * heard: કાલે સાંજ સુધીમાં ડિલવરી થઈ જશે
* `audio/gu_03.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.15s, RMS -23.57 dBFS, peak -8.4 dBFS, clipped 0.000%, voiced 80%, voice-band 99.1%, telephone-band 82%, >3.4kHz 1.17%, centroid 802 Hz; render 330 ms, ASR 1864 ms
  * ref: મારું સરનામું અમદાવાદમાં છે.
  * heard: મારું સરનામું અમદાવાદમાં છે

### mr — PASS (automated)

* `audio/mr_01.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 3.43s, RMS -23.39 dBFS, peak -7.88 dBFS, clipped 0.000%, voiced 64%, voice-band 98.9%, telephone-band 76%, >3.4kHz 1.29%, centroid 688 Hz; render 931 ms, ASR 2375 ms
  * ref: माझा ऑर्डर नंबर एक दोन तीन आहे.
  * heard: माझा ऑर्डर नंबर एक दोन तीन आहे
* `audio/mr_02.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 3.12s, RMS -23.42 dBFS, peak -9.12 dBFS, clipped 0.000%, voiced 72%, voice-band 97.4%, telephone-band 64%, >3.4kHz 2.10%, centroid 646 Hz; render 491 ms, ASR 2126 ms
  * ref: उद्या संध्याकाळपर्यंत डिलिव्हरी होईल.
  * heard: उद्या संध्याकाळपर्यंत डिलिव्हरी होईल
* `audio/mr_03.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.06s, RMS -23.59 dBFS, peak -7.86 dBFS, clipped 0.000%, voiced 59%, voice-band 98.0%, telephone-band 74%, >3.4kHz 1.68%, centroid 794 Hz; render 412 ms, ASR 1451 ms
  * ref: माझा पत्ता पुण्यात आहे.
  * heard: माझा पत्ता पुण्यात आहे

### bn — PARTIAL

* `audio/bn_01.wav` — PARTIAL; CER raw 0.208 / clean 0.174, WER clean 0.333; 2.46s, RMS -23.5 dBFS, peak -3.54 dBFS, clipped 0.000%, voiced 62%, voice-band 99.5%, telephone-band 89%, >3.4kHz 1.65%, centroid 878 Hz; render 747 ms, ASR 3507 ms
  * ref: আমার অর্ডার নম্বর এক দুই তিন।
  * heard: আমার অর্ডার ন্বর এক তিন
* `audio/bn_02.wav` — PASS (automated); CER raw 0.036 / clean 0.000, WER clean 0.000; 2.27s, RMS -23.54 dBFS, peak -0.52 dBFS, clipped 0.000%, voiced 74%, voice-band 98.6%, telephone-band 79%, >3.4kHz 1.96%, centroid 802 Hz; render 2072 ms, ASR 2431 ms
  * ref: কাল সন্ধ্যার মধ্যে ডেলিভারি হবে।
  * heard: কাল সন্ধ্যার মধ্যে ডেলিভারি হবে
  * note: raw-harness error is punctuation only (danda counted as a character)
* `audio/bn_03.wav` — PASS (automated); CER raw 0.053 / clean 0.000, WER clean 0.000; 1.71s, RMS -23.69 dBFS, peak -5.7 dBFS, clipped 0.000%, voiced 53%, voice-band 98.8%, telephone-band 90%, >3.4kHz 1.91%, centroid 911 Hz; render 912 ms, ASR 2379 ms
  * ref: আমার ঠিকানা কলকাতায়।
  * heard: আমার ঠিকানা কলকাতায়
  * note: raw-harness error is punctuation only (danda counted as a character)

### ta — PASS (automated)

* `audio/ta_01.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.43s, RMS -23.51 dBFS, peak -7.62 dBFS, clipped 0.000%, voiced 71%, voice-band 98.8%, telephone-band 70%, >3.4kHz 0.56%, centroid 495 Hz; render 888 ms, ASR 2368 ms
  * ref: என் ஆர்டர் எண் ஒன்று இரண்டு மூன்று.
  * heard: என் ஆர்டர் எண் ஒன்று இரண்டு மூன்று
* `audio/ta_02.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.24s, RMS -23.55 dBFS, peak -5.36 dBFS, clipped 0.000%, voiced 68%, voice-band 99.5%, telephone-band 83%, >3.4kHz 0.52%, centroid 651 Hz; render 686 ms, ASR 2309 ms
  * ref: நாளை மாலைக்குள் டெலிவரி ஆகும்.
  * heard: நாளை மாலைக்குள் டெலிவரி ஆகும்
* `audio/ta_03.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 1.95s, RMS -23.62 dBFS, peak -6.53 dBFS, clipped 0.000%, voiced 69%, voice-band 99.2%, telephone-band 73%, >3.4kHz 0.91%, centroid 491 Hz; render 463 ms, ASR 1918 ms
  * ref: என் முகவரி சென்னையில் உள்ளது.
  * heard: என் முகவரி சென்னையில் உள்ளது

### te — FAIL

* `audio/te_01.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 3.00s, RMS -23.43 dBFS, peak -3.34 dBFS, clipped 0.000%, voiced 53%, voice-band 99.2%, telephone-band 89%, >3.4kHz 1.69%, centroid 771 Hz; render 474 ms, ASR 1562 ms
  * ref: నా ఆర్డర్ నంబర్ ఒకటి రెండు మూడు.
  * heard: నా ఆర్డర్ నంబర్ ఒకటి రెండు మూడు
* `audio/te_02.wav` — FAIL; CER raw 0.000 / clean 0.000, WER clean 0.000; 2.54s, RMS -23.49 dBFS, peak -5.14 dBFS, clipped 0.000%, voiced 69%, voice-band 95.0%, telephone-band 87%, >3.4kHz 6.63%, centroid 1020 Hz; render 517 ms, ASR 2007 ms
  * ref: రేపు సాయంత్రం వరకు డెలివరీ అవుతుంది.
  * heard: రేపు సాయంత్రం వరకు డెలివరీ అవుతుంది
  * signal gate fails: high_frequency_noise
* `audio/te_03.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.21s, RMS -23.55 dBFS, peak -4.65 dBFS, clipped 0.000%, voiced 70%, voice-band 98.0%, telephone-band 91%, >3.4kHz 2.51%, centroid 918 Hz; render 873 ms, ASR 3766 ms
  * ref: నా చిరునామా హైదరాబాద్‌లో ఉంది.
  * heard: నా చిరునామా హైదరాబాద్ లో ఉంది

### kn — PASS (automated)

* `audio/kn_01.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 3.02s, RMS -23.43 dBFS, peak -10.58 dBFS, clipped 0.000%, voiced 74%, voice-band 99.7%, telephone-band 49%, >3.4kHz 0.35%, centroid 408 Hz; render 1145 ms, ASR 3660 ms
  * ref: ನನ್ನ ಆರ್ಡರ್ ನಂಬರ್ ಒಂದು ಎರಡು ಮೂರು.
  * heard: ನನ್ನ ಆರ್ಡರ್ ನಂಬರ್ ಒಂದು ಎರಡು ಮೂರು
* `audio/kn_02.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 3.05s, RMS -23.42 dBFS, peak -9.31 dBFS, clipped 0.000%, voiced 74%, voice-band 98.8%, telephone-band 59%, >3.4kHz 1.20%, centroid 514 Hz; render 1034 ms, ASR 4298 ms
  * ref: ನಾಳೆ ಸಂಜೆಯೊಳಗೆ ಡೆಲಿವರಿ ಆಗುತ್ತದೆ.
  * heard: ನಾಳೆ ಸಂಜೆಯೊಳಗೆ ಡೆಲಿವರಿ ಆಗುತ್ತದೆ
* `audio/kn_03.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.54s, RMS -23.49 dBFS, peak -11.45 dBFS, clipped 0.000%, voiced 76%, voice-band 99.3%, telephone-band 46%, >3.4kHz 0.67%, centroid 416 Hz; render 1862 ms, ASR 3287 ms
  * ref: ನನ್ನ ವಿಳಾಸ ಬೆಂಗಳೂರಿನಲ್ಲಿದೆ.
  * heard: ನನ್ನ ವಿಳಾಸ ಬೆಂಗಳೂರಿನಲ್ಲಿದೆ

### ml — PARTIAL

* `audio/ml_01.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.47s, RMS -23.5 dBFS, peak -8.69 dBFS, clipped 0.000%, voiced 75%, voice-band 99.9%, telephone-band 57%, >3.4kHz 0.20%, centroid 472 Hz; render 746 ms, ASR 3666 ms
  * ref: എന്റെ ഓർഡർ നമ്പർ ഒന്ന് രണ്ട് മൂന്ന്.
  * heard: എന്റെ ഓർഡർ നമ്പർ ഒന്ന് രണ്ട് മൂന്ന്
* `audio/ml_02.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.63s, RMS -23.48 dBFS, peak -6.93 dBFS, clipped 0.000%, voiced 77%, voice-band 99.7%, telephone-band 61%, >3.4kHz 0.52%, centroid 624 Hz; render 1319 ms, ASR 4776 ms
  * ref: നാളെ വൈകുന്നേരത്തിനുള്ളിൽ ഡെലിവറി ആകും.
  * heard: നാളെ വൈകുന്നേരത്തിനുള്ളിൽ ഡെലിവറി ആകും
* `audio/ml_03.wav` — PARTIAL; CER raw 0.087 / clean 0.087, WER clean 0.333; 1.54s, RMS -23.77 dBFS, peak -9.17 dBFS, clipped 0.000%, voiced 77%, voice-band 99.3%, telephone-band 48%, >3.4kHz 0.88%, centroid 477 Hz; render 819 ms, ASR 3788 ms
  * ref: എന്റെ വിലാസം കൊച്ചിയിലാണ്.
  * heard: എറെ വിലാസം കൊച്ചിയിലാണ്

### pa — PASS (automated)

* `audio/pa_01.wav` — PASS (automated); CER raw 0.042 / clean 0.000, WER clean 0.000; 3.19s, RMS -23.41 dBFS, peak -5.83 dBFS, clipped 0.000%, voiced 54%, voice-band 99.7%, telephone-band 91%, >3.4kHz 0.33%, centroid 682 Hz; render 2562 ms, ASR 4559 ms
  * ref: ਮੇਰਾ ਆਰਡਰ ਨੰਬਰ ਇੱਕ ਦੋ ਤਿੰਨ ਹੈ।
  * heard: ਮੇਰਾ ਆਰਡਰ ਨੰਬਰ ਇੱਕ ਦੋ ਤਿੰਨ ਹੈ
  * note: raw-harness error is punctuation only (danda counted as a character)
* `audio/pa_02.wav` — PASS (automated); CER raw 0.036 / clean 0.000, WER clean 0.000; 2.45s, RMS -23.51 dBFS, peak -4.34 dBFS, clipped 0.000%, voiced 66%, voice-band 97.9%, telephone-band 87%, >3.4kHz 2.50%, centroid 996 Hz; render 1606 ms, ASR 3554 ms
  * ref: ਕੱਲ੍ਹ ਸ਼ਾਮ ਤੱਕ ਡਿਲੀਵਰੀ ਹੋ ਜਾਵੇਗੀ।
  * heard: ਕੱਲ੍ਹ ਸ਼ਾਮ ਤੱਕ ਡਿਲੀਵਰੀ ਹੋ ਜਾਵੇਗੀ
  * note: raw-harness error is punctuation only (danda counted as a character)
* `audio/pa_03.wav` — PASS (automated); CER raw 0.048 / clean 0.000, WER clean 0.000; 2.49s, RMS -23.5 dBFS, peak -5.53 dBFS, clipped 0.000%, voiced 50%, voice-band 98.9%, telephone-band 82%, >3.4kHz 0.88%, centroid 692 Hz; render 1388 ms, ASR 3312 ms
  * ref: ਮੇਰਾ ਪਤਾ ਲੁਧਿਆਣਾ ਵਿੱਚ ਹੈ।
  * heard: ਮੇਰਾ ਪਤਾ ਲੁਧਿਆਣਾ ਵਿੱਚ ਹੈ
  * note: raw-harness error is punctuation only (danda counted as a character)

### or — PASS (automated)

* `audio/or_01.wav` — PASS (automated); CER raw 0.045 / clean 0.000, WER clean 0.000; 2.77s, RMS -23.46 dBFS, peak -5.6 dBFS, clipped 0.000%, voiced 54%, voice-band 99.7%, telephone-band 90%, >3.4kHz 0.28%, centroid 649 Hz; render 370 ms, ASR 1330 ms
  * ref: ମୋ ଅର୍ଡର ନମ୍ବର ଏକ ଦୁଇ ତିନି।
  * heard: ମୋ ଅର୍ଡର ନମ୍ବର ଏକ ଦୁଇ ତିନି
  * note: raw-harness error is punctuation only (danda counted as a character)
* `audio/or_02.wav` — PASS (automated); CER raw 0.036 / clean 0.000, WER clean 0.000; 2.38s, RMS -23.52 dBFS, peak -5.82 dBFS, clipped 0.000%, voiced 70%, voice-band 98.9%, telephone-band 74%, >3.4kHz 1.26%, centroid 627 Hz; render 329 ms, ASR 1412 ms
  * ref: କାଲି ସନ୍ଧ୍ୟା ସୁଦ୍ଧା ଡେଲିଭରି ହେବ।
  * heard: କାଲି ସନ୍ଧ୍ୟା ସୁଦ୍ଧା ଡେଲିଭରି ହେବ
  * note: raw-harness error is punctuation only (danda counted as a character)
* `audio/or_03.wav` — PASS (automated); CER raw 0.136 / clean 0.095, WER clean 0.250; 2.73s, RMS -23.46 dBFS, peak -7.02 dBFS, clipped 0.000%, voiced 57%, voice-band 97.3%, telephone-band 88%, >3.4kHz 1.72%, centroid 719 Hz; render 334 ms, ASR 1608 ms
  * ref: ମୋ ଠିକଣା ଭୁବନେଶ୍ୱରରେ ଅଛି।
  * heard: ମୋ ଠିକ ଭୁବନେଶ୍ୱରରେ ଅଛି

### as — PARTIAL

* `audio/as_01.wav` — PARTIAL; CER raw 0.292 / clean 0.261, WER clean 0.667; 2.59s, RMS -23.48 dBFS, peak -7.5 dBFS, clipped 0.000%, voiced 67%, voice-band 99.6%, telephone-band 69%, >3.4kHz 0.56%, centroid 625 Hz; render 629 ms, ASR 3399 ms
  * ref: মোৰ অৰ্ডাৰ নম্বৰ এক দুই তিনি।
  * heard: মোর অর্ডার নম্বার এক দুই তিনই
* `audio/as_02.wav` — PARTIAL; CER raw 0.300 / clean 0.276, WER clean 1.000; 2.38s, RMS -23.52 dBFS, peak -3.71 dBFS, clipped 0.000%, voiced 75%, voice-band 98.0%, telephone-band 64%, >3.4kHz 1.04%, centroid 638 Hz; render 534 ms, ASR 1949 ms
  * ref: কাইলৈ সন্ধিয়াৰ ভিতৰত ডেলিভাৰী হ'ব।
  * heard: কাইলে সন্ধ্যি ভিতরত ডেলিভারি হব
* `audio/as_03.wav` — PARTIAL; CER raw 0.333 / clean 0.300, WER clean 0.750; 1.88s, RMS -23.64 dBFS, peak -6.6 dBFS, clipped 0.000%, voiced 64%, voice-band 97.1%, telephone-band 64%, >3.4kHz 2.82%, centroid 711 Hz; render 433 ms, ASR 1240 ms
  * ref: মোৰ ঠিকনা গুৱাহাটীত আছে।
  * heard: মোর ঠিকোনা গয়াহাটি আছে

### en — FAIL

* `audio/en_01.wav` — PARTIAL; CER raw 0.423 / clean 0.423, cer_itn 0.000, WER clean 0.429; 2.45s, RMS -23.51 dBFS, peak -7.75 dBFS, clipped 0.000%, voiced 67%, voice-band 98.7%, telephone-band 70%, >3.4kHz 1.21%, centroid 664 Hz; render 341 ms, ASR 1102 ms
  * ref: My order number is one two three.
  * heard: My order number is 123.
  * note: miss is whisper digit formatting ('1-2-3' for 'one two three'), not missing speech
* `audio/en_02.wav` — PASS (automated); CER raw 0.000 / clean 0.000, cer_itn 0.000, WER clean 0.000; 2.82s, RMS -23.45 dBFS, peak -6.75 dBFS, clipped 0.000%, voiced 68%, voice-band 99.3%, telephone-band 76%, >3.4kHz 0.64%, centroid 500 Hz; render 437 ms, ASR 1099 ms
  * ref: Delivery will happen before tomorrow evening.
  * heard: Delivery will happen before tomorrow evening.
* `audio/en_03.wav` — FAIL; CER raw 0.000 / clean 0.000, cer_itn 0.000, WER clean 0.000; 1.88s, RMS -23.64 dBFS, peak -7.98 dBFS, clipped 0.000%, voiced 67%, voice-band 88.4%, telephone-band 60%, >3.4kHz 11.26%, centroid 1461 Hz; render 301 ms, ASR 999 ms
  * ref: My address is in Delhi.
  * heard: My address is in Delhi.
  * signal gate fails: high_frequency_noise

## Caveats (read before quoting any number)

* Audio is **TTS-synthesised**, not real recordings. The round-trip shares the synthesis domain and a clean channel, so it flatters the recogniser. These CER/WER values are an intelligibility proxy for the voice, not production ASR accuracy, and they count as 0 real recordings collected.
* Assamese is decoded with the Bengali Conformer (no Assamese ONNX export exists); Bengali orthography in the transcript is expected and scores as errors.
* A low CER proves the recogniser recovered the words; it does not prove naturalness, prosody, or absence of artefacts. Only human listening can judge those: NOT TESTED.
* One render per sentence, single speaker (sid 0), default speed. Run-to-run thermal variance on this 15 W laptop affects the millisecond columns, not the audio.
* Signal gates prove the output is audible speech-band energy, not silence, noise or clipping. They cannot prove the words sound right to a native listener.
