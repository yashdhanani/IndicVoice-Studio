# IndicVoice — Capacity Validation (Real-World Validation V2, Phase G)

**Bottom line (honest):** The system is **reliable under concurrency** — 100% of turns
succeeded at 1, 2, 3 and 5 simultaneous sessions, sessions clean up correctly, a
post-load recovery turn succeeds, RSS is stable (no leak) and outbound queues never
back up. But the reference laptop (i7-8565U, 4C/8T, 15 W) is **CPU-bound**: whole-machine
CPU sits at ~100% even at a single session during decode bursts, the server event loop
stalls 0.4–1.7 s (audio would stutter), and perceived latency scales badly with
concurrency. The conservative smooth-audio recommendation is therefore **0 levels meet
the strict bar**; the practical pilot ceiling on this hardware is **1 concurrent session**
for usable (not smooth) latency. Multi-session pilots need stronger hardware.

No production code was changed. A bug in the new CPU sampler was found and fixed
(run 1 preserved as evidence). The 15 W laptop was not overheated or destabilized:
load is bounded (≤5 sessions), with 10 s cooldowns between levels.

Status vocabulary: PASS (automated) / PASS — manually verified / PARTIAL / FAIL /
NOT TESTED / NOT APPLICABLE.

Evidence: `benchmarks/results/realworld_v2/capacity_v2.json` (corrected run),
`capacity_v2_run1_cpu_bug.json` (run 1, CPU sampler bug preserved). Runner:
`benchmarks/run_capacity.py`. Tests: `tests/test_capacity.py` (14).

---

## 1. Method

Levels 1, 2, 3, 5 concurrent sessions × 4 sequential real-time turns each (hi),
real server (real local ASR + Groq LLM + real local TTS), 10 s cooldown between
levels. Three resource axes sampled during each level:

- **System CPU** (`CPUSampler`, GetSystemTimes, whole machine)
- **Server RSS** (`RSSSampler`, follows the venv launcher child)
- **Live gauges** (`GET /metrics` polled at 1 Hz: active sessions, outbound queue
  total/max, ASR executor queue, event-loop delay)

After load: verify `active_sessions → 0` (cleanup) and run one fresh turn (recovery).
Level 10 is intentionally excluded on this 4-core/15 W laptop.

**Caveats:** corpus is TTS-synthesized starter clips (not real recordings); the machine
was thermally loaded from the preceding Phase F matrix, so absolute latencies are
pessimistic (a cooled run in Phase F measured hi idle e2e p50 ~1567 ms vs ~2558 ms here).
CPU-load reflects whole-machine saturation including the measurement client.

## 2. Results

| Level | Turns ok | e2e p50 | e2e p95 | first_audio p50 | asr p50 | CPU peak / mean | loop-delay peak | queue max | RSS |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 4/4 | 2558 | 2872 | 2153 | 1321 | 100 / 98.2 % | 401 ms | 0 | — |
| 2 | 8/8 | 2619 | 6323 | 2210 | 1089 | 100 / 98.7 % | 731 ms | 0 | — |
| 3 | 12/12 | 4312 | 9402 | 3944 | 1317 | 100 / 100 % | 784 ms | 0 | — |
| 5 | 20/20 | 7482 | 15012 | 7067 | 4545 | 100 / 99.9 % | 1690 ms | 1 | — |

Server RSS: **peak 880.6 MB, final 719.7 MB** (stable, 103 samples — no growth trend).
Post-load: **active_sessions 0, cleanup_ok true, recovery_turn_ok true**
(recovery e2e 3698 ms — slow while hot, but functional).

## 3. What works (reliability) — PASS (automated)

- **100% turn success** at every level (4/4, 8/8, 12/12, 20/20). No dropped calls.
- **Session cleanup**: `active_sessions` returns to 0 after load; per-IP slots released.
- **Recovery**: a fresh turn after the full matrix succeeds.
- **Memory stability**: RSS peak 880 MB → final 720 MB; no leak across 44 turns.
- **No queue backpressure**: outbound queue max 0–1; ASR executor queue 0 throughout.
  Audio is delivered as produced; the bottleneck is compute, not buffering.

## 4. What is constrained (performance) — the honest limit

- **CPU saturation at ~100% even at 1 session.** sherpa-onnx ASR uses intra-op
  parallelism across all 4 cores; combined with TTS and the client, the machine is
  maxed during decode bursts regardless of session count.
- **Event-loop stalls 401 ms (1 session) → 1690 ms (5 sessions).** The Python loop
  thread is starved while ONNX holds cores; audio delivery would stutter. Between
  turns the loop is healthy (monitor observed 9–14 ms), so stalls are decode-burst
  bound, not a permanent block.
- **Latency scales badly**: e2e p50 2.5 s → 7.5 s, p95 2.9 s → 15 s from 1 → 5
  sessions; asr p50 1.3 s → 4.5 s as decodes compete for cores.

## 5. Conservative capacity recommendation

The recommendation logic (`capacity_recommendation`, tested) marks a level safe only
if **100% success AND event-loop delay < 250 ms AND CPU peak < 95 %**, taking the highest
contiguous safe level from 1. Result:

```
recommended_max_concurrency = 0
measured_levels = [1, 2, 3, 5]   safe_levels = []
```

**Interpretation (not "the system is broken"):** no level meets the *smooth-audio* bar
on this CPU-only 15 W laptop, because decode bursts saturate cores and stall the loop.
The system still **completes every call**. Practical guidance:

- **This hardware:** pilot at **1 concurrent session** for usable latency; expect
  occasional stutter during decode. Do not run multi-session pilots here.
- **Reliability ceiling measured:** 5 concurrent sessions complete without failure —
  useful headroom for *correctness*, not for *latency*.
- The threshold was **not** lowered to manufacture a passing number.

## 6. Scaling guidance (analysis — not applied)

The bottleneck is **CPU**, not memory, queues, or session handling. To scale concurrency:

| Lever | Effect | Cost / risk |
|---|---|---|
| More physical cores / higher-TDP host | directly reduces decode contention and loop stalls | hardware cost |
| Cap ONNX intra-op threads (leave loop headroom) | fewer loop stalls, slower per-decode | tuning; production change, needs A/B |
| Separate ASR / TTS worker processes | isolates GIL/CPU contention | complexity; shared ticket store needed |
| Horizontal scaling behind a load balancer | linear session capacity | multi-worker ticket store (DEPLOYMENT_V1) |
| GPU offload | large decode speedup | **out of scope** — V1 forbids a GPU dependency |

Do **not** raise queue/session caps to hide saturation; that converts stalls into
backpressure and dropped audio. Do not lower endpoint silence to fake latency gains.

## 7. Incident during this phase (recorded, not hidden)

Run 1's `CPUSampler._read` referenced `ctypes` (imported only locally in `__init__`),
raising `NameError` in the sampler thread → `cpu_peak=None`. Fixed to use `self._ctypes`;
added `CPUSamplerTests` (read returns valid counters; sampler produces samples) so the
regression is caught. Run 1 is preserved as `capacity_v2_run1_cpu_bug.json`; the corrected
re-run is `capacity_v2.json`. Run 1 also showed an extreme level-1 loop-delay spike
(2886 ms) consistent with thermal/cold-start immediately after Phase F; the corrected,
cooled re-run shows 401 ms.

## 8. Acceptance gate (concurrency / capacity)

**PARTIAL.** Reliability under concurrency is PASS (automated): 100% success through 5
sessions, cleanup, recovery, memory stability, no backpressure. Performance capacity is
**constrained** on the reference hardware (CPU-bound, loop stalls); the conservative
smooth-audio recommendation is 0 and the practical pilot ceiling is 1 session. Real-recording
and stronger-hardware capacity are NOT TESTED. Higher levels (10) were not run, to avoid
destabilizing the 15 W laptop.