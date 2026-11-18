# 13 — Known Issues (open)

## Critical / high

1. F4 Gujarati VAD turn split: synthetic clip (5.45 s) splits into 2 turns despite 0.2 s max true silence < endpoint 0.26 s. Needs real recordings before tuning. OPEN.
2. E2E latency p95 2.8–7.1 s; 300–500 ms target NOT met (structural).
3. Assamese ASR CER 0.268 (Bengali-model alias); native export path exists but no model present.
4. English ASR CER 0.141 driven by one clip (digit formatting).
5. No real human recordings (0/240); real-world accuracy unvalidated.
6. No physical microphone / phone / browser playback tested.
7. No human MOS / naturalness study.

## Medium

8. D7 `_HALLUCINATIONS` contains "एक" → drops real "one" answers.
9. D8 idle watchdog counts inbound only (long replies/holds).
10. D9 barge-in race with keep-alive LLM socket (suspected, unverified).
11. D10 tiny TTS ignores cancel mid-generation.
12. D11 backend-availability checks MMS-only.
13. D12 Latin loanwords dropped/mispronounced in 8 languages.
14. D13 sender thread-pool pressure under concurrency.
15. D14 no per-message rate limit / ticket lockout.
16. D18 `.gitignore` ignores `tools/`.
17. D19 agent.marks race (cosmetic).
18. D20 AudioSink.is_speaking wall-clock estimate.
19. D21 hi/mr and bn/as script-indistinguishable.

## Low / hygiene

20. D15 stale comment in config (endpoint 0.45 vs 0.26).
21. D16 docstring barge-in "well under 200 ms" vs actual 0.45 s.
22. D17 requirements.txt unused deps (num2words, indic-nlp-library absent).
23. D4 no git remote (no CI execution).
24. Observability: no structured logs, turn IDs, metrics export, alerting.

## Stage-bench tooling gap

25. `run_stage_bench.PHRASES` only defines 6 languages (hi, en, gu, ta, mr, bn); te/kn/ml/pa/or/as skipped in this run. Not an engine failure but a coverage gap.