# IndicVoice human voice-quality — final report (20261117-173537)

Status vocabulary: PASS (automated) / PASS — manually verified / PARTIAL / FAIL / NOT TESTED / NOT APPLICABLE.

## 1. Overall language quality matrix

| lang | round-trip | clean/n | CER clean mean | human naturalness | production readiness |
|---|---|---|---|---|---|
| hi | PARTIAL | 8/9 | 0.106 | NOT TESTED | NOT TESTED — no human evidence |
| gu | PARTIAL | 8/9 | 0.021 | NOT TESTED | NOT TESTED — no human evidence |
| mr | PASS (automated) | 9/9 | 0.0 | NOT TESTED | NOT TESTED — no human evidence |
| bn | PASS (automated) | 9/9 | 0.0 | NOT TESTED | NOT TESTED — no human evidence |
| ta | PASS (automated) | 9/9 | 0.004 | NOT TESTED | NOT TESTED — no human evidence |
| te | PASS (automated) | 9/9 | 0.0 | NOT TESTED | NOT TESTED — no human evidence |
| kn | PASS (automated) | 9/9 | 0.0 | NOT TESTED | NOT TESTED — no human evidence |
| ml | PARTIAL | 5/9 | 0.035 | NOT TESTED | NOT TESTED — no human evidence |
| pa | PASS (automated) | 9/9 | 0.018 | NOT TESTED | NOT TESTED — no human evidence |
| or | PARTIAL | 8/9 | 0.027 | NOT TESTED | NOT TESTED — no human evidence |
| as | PARTIAL | 0/9 | 0.258 | NOT TESTED | NOT TESTED — no human evidence |
| en | PARTIAL | 6/9 | 0.141 | NOT TESTED | NOT TESTED — no human evidence |

## 2. ASR results (synthetic round-trip, local only)

- hi: backend indic, CER clean mean 0.106, worst 0.955, word-miss renders 1.
- gu: backend indic, CER clean mean 0.021, worst 0.111, word-miss renders 1.
- mr: backend indic, CER clean mean 0.0, worst 0.0, word-miss renders 0.
- bn: backend indic, CER clean mean 0.0, worst 0.0, word-miss renders 0.
- ta: backend indic, CER clean mean 0.004, worst 0.034, word-miss renders 0.
- te: backend indic, CER clean mean 0.0, worst 0.0, word-miss renders 0.
- kn: backend indic, CER clean mean 0.0, worst 0.0, word-miss renders 0.
- ml: backend indic, CER clean mean 0.035, worst 0.087, word-miss renders 4.
- pa: backend indic, CER clean mean 0.018, worst 0.074, word-miss renders 0.
- or: backend indic, CER clean mean 0.027, worst 0.048, word-miss renders 1.
- as: backend indic, CER clean mean 0.258, worst 0.3, word-miss renders 9.
- en: backend whisper, CER clean mean 0.141, worst 0.423, word-miss renders 3.

## 3. TTS results

- hi: backend tiny, 9 renders, audible_all=True, mean duration 2.161 s, render RTF 0.171.
- gu: backend tiny, 9 renders, audible_all=True, mean duration 2.633 s, render RTF 0.19.
- mr: backend tiny, 9 renders, audible_all=True, mean duration 2.88 s, render RTF 0.156.
- bn: backend tiny, 9 renders, audible_all=True, mean duration 2.151 s, render RTF 0.169.
- ta: backend tiny, 9 renders, audible_all=True, mean duration 2.21 s, render RTF 0.169.
- te: backend tiny, 9 renders, audible_all=True, mean duration 2.591 s, render RTF 0.143.
- kn: backend tiny, 9 renders, audible_all=True, mean duration 2.881 s, render RTF 0.143.
- ml: backend tiny, 9 renders, audible_all=True, mean duration 2.216 s, render RTF 0.176.
- pa: backend tiny, 9 renders, audible_all=True, mean duration 2.718 s, render RTF 0.132.
- or: backend tiny, 9 renders, audible_all=True, mean duration 2.641 s, render RTF 0.184.
- as: backend tiny, 9 renders, audible_all=True, mean duration 2.292 s, render RTF 0.18.
- en: backend tiny, 9 renders, audible_all=True, mean duration 2.389 s, render RTF 0.173.

## 4. Pronunciation defects (measured candidates, not native-speaker verdicts)

- hi s1 take 1: «मेरा ऑर्डर नंबर एक दो तीन है।» → «म» (CER clean 0.955). words lost or altered in this render
- gu s2 take 2: «કાલે સાંજ સુધીમાં ડિલિવરી થઈ જશે.» → «કાલે સાંજ સુધીમાંડીલીવરી થાઈ જશે» (CER clean 0.111). words lost or altered in this render
- ml s2 take 2: «നാളെ വൈകുന്നേരത്തിനുള്ളിൽ ഡെലിവറി ആകും.» → «നാളെ വൈകുന്നേരത്തിനുള്ളിൽ ഡെലിവറിിയകും» (CER clean 0.057). words lost or altered in this render
- ml s3 take 1: «എന്റെ വിലാസം കൊച്ചിയിലാണ്.» → «എറെ വിലാസം കൊച്ചിയിലാണ്» (CER clean 0.087). words lost or altered in this render
- ml s3 take 2: «എന്റെ വിലാസം കൊച്ചിയിലാണ്.» → «എറെ വിലാസം കൊച്ചിയിലാണ്» (CER clean 0.087). words lost or altered in this render
- ml s3 take 3: «എന്റെ വിലാസം കൊച്ചിയിലാണ്.» → «എറെ വിലാസം കൊച്ചിയിലാണ്» (CER clean 0.087). words lost or altered in this render
- or s3 take 1: «ମୋ ଠିକଣା ଭୁବନେଶ୍ୱରରେ ଅଛି।» → «ମୋଠି କଣ ଭୁବନେଶ୍ୱରରେ ଅଛି» (CER clean 0.048). words lost or altered in this render
- as s1 take 1: «মোৰ অৰ্ডাৰ নম্বৰ এক দুই তিনি।» → «মোর অর্ডার নম্বর এক দুই তিন» (CER clean 0.217). words lost or altered in this render
- as s1 take 2: «মোৰ অৰ্ডাৰ নম্বৰ এক দুই তিনি।» → «মোর অর্ডার নম্বর এক দুই তিনই» (CER clean 0.217). words lost or altered in this render
- as s1 take 3: «মোৰ অৰ্ডাৰ নম্বৰ এক দুই তিনি।» → «মোর অর্ডার নম্বার এক দুই তিনই» (CER clean 0.261). words lost or altered in this render
- as s2 take 1: «কাইলৈ সন্ধিয়াৰ ভিতৰত ডেলিভাৰী হ'ব।» → «কাইল সন্ধ্যিয়ার ভিতরত ডেলিভারি হব» (CER clean 0.241). words lost or altered in this render
- as s2 take 2: «কাইলৈ সন্ধিয়াৰ ভিতৰত ডেলিভাৰী হ'ব।» → «কাইল সন্ধ্যিার ভিতরত ডেলিভারি হব» (CER clean 0.241). words lost or altered in this render
- as s2 take 3: «কাইলৈ সন্ধিয়াৰ ভিতৰত ডেলিভাৰী হ'ব।» → «কাইল সন্ধ্যিার ভিতরত ডেলিভারি হব» (CER clean 0.241). words lost or altered in this render
- as s3 take 1: «মোৰ ঠিকনা গুৱাহাটীত আছে।» → «মোর ঠিকোনা গয়াহাটি আছে» (CER clean 0.3). words lost or altered in this render
- as s3 take 2: «মোৰ ঠিকনা গুৱাহাটীত আছে।» → «মোর ঠিকোন গুয়াহাটিত আছে» (CER clean 0.3). words lost or altered in this render
- as s3 take 3: «মোৰ ঠিকনা গুৱাহাটীত আছে।» → «মোর ঠিকোনা গয়াহাটি আছে» (CER clean 0.3). words lost or altered in this render
- en s1 take 1: «My order number is one two three.» → «My order number is 123.» (CER clean 0.423). miss is whisper digit formatting ('1-2-3' for 'one two three'), not missing speech; words lost or altered in this render
- en s1 take 2: «My order number is one two three.» → «My order number is 1-2-3.» (CER clean 0.423). miss is whisper digit formatting ('1-2-3' for 'one two three'), not missing speech; words lost or altered in this render
- en s1 take 3: «My order number is one two three.» → «My order number is 123.» (CER clean 0.423). miss is whisper digit formatting ('1-2-3' for 'one two three'), not missing speech; words lost or altered in this render

## 5. Prosody and naturalness defects

- NOT TESTED — no human prosody ratings exist. Automated signal gates (audibility, clipping, voice-band coverage) are not naturalness measurements.

## 6. Human evaluation results

- HUMAN DATASET: NOT TESTED (0/240 slots collected, 0 transcripts independently verified).
- Listening responses: 1 files, 1 listeners → PARTIAL.

## 7. MOS

- NOT TESTED. No ITU-T MOS protocol has been run. Listener means, when collected, are labelled 'mean listener rating', never MOS.

## 8. Provider and voice comparison

| lang | selected TTS | tiny | MMS fallback | supertonic eligible | local ASR |
|---|---|---|---|---|---|
| hi | tiny | True | True | True | asr-hi |
| gu | tiny | True | True | False | asr-gu |
| mr | tiny | True | True | False | asr-mr |
| bn | tiny | True | True | False | asr-bn |
| ta | tiny | True | True | False | asr-ta |
| te | tiny | True | True | False | asr-te |
| kn | tiny | True | True | False | asr-kn |
| ml | tiny | True | True | False | asr-ml |
| pa | tiny | True | True | False | asr-pa |
| or | tiny | True | True | False | asr-or |
| as | tiny | True | True | False | asr-bn (bn alias) |
| en | tiny | True | True | True | None |

Selection is unchanged from the frozen V2 configuration; no provider was swapped without measured evidence.

## 9. Latency comparison

- hi: render RTF mean 0.171 (render time / audio duration).
- gu: render RTF mean 0.19 (render time / audio duration).
- mr: render RTF mean 0.156 (render time / audio duration).
- bn: render RTF mean 0.169 (render time / audio duration).
- ta: render RTF mean 0.169 (render time / audio duration).
- te: render RTF mean 0.143 (render time / audio duration).
- kn: render RTF mean 0.143 (render time / audio duration).
- ml: render RTF mean 0.176 (render time / audio duration).
- pa: render RTF mean 0.132 (render time / audio duration).
- or: render RTF mean 0.184 (render time / audio duration).
- as: render RTF mean 0.18 (render time / audio duration).
- en: render RTF mean 0.173 (render time / audio duration).
- End-to-end conversational latency: see historical realworld_v2 artifacts; not re-measured against the live port-8000 process by this console.

## 10. CPU and RAM

- Console process RSS: None MB · logical CPUs: 8.
- Configured STT threads: 4; TTS threads knob: 2 (0 = ORT default).
- Historical capacity evidence: benchmarks/results/realworld_v2 (read-only).

## 11. Regression tests

- PASS (automated) — 161 tests, 0 skipped (log: eval\_regression_now.log).

## 12. Known limitations

- Malayalam എന്റെ heard as എറെ in 3/3 takes (repeatable pronunciation candidate).
- Hindi: 1/9 renders decoded to a single character by the Conformer (decode instability).
- Assamese round-trip confounded by the Bengali Conformer alias.
- English local whisper digit formatting inflates raw CER (digit-expanded CER 0.000).
- Synthesis is non-deterministic across takes.
- Assamese ASR uses the Bengali Conformer alias; round-trip CER is confounded.
- Synthesis is non-deterministic; single-render claims are invalid.

## 13. Recommended next improvements

1. Collect the 240-slot human dataset with consented native speakers (≥5/language).
2. Run blind listening sessions with the prepared packages; score with score_responses.
3. Native-speaker review of the Malayalam എന്റെ pronunciation candidate.
4. Investigate the Hindi Conformer single-character decode collapse.
5. Export a dedicated Assamese ASR model to remove the Bengali alias confound.

## 14. Production readiness by language

- hi (Hindi): automated speech generation partially verified; pronunciation partially validated; human naturalness NOT TESTED; production-ready NOT TESTED.
- gu (Gujarati): automated speech generation partially verified; pronunciation partially validated; human naturalness NOT TESTED; production-ready NOT TESTED.
- mr (Marathi): automated speech generation verified; pronunciation partially validated; human naturalness NOT TESTED; production-ready NOT TESTED.
- bn (Bengali): automated speech generation verified; pronunciation partially validated; human naturalness NOT TESTED; production-ready NOT TESTED.
- ta (Tamil): automated speech generation verified; pronunciation partially validated; human naturalness NOT TESTED; production-ready NOT TESTED.
- te (Telugu): automated speech generation verified; pronunciation partially validated; human naturalness NOT TESTED; production-ready NOT TESTED.
- kn (Kannada): automated speech generation verified; pronunciation partially validated; human naturalness NOT TESTED; production-ready NOT TESTED.
- ml (Malayalam): automated speech generation partially verified; pronunciation partially validated; human naturalness NOT TESTED; production-ready NOT TESTED.
- pa (Punjabi): automated speech generation verified; pronunciation partially validated; human naturalness NOT TESTED; production-ready NOT TESTED.
- or (Odia): automated speech generation partially verified; pronunciation partially validated; human naturalness NOT TESTED; production-ready NOT TESTED.
- as (Assamese): automated speech generation partially verified; pronunciation partially validated; human naturalness NOT TESTED; production-ready NOT TESTED.
- en (English): automated speech generation partially verified; pronunciation partially validated; human naturalness NOT TESTED; production-ready NOT TESTED.

No language is marked production-ready: that claim requires human evidence which does not yet exist.
