# INDICVOICE — FINAL SPEECH-TO-SPEECH LAUNCH ASSESSMENT

**Final verdict: READY FOR INTERNAL ALPHA**

## 1. What actually works

- Cascaded STS pipeline (ASR→LLM→TTS) over WebSocket, 12 languages configured.
- VAD + endpointing + streaming ASR with speculative decode and staleness guard.
- Language switching by script with Latin-evidence gate (≥3 words).
- LLM response generation (Groq gpt-oss-20b, reasoning low) with 2-sentence cap.
- TTS via tiny/supertonic/MMS with humanizer + seam blending.
- Barge-in with sink mute-after-cancel + resume on new turn.
- Security controls for trusted networks (token, origin, limits, TLS self-signed).
- 186 automated tests passing.

## 2. What was tested

- Full unit/integration/WS suite: 186 OK (137.4 s).
- Stage bench (synthetic): 6 languages measured (hi, gu, mr, bn, ta, en); VAD, TTS RTF, ASR CER, RSS.
- E2E latency: hi + en, 2×40 live turns (p50/p90/p95).
- Concurrency: 1/2/3/5 sessions (33/33 turns).
- Streaming vs block ASR parity: 12 languages (synthetic, prior report).
- LLM script consistency: 12 languages.
- Security controls: automated (tests/test_security_revalidate, test_xss, test_lan_tls_check).

## 3. What failed

- E2E latency 300–500 ms target NOT met (p50 1.1–1.9 s, p95 2.8–7.1 s).
- Gujarati VAD turn split (1 split) on synthetic clip.
- en ASR CER 0.216 (digit formatting).
- as ASR CER 0.268 (Bengali alias).

## 4. What was fixed (this engagement)

- F1 sink mute-after-cancel (AudioSink._accepting + resume; cancel checks before _emit).
- F2 Latin-switch evidence gate (_LATIN_SWITCH_MIN_WORDS = 3).
- F3 per-turn endpoint retune (CallSession._endpoint_override, _retune_endpoint()).
- 10 new regression tests; all pass.

## 5. What remains unresolved

- F4 Gujarati VAD split (needs real recordings).
- D7, D8, D9, D10, D11, D12, D13, D14, D15–D21 (see 13_known_issues.md).
- Real corpus 0/240; human MOS not done; physical mic/phone not tested; CI not executed on GitHub.

## 6. All 12 language results

See 04_language_quality_matrix.md. Synthetic round-trip only. No language validated on real human speech. te/kn/ml/pa/or/as lack stage-bench coverage in this run.

## 7. Real end-to-end latency

hi p50 1130 ms / p95 2766 ms (run2); en p50 1264 ms / p95 2887 ms (run2). See 08_latency_analysis.md.

## 8. p50, p90, p95

hi: p50 1130.1, p90 1937.2, p95 2766.2 ms (run2). en: p50 1264.2, p90 1589.8, p95 2886.6 ms (run2).

## 9. CPU and RAM

RSS ~1.3 GB with models loaded; safe concurrency ≤2–3 calls on i7-8565U. See 11_cpu_memory_analysis.md.

## 10. Tested concurrency

1/2/3/5 sessions (33/33 turns OK). Level 10+ not tested.

## 11. Security status

Trusted-network adequate with token + TLS. Self-signed TLS; no public-internet hardening. See 10_security_audit.md.

## 12. Human evaluation status

NOT TESTED. No native speakers, no MOS study, no real recordings.

## 13. Critical deployment blockers

- E2E latency far above 300–500 ms target.
- No real-world accuracy evidence (0/240 recordings).
- No physical device validation.
- Self-signed TLS / no public-internet hardening.
- Assamese weak ASR (0.268 synthetic CER).

## 14. Exact steps to reach next launch level (Controlled Pilot)

1. Collect ≥20 real recordings/language (240 total) and re-measure ASR WER/CER.
2. Run E2E latency for all 12 languages (not just hi/en).
3. Physical mic + phone + browser playback validation.
4. Human MOS study with ≥10 listeners/language.
5. Resolve F4 (Gujarati split) with real recordings.
6. Activate CI on a remote; verify fast + model tiers.
7. Multi-hour soak at 2–3 concurrent calls.
8. Improve E2E latency (LLM TTFT, endpointing) — roadmap P4.

## GO / NO-GO checklist

- [NO-GO] Production public deployment: blockers above.
- [GO] Internal alpha / development use on trusted network with token.
- [NO-GO] Controlled pilot: device tests + real corpus outstanding.
- [NO-GO] Production ready: not met.