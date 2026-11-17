# IndicVoice — Concurrency Report V1 (Production Hardening V1, Phase G)

Date: 2026-11-17 · Harness: `benchmarks/run_concurrency.py`
Raw data: `benchmarks/results/production_v1/concurrency_v1.json`
(+ `concurrency_v1_server.log`).

## Setup

- Real server started by the harness (127.0.0.1:8010, `--warm hi`), real
  local hi ASR + Groq LLM (`openai/gpt-oss-20b`) + Indic Tiny TTS.
- N simultaneous WebSocket sessions, each running 3 sequential real-time
  turns (synthetic starter clips, 20 ms framing + 1 s trailing silence).
  Levels run sequentially with a 3 s settle gap; within a level all
  sessions start together (`asyncio.gather`).
- Hardware: i7-8565U (4 cores / 8 threads, 15 W), 16 GB RAM (~4 GB free),
  Windows 11, Python 3.13. **Level 10 deliberately excluded**: five
  concurrent CPU decodes already saturate this chip; ten would measure
  thermal throttling, not the server. The harness accepts
  `--levels 1 2 3 5 10` for stronger hardware.
- Server working set sampled every 2 s (actual interpreter child process).

## Results

| Level | Turns OK | Success rate | Wall (s) | E2E p50 (ms) | E2E p95 (ms) | ASR p50 (ms) | ASR p95 (ms) |
|---|---|---|---|---|---|---|---|
| 1 | 3/3 | 100% | 17.0 | 1032.7 | 1465.8 | 0.4 | 0.4 |
| 2 | 6/6 | 100% | 19.2 | 1334.1 | 1888.0 | 1.4 | 243.8 |
| 3 | 9/9 | 100% | 24.8 | 1990.1 | 3822.8 | 1.2 | 2376.9 |
| 5 | 15/15 | 100% | 29.1 | 3703.3 | 6649.0 | 1921.0 | 4412.9 |

- **Server RSS peak: 732.5 MB** (hi warmed; final 731.8 MB — no growth
  trend across the matrix; hi+en warm in the E2E benchmark peaked at
  845 MB).
- Zero error events, zero early closes, zero failed turns at every level.
- E2E = client last-speech-frame → first-audio-byte (includes endpoint
  silence); definitions identical to the E2E report.

## Interpretation (honest)

1. **Highest successfully verified level: 5 concurrent sessions** —
   functionally clean (100% turn success, no crashes, no memory growth,
   per-IP limit of 8 not hit).
2. **Functional ≠ usable.** At level 5 the median caller waits 3.7 s for
   first audio (p95 6.6 s) because local ASR decodes queue on 4 physical
   cores; speculative decodes miss their window (ASR p50 jumps from ~1 ms
   to 1921 ms as the cost gate and CPU contention push turns to full
   decode). On this hardware the **recommended production ceiling is 2–3
   concurrent calls** (p50 ≤ 2 s).
3. Degradation is graceful and accuracy-safe: contention delays decodes;
   it never corrupts transcripts (final decode is always full-buffer).
4. The per-IP session cap (8) is above the tested ceiling; a NAT'd office
   with >8 callers would see 4429 — tune `MAX_SESSIONS_PER_IP` consciously,
   it is a constant today.
5. n = 3 turns/session is small; percentiles at level 5 describe this run,
   not a stable distribution. Re-run on target hardware before capacity
   commitments.

## Status

| Item | Status |
|---|---|
| Levels 1/2/3/5, 33/33 turns, RSS series | PASS (automated measurement) |
| Level 10 | NOT TESTED (hardware-unsafe by design on this machine) |
| Mixed-language concurrency | NOT TESTED (hi only) |
| Telephony-path concurrency | NOT TESTED |
| Long-duration (30 min) concurrent soak | NOT TESTED |
| Multi-worker / multi-host scaling | NOT APPLICABLE (single-worker deployment; see DEPLOYMENT_V1) |

## Reproduce

```bash
.venv313/Scripts/python.exe benchmarks/run_concurrency.py --levels 1 2 3 5 --turns 3
```