# 11 — CPU & Memory Analysis

## Target machine

Intel i7-8565U (4 cores/8 threads, 15 W), 16 GB RAM, Windows 11, CPU-only, Python 3.13.

## Measured

- Stage-bench process RSS end: 1344.4 MB (all models loaded).
- E2E server working set peak: 845 MB (run2, hi+en warmed).
- Concurrency matrix: 1/2/3/5 sessions, 33/33 turns OK, RSS stable 732.5 MB peak; recommended ≤2–3 concurrent calls.
- Startup/warm-up: `--warm hi en` loads models at start; model loading time not separately measured here.
- ASR threads: STT_NUM_THREADS default 4 (configurable); TTS 2; ASR_WORKERS 2.
- Event-loop health: V3 Phase B (event-driven sender, dedicated ASR pool) — measured in concurrency matrix.

## Not measured / not tested

- Idle memory baseline: not separately captured.
- Long-session memory growth (leak detection): NOT TESTED.
- Audio queue growth under load: NOT TESTED beyond caps.
- >5 concurrent sessions / level 10: NOT TESTED (by design).
- CPU saturation percentages per stage: not captured.
- Model loading time: not measured.

## Conclusion

System fits in ~1.3 GB RAM with models loaded; safe concurrency ≤2–3 calls on the reference laptop. No claim beyond tested capacity.