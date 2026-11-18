# 06 — TTS Validation

## Providers implemented

- Indic Tiny TTS (AI4Bharat Rasa, Matcha+Vocos, onnxruntime) — 12 languages, 24 kHz, primary when downloaded.
- Supertonic 3 (INT8, 44.1 kHz) — hi, en only.
- MMS-TTS (sherpa, 16 kHz) — fallback for all 12.

Selection: `config.tts_backend(lang)` → tiny → supertonic → mms. Backend availability checks are MMS-directory-based (D11 open: tiny-only installs misreport readiness).

## Measured (this run)

- TTS RTF p50: hi 0.08, gu 0.09, mr 0.09, bn 0.09, ta 0.10, en 0.12 (tiny).
- TTS ms p50: hi 318.0, gu 496.4, mr 430.0, bn 324.4, ta 335.0, en 502.5.
- All measured clips intelligible to ASR (round-trip CER ≤0.037 except en digit formatting).
- Sample rates: tiny 24 kHz, supertonic 44.1 kHz, MMS 16 kHz; resampled to 16 kHz output.

## Verified

- AudioPlayer/AudioSink mute-after-cancel (F1) + resume() on new turn; cancel checks before _emit.
- Empty-output/clipping not systematically measured.
- Humanizer clause pauses (120–250 ms), sentence pause 220 ms, seam blending implemented.
- Leveling: tiny output ~8 dB quieter, levelled to TINY_TARGET_RMS 0.07.

## Not tested

- MOS / native-speaker naturalness: NOT TESTED (no listeners).
- Pronunciation of numbers/currency/dates/abbreviations/names/technical terms on real ears: NOT TESTED.
- Clipping/distortion/abrupt endings/gaps/overlap: not systematically measured.
- Tiny TTS mid-generation cancel (D10): NOT implemented (cancel only between clauses/sentences).
- Long-response stability beyond MAX_REPLY_SENTENCES=2: not tested.

## Conclusion

TTS generates audio reliably and fast on CPU. Naturalness is unverified by humans. No quality claim beyond synthetic round-trip intelligibility.