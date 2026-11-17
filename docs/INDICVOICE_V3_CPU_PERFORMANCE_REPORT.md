# IndicVoice V3 — CPU & Performance Engineering Report (Phase B)

Status key: PASS (automated) / PASS — manually verified / PARTIAL / FAIL / NOT TESTED / NOT APPLICABLE.

All evidence in this report is from **synthetic TTS starter clips** (`eval_data/`) on the
reference laptop (i7-8565U, 4 physical cores / 8 logical, 16 GB, Windows 11, CPU-only,
Python 3.13.18). It describes pipeline behavior on this machine, not real-world acoustic
robustness. IDE/webview background load (17–78% CPU at block start) was present and is
recorded per measurement block; it is a confound, not controlled away.

Artifacts (never overwritten):
- `benchmarks/results/realworld_v3/thread_sweep_v3.json` (microbenchmark sweep + contention)
- `benchmarks/results/realworld_v3/capacity_v3_stt8_ttsdefault.json` (live matrix, V2 thread config)
- `benchmarks/results/realworld_v3/capacity_v3_stt4_tts2.json` (live matrix, 4/2)
- `benchmarks/results/realworld_v3/capacity_v3_stt2_tts2.json` (live matrix, 2/2)

---

## B.1 Root causes investigated (Phase A candidates → verdicts)

| # | Candidate | Verdict | Evidence |
|---|-----------|---------|----------|
| 1 | ONNX intra-op thread oversubscription (STT=8, TTS=ORT default ≈ all cores, on 4 physical cores) | **CONFIRMED — primary** | Sweep §B.2: 2:2 under contention is ~2.6× faster on both stages at 70.6% CPU vs 100% |
| 2 | Sender occupying default-executor workers (`run_in_executor(None, queue.get, 0.2)` per session) | **CONFIRMED** | Each session permanently held 1 of 12 default workers; ASR work queued behind polls. Fixed (§B.3); loop-delay peak at 1 session fell from 401 ms (V2) to 15.1 ms |
| 3 | Quadratic audio-buffer copies in `StreamingSTT.accept` (`np.concatenate` per 32 ms frame) | **CONFIRMED (structural)** | ~3.6 GB cumulative copies for a 60 s utterance; replaced with amortized preallocated storage (§B.3) |
| 4 | Finalize buffer race (latent) | **CONFIRMED by new regression test** | `finalize()` read `self._buf` after its wait loop; concurrent `start()` could swap in the next utterance's audio. Fixed (§B.3) |
| 5 | VAD on the event loop | PARTIAL — per-frame VAD is cheap (Silero on ≤32 ms chunks); loop-delay measurements after fix #2 show ≤15 ms at 1 session. No change made |
| 6 | Speculative streaming net-negative overlap | CONFIRMED in V2; retained as-is per rollback rule. Phase B changes do not alter the streaming decision logic |
| 7 | Model duplication across sessions | NOT A DEFECT — shared STT/TTS caches already dedupe; RSS series shows one growth curve, not per-session copies |

## B.2 Controlled thread sweep (hi, 3 clips × 6 repeats)

ASR solo decode (fresh engine per config, transcripts **byte-identical across all thread counts**):

| STT threads | p50 ms | p90 ms | max ms | CPU during | bg CPU before |
|---|---|---|---|---|---|
| 8 (V2 default) | 351.8 | 676.1 | 912.2 | 99.8% | 28.7% |
| 4 | **146.8** | 162.5 | 176.2 | 77.2% | 30.8% |
| 2 | 226.5 | 246.3 | 246.8 | 56.6% | 19.2% |
| 1 | 362.3 | 389.1 | 573.6 | 47.1% | 30.1% |

TTS solo synthesis (Indic Tiny hi, ~6.16 s audio per sample):

| TTS threads | p50 ms | RTF p50 | CPU during | bg CPU before |
|---|---|---|---|---|
| ORT default (V2) | 672.8 | 0.109 | 98.5% | 27.9% |
| 4 | 657.0 | 0.107 | 97.3% | 46.5% |
| 2 | **607.6** | **0.099** | 57.9% | 17.2% |
| 1 | 780.8 | 0.127 | 28.3% | 21.7% |

Simultaneous contention (ASR decode loop in a worker thread while TTS synthesizes — the real overlap case):

| STT : TTS | ASR p50 ms | ASR p90 ms | TTS p50 ms | TTS p90 ms | CPU during | bg before |
|---|---|---|---|---|---|---|
| 8 : default (V2) | 577.1 | 1210.2 | 1704.8 | 2922.6 | 100.0% | 31.5% |
| 4 : 2 | 269.0 | 412.8 | 1083.5 | 1405.0 | 99.7% | **77.6%** ⚠ |
| 2 : 2 | **224.7** | **235.2** | **628.5** | **687.9** | **70.6%** | 19.4% |

Reading: on 4 physical cores, ~16 compute threads (8 STT + ORT-default TTS) thrash;
2:2 leaves headroom for the event loop, VAD, resampling and the OS. The 4:2 contention
block started under 77.6% background load, so its absolute numbers are pessimistic;
the 2:2 block ran under 19.4%. Direction is consistent with the solo sweeps, but the
live matrix (§B.4) is the deciding evidence.

Accuracy guard: every ASR config produced identical transcripts for all three clips
(`transcripts_identical_to_first_config: true`). Thread count changes scheduling, not decode output.

## B.3 Structural fixes implemented (independent of thread counts)

1. **Event-driven sender** (`src/call_server.py`): replaced the per-session
   `run_in_executor(None, queue.get, 0.2)` polling with an `asyncio.Event` woken via
   `loop.call_soon_threadsafe` from `_put`/`close`. No executor worker is occupied while
   idle; wakeups are immediate instead of up-to-200 ms polls. Regression test asserts
   `loop._default_executor is None` after 50 deliveries from a worker thread.
2. **Dedicated bounded ASR pool** (`ASR_WORKERS=2`, env `INDICVOICE_ASR_WORKERS`):
   streaming finalize and block transcribe run in an app-lifespan-owned
   `ThreadPoolExecutor`, isolated from any default-executor users; shut down with
   `cancel_futures=True` on app exit. Queue depth exposed at `/metrics`
   (`asr_executor_queue`).
3. **Amortized audio buffer** (`src/streaming_stt.py`): preallocated `_storage` with a
   `_buf` view, 2× growth; appends are O(chunk) instead of O(utterance). Exact-content
   regression test over 200 random chunks.
4. **Finalize race fix**: `finalize()` captures the buffer at entry (under the cond)
   before waiting, so a concurrent `start()` for the next utterance can never swap the
   audio out from under the authoritative decode. Found by the new regression test
   `test_finalize_detaches_store_from_next_utterance` (it FAILED before the fix —
   checksum showed the next utterance's audio).

New knobs (`src/config.py`), all env-overridable, exact-V2 rollback =
`INDICVOICE_STT_THREADS=8 INDICVOICE_TTS_THREADS=0`:

| Knob | Env | Meaning |
|---|---|---|
| `STT_NUM_THREADS` | `INDICVOICE_STT_THREADS` | ASR ONNX intra-op threads |
| `TTS_NUM_THREADS` | `INDICVOICE_TTS_THREADS` | Tiny TTS intra-op threads; **0 = ORT default = pre-V3 behavior** |
| `ASR_WORKERS` | `INDICVOICE_ASR_WORKERS` | dedicated ASR pool size |

Tiny TTS thread routing goes through `config.TTS_NUM_THREADS` explicitly (cache key
includes it); sherpa backends are unchanged.

Tests: 13 new tests in `tests/test_v3_performance.py` — all PASS. Existing
streaming/ws/metrics/capacity subset (52 tests) re-run green after the changes.
No existing test was weakened or deleted.

Test-harness defect found and fixed during the combined re-run: the new
`TinyThreadRoutingTests` used `mock.patch.dict(sys.modules, …)`, which on exit
**removes every module first imported inside the context** — including
`sherpa_onnx`, imported by `_build_shared_tts`. sherpa's pybind11 C extension
cannot re-initialise in the same process, so every later `import sherpa_onnx`
raised `type … already registered` and all model-tier WS tests failed
(8 failures + 1 error, logged in `phase_b_retest.log`). Fix: pre-import
`sherpa_onnx` before the patch context so it is part of the snapshot. This was
a test-scaffolding bug, not a product defect — production never patches
`sys.modules`. The combined suite itself is the regression guard.

## B.4 Live capacity matrix (same structural code, three thread configs)

Identical conditions per config: hi, levels 1/2/3/5, 3 turns per session, port 8013,
8 s cooldown, real Groq LLM, real local ASR/TTS, sequential server per config.
Safety basis (unchanged from V2): highest contiguous level with 100% turn success,
event-loop delay <250 ms and CPU peak <95%.

### Config 1 — STT=8, TTS=ORT default (V2 threads + V3 structural fixes)

| Level | Success | e2e p50 ms | e2e p90 ms | first-audio p50 ms | CPU peak | loop-delay peak ms | ASR-queue peak |
|---|---|---|---|---|---|---|---|
| 1 | 3/3 | 1070.0 | 1301.1 | 717.5 | 70.7% | **15.1** | 0 |
| 2 | 6/6 | 1071.4 | 1937.1 | 663.4 | 100.0% | 146.7 | 0 |
| 3 | 9/9 | 2860.8 | 7330.3 | 2328.4 | 100.0% | 545.2 | 0 |
| 5 | 15/15 | 3392.2 | 5774.8 | 2930.3 | 100.0% | 415.7 | 2 |

Cleanup OK, recovery turn OK (995.4 ms). Recommended concurrency: **1** (unchanged).
Server RSS peak 836.4 MB. Note vs V2: loop-delay peak at 1 session 401→15 ms and at
2 sessions 1690→147 ms — the structural fixes alone removed most loop stalls even
before thread tuning.

### Config 2 — STT=4, TTS=2

| Level | Success | e2e p50 ms | e2e p90 ms | first-audio p50 ms | CPU peak / mean | loop-delay peak ms | ASR-queue peak |
|---|---|---|---|---|---|---|---|
| 1 | 3/3 | 1419.1 | 1435.5 | 1111.7 | 53.3% / 32.4% | 13.5 | 0 |
| 2 | 6/6 | 1095.8 | 1348.4 | 787.6 | 78.7% / 49.8% | 51.7 | 0 |
| 3 | 9/9 | **1133.5** | **2429.6** | 824.1 | 100.0% / 56.3% | 87.9 | 0 |
| 5 | 15/15 | **1366.9** | **4419.8** | 1042.3 | 100.0% / 85.6% | 100.0 | 0 |

Cleanup OK, recovery turn OK (1751.4 ms). RSS peak 834.2 MB.
Recommended concurrency: **2** (safe levels 1–2 by the unchanged V2 basis).
Level-1 p50 (1419 ms) is a 3-turn sample dominated by two ~1 s Groq TTFTs;
level-1 p95 spread is small (1435 ms) and CPU/loop health are the best of all configs.

### Config 3 — STT=2, TTS=2

| Level | Success | e2e p50 ms | e2e p90 ms | first-audio p50 ms | CPU peak / mean | loop-delay peak ms | ASR-queue peak |
|---|---|---|---|---|---|---|---|
| 1 | 3/3 | 1157.9 | 1696.3 | 843.8 | 98.6% / 64.5% | 107.2 | 0 |
| 2 | 6/6 | 1636.4 | 1728.1 | 1285.4 | 81.5% / 46.9% | 58.9 | 0 |
| 3 | 9/9 | 1304.1 | 2930.6 | 1006.7 | 88.1% / 60.5% | 157.2 | 0 |
| 5 | 15/15 | 1983.8 | **2826.4** | 1657.1 | 100.0% / 85.4% | 167.2 | 0 |

Cleanup OK, recovery turn OK (2590.3 ms). RSS peak 813.3 MB.
Recommended concurrency: **0** by the strict basis — level 1 hit a 98.6% CPU sample
(>95% gate), so no level is "safe" even though every turn succeeded.

### Cross-config comparison (all 33 turns per config, 100% success everywhere)

| Metric | 8/default | 4/2 | 2/2 |
|---|---|---|---|
| e2e p50 @3 sessions | 2860.8 | **1133.5** | 1304.1 |
| e2e p95 @3 sessions | 7330.3 | **2429.6** | 2930.6 |
| e2e p50 @5 sessions | 3392.2 | **1366.9** | 1983.8 |
| e2e p95 @5 sessions | 6887.9 | 5389.5 | **2844.7** |
| loop-delay peak @3 / @5 | 545 / 416 | **88 / 100** | 157 / 167 |
| CPU mean @3 sessions | 95.8% | **56.3%** | 60.5% |
| safe levels (V2 basis) | [1] | **[1, 2]** | [] |
| recommended concurrency | 1 | **2** | 0 |
| RSS peak MB | 836.4 | 834.2 | **813.3** |
| transcripts vs 8/default | — | identical | identical |

Honest anomaly note: 2/2 won the isolated contention microbench (§B.2) but did NOT
win the live matrix. Live 2-thread ASR decodes were slower (full-strategy asr_ms
434–711 ms at level 1 vs ~170–225 ms for 4/2), speculative misses were more frequent
(19 full vs 14 for 4/2), and level-1 CPU mean was higher (64.5% vs 32.4%). The
microbench contention block for 4/2 also ran under 77.6% background load, biasing it
pessimistic. **Live evidence outranks the microbench: 4/2 is the measured winner.**
2/2 remains attractive only for its level-5 p95 tail; it is available via env knob.

### Decision

- **New defaults: `STT_NUM_THREADS=4`, `TTS_NUM_THREADS=2`, `ASR_WORKERS=2`**
  (STT default formula capped at 4, floor 2; env overrides unchanged).
- Exact pre-V3 rollback: `INDICVOICE_STT_THREADS=8 INDICVOICE_TTS_THREADS=0`.
- Alternative tail-optimized profile: `INDICVOICE_STT_THREADS=2 INDICVOICE_TTS_THREADS=2`.
- **Measured safe concurrency on this laptop: 2 sessions** (100% turn success,
  loop delay <250 ms, CPU peak <95% at levels 1–2 with 4/2). Levels 3 and 5 complete
  all turns but saturate CPU; they are demonstrated capacity, not recommended capacity.
  No higher target is claimed.
- Accuracy: transcripts byte-identical across all three configs and all sweep thread
  counts; no endpoint, VAD, or streaming-decision settings were changed.
- Status: **PASS (automated)** for the engineering gates above. Real-world acoustic
  robustness and human-perceived smoothness remain **NOT TESTED** (Phases D–F).

## B.5 Caveats

- Synthetic corpus only; no real recordings exist yet (corpus 0/240 → Phase D/F).
- Background IDE load varied 17–78% between blocks; per-block values recorded.
- Percentiles are not additive; stage timings overlap in the streaming pipeline.
- 15 W laptop thermals: sustained multi-session runs may throttle; short blocks mitigate.
- Groq free-tier LLM latency varies with service load; `llm_ms` includes network TTFT.
- This report does not claim any concurrency target the hardware did not demonstrate.