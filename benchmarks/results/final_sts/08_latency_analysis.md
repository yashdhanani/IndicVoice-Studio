# 08 — Latency Analysis

## Measurements (live E2E, 2×40 turns, single session, controlled load)

Source: `docs/INDICVOICE_E2E_LATENCY_REPORT.md`, `benchmarks/results/production_v1/e2e_v1.json`.

| Lang | Run | n | E2E client p50 ms | p90 | p95 | max | failed |
|---|---|---|---|---|---|---|---|
| hi | 1 | 20 | 1882.8 | 4300.1 | 7052.8 | 7052.8 | 0 |
| hi | 2 | 20 | 1130.1 | 1937.2 | 2766.2 | 2766.2 | 0 |
| en | 1 | 20 | 1195.8 | 1351.5 | 1416.4 | 1416.4 | 0 |
| en | 2 | 20 | 1264.2 | 1589.8 | 2886.6 | 2886.6 | 0 |

- `e2e_client_ms` = last speech frame sent → first reply audio byte received (includes endpoint silence + transport).
- `first_audio_ms` (server) p50: hi 806 (run2), en 1084 (run2).
- Stage p50 (run2): hi asr 0.9, llm 512, tts 214; en asr 467, llm 943, tts 115.
- Memory peak: 845 MB (run2, hi+en warmed).
- RSS stage-bench end: 1344.4 MB.

## Stage-level (synthetic, this run)

- VAD onset: 672–1248 ms; endpoint delay: -2304 to +64 ms.
- TTS RTF: 0.08–0.12 (all measured).
- ASR decode p50: 192.8–1876.8 ms depending on language.

## Verdict on latency target

The brief's 300–500 ms E2E target is **NOT met**. Best case ~750 ms; p50 1.1–1.9 s; p95 2.8–7.1 s (run-dependent, 15 W laptop). Floor is structural: endpoint silence (260–450 ms) + LLM TTFT (280–950 ms) + TTS first sentence (85–215 ms). Sub-500 ms requires native streaming ASR with earlier endpointing and a faster/local LLM (roadmap P4), not a tuning flag.

## Other 10 languages

E2E NOT TESTED. ASR-stage latency only (synthetic). No E2E percentiles available.

## Concurrency

Measured 1/2/3/5 sessions: 33/33 turns OK, RSS stable 732.5 MB; recommended ≤2–3 concurrent calls on reference 4-core laptop. Level 10+ not tested. See `INDICVOICE_CONCURRENCY_REPORT.md`.