# IndicVoice — does the voice speak? (local measured check)

Run: `speak_check_20261117-162153` · generated 2026-11-17 16:25:49 · host CPU-only, no cloud inference, no LLM, no playback on this machine.

## What was measured

Each corpus sentence was rendered through the production playback path (`TTSEngine.render_sentence`, humanised — the same audio the server pushes to the speaker), saved as a mono PCM16 wav, then:

* objective signal health of the saved wav (duration, RMS/peak, clipping, voiced fraction, 300–3400 Hz energy ratio, spectral centroid);
* round-trip through the local production recogniser, CER/WER vs the reference;
* script check on the transcript.

## Two CER/WER columns, and why

* `cer` / `wer` — exactly what `src.evaluate` computes, comparable with earlier eval runs. Its `normalise` keeps U+0964 (danda) because that codepoint sits inside the Devanagari block it preserves, so a *perfect* Hindi transcript still scores about 1/len ≈ 0.04. That is a scoring artifact, not speech error.
* `cer_clean` / `wer_clean` — punctuation and symbols removed by Unicode category before scoring. **The gates use this column.** The production harness was not modified.
* `cer_itn` (English only) — clean CER after expanding whisper's digits back to words (`1-2-3` → `one two three`). Diagnostic only, never used by a gate.

## Gates (engineering thresholds chosen for this check)

```json
{
  "min_duration_s": 0.4,
  "min_rms_dbfs": -35.0,
  "min_voiced_frac": 0.3,
  "max_clip_frac": 0.002,
  "min_speech_band_ratio": 0.5,
  "max_cer_clean": 0.15,
  "max_wer_clean": 0.3
}
```

Status vocabulary: PASS (automated) / PARTIAL / FAIL. **Human listening and MOS: NOT TESTED** — nobody listened to these clips as part of this run; the wavs are packaged so that listening can happen.

## Per-language result

| lang | n | TTS | ASR | CER raw | CER clean | CER clean max | WER clean | mean s | render RTF | audible | status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| hi | 3 | tiny | indic | 0.047 | 0.000 | 0.000 | 0.000 | 2.16 | 0.14 | yes | PASS (automated) |
| gu | 3 | tiny | indic | 0.012 | 0.012 | 0.037 | 0.056 | 2.63 | 0.26 | yes | PASS (automated) |
| mr | 3 | tiny | indic | 0.000 | 0.000 | 0.000 | 0.000 | 2.87 | 0.24 | yes | PASS (automated) |
| bn | 3 | tiny | indic | 0.044 | 0.000 | 0.000 | 0.000 | 2.15 | 0.23 | yes | PASS (automated) |
| ta | 3 | tiny | indic | 0.000 | 0.000 | 0.000 | 0.000 | 2.20 | 0.36 | yes | PASS (automated) |
| te | 3 | tiny | indic | 0.000 | 0.013 | 0.038 | 0.167 | 2.58 | 0.48 | yes | PARTIAL |
| kn | 3 | tiny | indic | 0.000 | 0.000 | 0.000 | 0.000 | 2.87 | 0.20 | NO | FAIL |
| ml | 3 | tiny | indic | 0.029 | 0.029 | 0.087 | 0.111 | 2.21 | 1.53 | NO | FAIL |
| pa | 3 | tiny | indic | 0.042 | 0.000 | 0.000 | 0.000 | 2.71 | 0.15 | yes | PASS (automated) |
| or | 3 | tiny | indic | 0.073 | 0.032 | 0.048 | 0.139 | 2.63 | 0.14 | yes | PASS (automated) |
| as | 3 | tiny | indic | 0.294 | 0.264 | 0.300 | 0.806 | 2.29 | 0.26 | yes | PARTIAL |
| en | 3 | tiny | whisper | 0.141 | 0.141 | 0.423 | 0.143 | 2.38 | 0.14 | yes | PARTIAL |

## Per-clip detail

### hi — PASS (automated)

* `audio/hi_01.wav` — PASS (automated); CER raw 0.043 / clean 0.000, WER clean 0.000; 2.45s, RMS -23.51 dBFS, peak -8.15 dBFS, clipped 0.000%, voiced 67%, speech-band 81%, centroid 633 Hz; render 282 ms, ASR 448 ms
  * ref: मेरा ऑर्डर नंबर एक दो तीन है।
  * heard: मेरा ऑर्डर नंबर एक दो तीन है
  * note: raw-harness error is punctuation only (danda counted as a character)
* `audio/hi_02.wav` — PASS (automated); CER raw 0.045 / clean 0.000, WER clean 0.000; 2.24s, RMS -23.55 dBFS, peak -7.11 dBFS, clipped 0.000%, voiced 66%, speech-band 87%, centroid 763 Hz; render 295 ms, ASR 379 ms
  * ref: कल शाम तक डिलीवरी हो जाएगी।
  * heard: कल शाम तक डिलीवरी हो जाएगी
  * note: raw-harness error is punctuation only (danda counted as a character)
* `audio/hi_03.wav` — PASS (automated); CER raw 0.053 / clean 0.000, WER clean 0.000; 1.79s, RMS -23.67 dBFS, peak -6.56 dBFS, clipped 0.000%, voiced 63%, speech-band 74%, centroid 631 Hz; render 337 ms, ASR 211 ms
  * ref: मेरा पता दिल्ली में है।
  * heard: मेरा पता दिल्ली में है
  * note: raw-harness error is punctuation only (danda counted as a character)

### gu — PASS (automated)

* `audio/gu_01.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 3.19s, RMS -23.41 dBFS, peak -6.29 dBFS, clipped 0.000%, voiced 58%, speech-band 79%, centroid 728 Hz; render 413 ms, ASR 2135 ms
  * ref: મારો ઓર્ડર નંબર એક બે ત્રણ છે.
  * heard: મારો ઓર્ડર નંબર એક બે ત્રણ છે
* `audio/gu_02.wav` — PASS (automated); CER raw 0.037 / clean 0.037, WER clean 0.167; 2.54s, RMS -23.49 dBFS, peak -3.58 dBFS, clipped 0.000%, voiced 78%, speech-band 89%, centroid 1012 Hz; render 628 ms, ASR 1699 ms
  * ref: કાલે સાંજ સુધીમાં ડિલિવરી થઈ જશે.
  * heard: કાલે સાંજ સુધીમાં ડિલીવરી થઈ જશે
* `audio/gu_03.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.15s, RMS -23.57 dBFS, peak -5.52 dBFS, clipped 0.000%, voiced 79%, speech-band 86%, centroid 875 Hz; render 851 ms, ASR 1979 ms
  * ref: મારું સરનામું અમદાવાદમાં છે.
  * heard: મારું સરનામું અમદાવાદમાં છે

### mr — PASS (automated)

* `audio/mr_01.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 3.43s, RMS -23.39 dBFS, peak -6.65 dBFS, clipped 0.000%, voiced 64%, speech-band 76%, centroid 750 Hz; render 650 ms, ASR 2745 ms
  * ref: माझा ऑर्डर नंबर एक दोन तीन आहे.
  * heard: माझा ऑर्डर नंबर एक दोन तीन आहे
* `audio/mr_02.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 3.12s, RMS -23.42 dBFS, peak -9.36 dBFS, clipped 0.000%, voiced 74%, speech-band 64%, centroid 577 Hz; render 678 ms, ASR 3686 ms
  * ref: उद्या संध्याकाळपर्यंत डिलिव्हरी होईल.
  * heard: उद्या संध्याकाळपर्यंत डिलिव्हरी होईल
* `audio/mr_03.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.06s, RMS -23.59 dBFS, peak -6.79 dBFS, clipped 0.000%, voiced 59%, speech-band 59%, centroid 727 Hz; render 624 ms, ASR 3310 ms
  * ref: माझा पत्ता पुण्यात आहे.
  * heard: माझा पत्ता पुण्यात आहे

### bn — PASS (automated)

* `audio/bn_01.wav` — PASS (automated); CER raw 0.042 / clean 0.000, WER clean 0.000; 2.46s, RMS -23.5 dBFS, peak -4.0 dBFS, clipped 0.000%, voiced 60%, speech-band 90%, centroid 876 Hz; render 664 ms, ASR 2652 ms
  * ref: আমার অর্ডার নম্বর এক দুই তিন।
  * heard: আমার অর্ডার নম্বর এক দুই তিন
  * note: raw-harness error is punctuation only (danda counted as a character)
* `audio/bn_02.wav` — PASS (automated); CER raw 0.036 / clean 0.000, WER clean 0.000; 2.27s, RMS -23.54 dBFS, peak -0.99 dBFS, clipped 0.000%, voiced 74%, speech-band 75%, centroid 921 Hz; render 603 ms, ASR 2341 ms
  * ref: কাল সন্ধ্যার মধ্যে ডেলিভারি হবে।
  * heard: কাল সন্ধ্যার মধ্যে ডেলিভারি হবে
  * note: raw-harness error is punctuation only (danda counted as a character)
* `audio/bn_03.wav` — PASS (automated); CER raw 0.053 / clean 0.000, WER clean 0.000; 1.71s, RMS -23.69 dBFS, peak -6.35 dBFS, clipped 0.000%, voiced 53%, speech-band 86%, centroid 921 Hz; render 282 ms, ASR 1882 ms
  * ref: আমার ঠিকানা কলকাতায়।
  * heard: আমার ঠিকানা কলকাতায়
  * note: raw-harness error is punctuation only (danda counted as a character)

### ta — PASS (automated)

* `audio/ta_01.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.43s, RMS -23.51 dBFS, peak -7.68 dBFS, clipped 0.000%, voiced 70%, speech-band 72%, centroid 520 Hz; render 729 ms, ASR 2154 ms
  * ref: என் ஆர்டர் எண் ஒன்று இரண்டு மூன்று.
  * heard: என் ஆர்டர் எண் ஒன்று இரண்டு மூன்று
* `audio/ta_02.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.24s, RMS -23.55 dBFS, peak -4.53 dBFS, clipped 0.000%, voiced 68%, speech-band 83%, centroid 707 Hz; render 1201 ms, ASR 3447 ms
  * ref: நாளை மாலைக்குள் டெலிவரி ஆகும்.
  * heard: நாளை மாலைக்குள் டெலிவரி ஆகும்
* `audio/ta_03.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 1.95s, RMS -23.62 dBFS, peak -6.35 dBFS, clipped 0.000%, voiced 71%, speech-band 73%, centroid 542 Hz; render 451 ms, ASR 2656 ms
  * ref: என் முகவரி சென்னையில் உள்ளது.
  * heard: என் முகவரி சென்னையில் உள்ளது

### te — PARTIAL

* `audio/te_01.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 3.00s, RMS -23.43 dBFS, peak -0.36 dBFS, clipped 0.000%, voiced 53%, speech-band 89%, centroid 763 Hz; render 741 ms, ASR 3386 ms
  * ref: నా ఆర్డర్ నంబర్ ఒకటి రెండు మూడు.
  * heard: నా ఆర్డర్ నంబర్ ఒకటి రెండు మూడు
* `audio/te_02.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.54s, RMS -23.49 dBFS, peak -3.32 dBFS, clipped 0.000%, voiced 67%, speech-band 89%, centroid 1077 Hz; render 2119 ms, ASR 4406 ms
  * ref: రేపు సాయంత్రం వరకు డెలివరీ అవుతుంది.
  * heard: రేపు సాయంత్రం వరకు డెలివరీ అవుతుంది
* `audio/te_03.wav` — PARTIAL; CER raw 0.000 / clean 0.038, WER clean 0.500; 2.21s, RMS -23.55 dBFS, peak -3.58 dBFS, clipped 0.000%, voiced 70%, speech-band 88%, centroid 982 Hz; render 795 ms, ASR 2585 ms
  * ref: నా చిరునామా హైదరాబాద్‌లో ఉంది.
  * heard: నా చిరునామా హైదరాబాద్ లో ఉంది

### kn — FAIL

* `audio/kn_01.wav` — FAIL; CER raw 0.000 / clean 0.000, WER clean 0.000; 3.02s, RMS -23.43 dBFS, peak -9.78 dBFS, clipped 0.000%, voiced 74%, speech-band 47%, centroid 421 Hz; render 941 ms, ASR 2127 ms
  * ref: ನನ್ನ ಆರ್ಡರ್ ನಂಬರ್ ಒಂದು ಎರಡು ಮೂರು.
  * heard: ನನ್ನ ಆರ್ಡರ್ ನಂಬರ್ ಒಂದು ಎರಡು ಮೂರು
  * signal gate fails: speech_band_energy
* `audio/kn_02.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 3.05s, RMS -23.42 dBFS, peak -9.22 dBFS, clipped 0.000%, voiced 75%, speech-band 59%, centroid 550 Hz; render 391 ms, ASR 2230 ms
  * ref: ನಾಳೆ ಸಂಜೆಯೊಳಗೆ ಡೆಲಿವರಿ ಆಗುತ್ತದೆ.
  * heard: ನಾಳೆ ಸಂಜೆಯೊಳಗೆ ಡೆಲಿವರಿ ಆಗುತ್ತದೆ
* `audio/kn_03.wav` — FAIL; CER raw 0.000 / clean 0.000, WER clean 0.000; 2.54s, RMS -23.49 dBFS, peak -10.43 dBFS, clipped 0.000%, voiced 76%, speech-band 47%, centroid 410 Hz; render 385 ms, ASR 1634 ms
  * ref: ನನ್ನ ವಿಳಾಸ ಬೆಂಗಳೂರಿನಲ್ಲಿದೆ.
  * heard: ನನ್ನ ವಿಳಾಸ ಬೆಂಗಳೂರಿನಲ್ಲಿದೆ
  * signal gate fails: speech_band_energy

### ml — FAIL

* `audio/ml_01.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.47s, RMS -23.5 dBFS, peak -8.73 dBFS, clipped 0.000%, voiced 76%, speech-band 59%, centroid 472 Hz; render 1229 ms, ASR 6543 ms
  * ref: എന്റെ ഓർഡർ നമ്പർ ഒന്ന് രണ്ട് മൂന്ന്.
  * heard: എന്റെ ഓർഡർ നമ്പർ ഒന്ന് രണ്ട് മൂന്ന്
* `audio/ml_02.wav` — PASS (automated); CER raw 0.000 / clean 0.000, WER clean 0.000; 2.63s, RMS -23.48 dBFS, peak -8.2 dBFS, clipped 0.000%, voiced 76%, speech-band 59%, centroid 632 Hz; render 2589 ms, ASR 6580 ms
  * ref: നാളെ വൈകുന്നേരത്തിനുള്ളിൽ ഡെലിവറി ആകും.
  * heard: നാളെ വൈകുന്നേരത്തിനുള്ളിൽ ഡെലിവറി ആകും
* `audio/ml_03.wav` — FAIL; CER raw 0.087 / clean 0.087, WER clean 0.333; 1.54s, RMS -23.77 dBFS, peak -10.09 dBFS, clipped 0.000%, voiced 75%, speech-band 41%, centroid 460 Hz; render 4821 ms, ASR 4770 ms
  * ref: എന്റെ വിലാസം കൊച്ചിയിലാണ്.
  * heard: എറെ വിലാസം കൊച്ചിയിലാണ്
  * signal gate fails: speech_band_energy

### pa — PASS (automated)

* `audio/pa_01.wav` — PASS (automated); CER raw 0.042 / clean 0.000, WER clean 0.000; 3.19s, RMS -23.41 dBFS, peak -5.04 dBFS, clipped 0.000%, voiced 58%, speech-band 86%, centroid 695 Hz; render 355 ms, ASR 1545 ms
  * ref: ਮੇਰਾ ਆਰਡਰ ਨੰਬਰ ਇੱਕ ਦੋ ਤਿੰਨ ਹੈ।
  * heard: ਮੇਰਾ ਆਰਡਰ ਨੰਬਰ ਇੱਕ ਦੋ ਤਿੰਨ ਹੈ
  * note: raw-harness error is punctuation only (danda counted as a character)
* `audio/pa_02.wav` — PASS (automated); CER raw 0.036 / clean 0.000, WER clean 0.000; 2.45s, RMS -23.51 dBFS, peak -4.17 dBFS, clipped 0.000%, voiced 66%, speech-band 87%, centroid 1003 Hz; render 438 ms, ASR 2248 ms
  * ref: ਕੱਲ੍ਹ ਸ਼ਾਮ ਤੱਕ ਡਿਲੀਵਰੀ ਹੋ ਜਾਵੇਗੀ।
  * heard: ਕੱਲ੍ਹ ਸ਼ਾਮ ਤੱਕ ਡਿਲੀਵਰੀ ਹੋ ਜਾਵੇਗੀ
  * note: raw-harness error is punctuation only (danda counted as a character)
* `audio/pa_03.wav` — PASS (automated); CER raw 0.048 / clean 0.000, WER clean 0.000; 2.49s, RMS -23.5 dBFS, peak -3.85 dBFS, clipped 0.000%, voiced 49%, speech-band 88%, centroid 736 Hz; render 388 ms, ASR 1153 ms
  * ref: ਮੇਰਾ ਪਤਾ ਲੁਧਿਆਣਾ ਵਿੱਚ ਹੈ।
  * heard: ਮੇਰਾ ਪਤਾ ਲੁਧਿਆਣਾ ਵਿੱਚ ਹੈ
  * note: raw-harness error is punctuation only (danda counted as a character)

### or — PASS (automated)

* `audio/or_01.wav` — PASS (automated); CER raw 0.091 / clean 0.048, WER clean 0.167; 2.77s, RMS -23.46 dBFS, peak -5.85 dBFS, clipped 0.000%, voiced 56%, speech-band 77%, centroid 611 Hz; render 340 ms, ASR 2645 ms
  * ref: ମୋ ଅର୍ଡର ନମ୍ବର ଏକ ଦୁଇ ତିନି।
  * heard: ମୋ ଅର୍ଡ଼ର ନମ୍ବର ଏକ ଦୁଇ ତିନି
* `audio/or_02.wav` — PASS (automated); CER raw 0.036 / clean 0.000, WER clean 0.000; 2.38s, RMS -23.52 dBFS, peak -5.69 dBFS, clipped 0.000%, voiced 70%, speech-band 81%, centroid 838 Hz; render 468 ms, ASR 2555 ms
  * ref: କାଲି ସନ୍ଧ୍ୟା ସୁଦ୍ଧା ଡେଲିଭରି ହେବ।
  * heard: କାଲି ସନ୍ଧ୍ୟା ସୁଦ୍ଧା ଡେଲିଭରି ହେବ
  * note: raw-harness error is punctuation only (danda counted as a character)
* `audio/or_03.wav` — PASS (automated); CER raw 0.091 / clean 0.048, WER clean 0.250; 2.73s, RMS -23.46 dBFS, peak -5.08 dBFS, clipped 0.000%, voiced 58%, speech-band 84%, centroid 642 Hz; render 277 ms, ASR 1660 ms
  * ref: ମୋ ଠିକଣା ଭୁବନେଶ୍ୱରରେ ଅଛି।
  * heard: ମୋ ଠିକଣ ଭୁବନେଶ୍ୱରରେ ଅଛି

### as — PARTIAL

* `audio/as_01.wav` — PARTIAL; CER raw 0.250 / clean 0.217, WER clean 0.667; 2.59s, RMS -23.48 dBFS, peak -7.55 dBFS, clipped 0.000%, voiced 64%, speech-band 69%, centroid 609 Hz; render 399 ms, ASR 1470 ms
  * ref: মোৰ অৰ্ডাৰ নম্বৰ এক দুই তিনি।
  * heard: মোর অর্ডার নম্বর এক দুই তিন
* `audio/as_02.wav` — PARTIAL; CER raw 0.300 / clean 0.276, WER clean 1.000; 2.38s, RMS -23.52 dBFS, peak -2.94 dBFS, clipped 0.000%, voiced 75%, speech-band 69%, centroid 718 Hz; render 1017 ms, ASR 2020 ms
  * ref: কাইলৈ সন্ধিয়াৰ ভিতৰত ডেলিভাৰী হ'ব।
  * heard: কাইল সন্ধ্যি ভিতরত ডেলিভারি হব
* `audio/as_03.wav` — PARTIAL; CER raw 0.333 / clean 0.300, WER clean 0.750; 1.88s, RMS -23.64 dBFS, peak -6.09 dBFS, clipped 0.000%, voiced 63%, speech-band 61%, centroid 784 Hz; render 353 ms, ASR 1258 ms
  * ref: মোৰ ঠিকনা গুৱাহাটীত আছে।
  * heard: মোর ঠিকোন গুয়াহাটিত আছে

### en — PARTIAL

* `audio/en_01.wav` — PARTIAL; CER raw 0.423 / clean 0.423, cer_itn 0.000, WER clean 0.429; 2.45s, RMS -23.51 dBFS, peak -7.69 dBFS, clipped 0.000%, voiced 69%, speech-band 71%, centroid 675 Hz; render 359 ms, ASR 1254 ms
  * ref: My order number is one two three.
  * heard: My order number is 123.
  * note: miss is whisper digit formatting ('1-2-3' for 'one two three'), not missing speech
* `audio/en_02.wav` — PASS (automated); CER raw 0.000 / clean 0.000, cer_itn 0.000, WER clean 0.000; 2.82s, RMS -23.45 dBFS, peak -6.43 dBFS, clipped 0.000%, voiced 68%, speech-band 73%, centroid 498 Hz; render 390 ms, ASR 1291 ms
  * ref: Delivery will happen before tomorrow evening.
  * heard: Delivery will happen before tomorrow evening.
* `audio/en_03.wav` — PASS (automated); CER raw 0.000 / clean 0.000, cer_itn 0.000, WER clean 0.000; 1.88s, RMS -23.64 dBFS, peak -6.17 dBFS, clipped 0.000%, voiced 66%, speech-band 67%, centroid 1395 Hz; render 264 ms, ASR 1010 ms
  * ref: My address is in Delhi.
  * heard: My address is in Delhi.

## Caveats (read before quoting any number)

* Audio is **TTS-synthesised**, not real recordings. The round-trip shares the synthesis domain and a clean channel, so it flatters the recogniser. These CER/WER values are an intelligibility proxy for the voice, not production ASR accuracy, and they count as 0 real recordings collected.
* Assamese is decoded with the Bengali Conformer (no Assamese ONNX export exists); Bengali orthography in the transcript is expected and scores as errors.
* A low CER proves the recogniser recovered the words; it does not prove naturalness, prosody, or absence of artefacts. Only human listening can judge those: NOT TESTED.
* One render per sentence, single speaker (sid 0), default speed. Run-to-run thermal variance on this 15 W laptop affects the millisecond columns, not the audio.
* Signal gates prove the output is audible speech-band energy, not silence, noise or clipping. They cannot prove the words sound right to a native listener.
