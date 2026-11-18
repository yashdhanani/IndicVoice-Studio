# Latency Profile (baseline)

## Measured (live E2E, 2×40 turns, single session)

Source: `docs/INDICVOICE_E2E_LATENCY_REPORT.md`.

| Lang | Run | n | E2E client p50 ms | p90 | p95 | max | failed |
|---|---|---|---|---|---|---|---|
| hi | 1 | 20 | 1882.8 | 4300.1 | 7052.8 | 7052.8 | 0 |
| hi | 2 | 20 | 1130.1 | 1937.2 | 2766.2 | 2766.2 | 0 |
| en | 1 | 20 | 1195.8 | 1351.5 | 1416.4 | 1416.4 | 0 |
| en | 2 | 20 | 1264.2 | 1589.8 | 2886.6 | 2886.6 | 0 |

- `e2e_client_ms` = last speech frame sent → first reply audio byte received (includes endpoint silence + transport).
- `first_audio_ms` (server) p50: hi 806 (run2), en 1084 (run2).
- Stage p50 (run2): hi asr 0.9, llm 512, tts 214; en asr 467, llm 943, tts 115.
- 300–500 ms target: NOT met. Floor = endpoint silence (260–450 ms) + LLM TTFT (280–950 ms) + TTS first sentence (85–215 ms).

## Stage-level (synthetic, this run)

- VAD onset: 672–1248 ms; endpoint delay: -2304 to +64 ms.
- TTS RTF: 0.08–0.12.

## Other 10 languages

E2E NOT TESTED. ASR-stage latency only (synthetic).

## Provisional targets (to investigate, not guarantees)

- Aim sub-700 ms hybrid p50 EOU→first-audio; sub-1.2 s p95 under defined realistic test environment.
- If infeasible, explain bottleneck and propose realistic SLO. Current bottleneck: LLM TTFT + endpoint silence.