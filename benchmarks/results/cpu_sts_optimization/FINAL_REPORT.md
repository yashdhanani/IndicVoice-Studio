# IndicVoice — CPU-Efficient STS Research & Baseline Report

## 1. Original architecture
Modular cascaded STS (ASR → LLM → TTS) over WebSocket. Local VAD/ASR/TTS + Groq LLM. See `benchmarks/results/final_sts/02_actual_architecture.md`.

## 2. Optimized architecture
No architecture change this pass. Architecture A (hybrid) retained. Adaptive routing (C) and full-local (B) deferred.

## 3. Models selected / rejected
- Retained: IndicConformer (local, 12 langs), Groq Whisper (en), tiny/supertonic/MMS TTS, Silero VAD.
- Not adopted (research only, not downloaded): Nemotron, Whisper.cpp, Faster-Whisper, Sarvam, Deepgram, ElevenLabs, IndicF5, Indic-Speak, Indic Parler-TTS, Piper. Reasons: no authorization/keys, no measured evidence, licensing/disk review pending.

## 4. Reason for selections
Current stack has measured RTF 0.07–0.12 and 186 passing tests. No candidate has measured evidence on this hardware/language set. Per project rules, no replacement without measured evidence.

## 5. Research references
`research_review.md` (web research: official docs, model cards, papers, repos). Sources dated 2025–2026.

## 6. All 12 languages and coverage
See `language_support_matrix.md`. No language human-verified. te/kn/ml/pa/or/as lack stage-bench coverage this run.

## 7. ASR accuracy comparison
See `asr_comparison.md`. Synthetic only. Real-world unvalidated.

## 8. TTS naturalness comparison
See `tts_comparison.md`. No human MOS. Synthetic round-trip intelligibility only.

## 9. Human evaluation results
NOT TESTED. See `human_quality_evaluation.md`.

## 10. CPU comparison before/after
No optimization applied. Baseline in `cpu_profile.md`. Before/after file ready for future deltas.

## 11. RAM comparison before/after
Baseline: ~1.3 GB (stage bench), 845 MB (E2E server peak). No change.

## 12. End-to-end latency comparison
Baseline: hi p50 1130.1 / p95 2766.2 ms; en p50 1264.2 / p95 2886.6 ms. Target 300–500 ms NOT met.

## 13. p50, p90, p95
See `latency_profile.md`.

## 14. Audio clarity findings
Synthetic round-trip CER ≤0.037 (except en 0.216 digit formatting). No human clarity assessment.

## 15. Pronunciation findings
NOT TESTED with human listeners.

## 16. Streaming and interruption results
Barge-in 0.45 s sustained VAD; sink mute-after-cancel; 10 turn-taking tests pass. D9 race unverified.

## 17. Regression results
186 tests OK, 137.4 s, exit 0.

## 18. Known limitations
See `benchmarks/results/final_sts/13_known_issues.md` + research gaps in `research_review.md`.

## 19. Rollback instructions
Per-call `?streaming=0`; per-server `--no-streaming`; full code `git revert`. See deployment checklist.

## 20. Final launch recommendation

**Verdict: READY FOR INTERNAL TESTING (research/baseline track).**

No production or pilot claim. Research and baseline audit complete. Optimization work requires authorization for: model downloads, paid API keys, human recording collection, and any architecture changes. Next steps: thread sweep, INT8 vs FP32 benchmark on representative audio, authorized Sarvam/ElevenLabs evaluation, real corpus collection.