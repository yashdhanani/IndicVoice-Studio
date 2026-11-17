# IndicVoice V3 — Phase A: independent baseline & repository audit

Date: 2026-11-17 · Assessor scope: full re-inspection of source, tests, CI,
models, benchmark artifacts and Git state before any V3 code change.
Status vocabulary: PASS (automated) / PASS — manually verified / PARTIAL /
FAIL / NOT TESTED / NOT APPLICABLE.

## A.1 Repository state (inspected, not assumed)

- Branch `main`, HEAD `f8ba93a` ("V2 Phase K"), **no remote configured**.
- V2 commit chain intact: `4a8156a → fca6aab → 67a9054 → fa7886a → ebb6082 →
  252dc6a → f8ba93a` on top of V1 (`74da488`, `4fb184d`, …) and baseline `5768a6d`.
- Working tree: **only** concurrent external work in `eval/` is uncommitted:
  - `eval/speak_check.py` modified (379 insertions / 144 deletions vs HEAD):
    multi-repeat rendering (`--repeats`), recalibrated voice-band gates with a
    measured kn/ml rationale, per-render wav hashing. Coherent, documented,
    and timestamped after the V2 close-out (16:41 today).
  - Three new run bundles `eval/speak_check_20261117-16{2153,2833,3551}/` + zips
    and `speak_check_run.log` (16:39–16:42 today).
  - **Ownership: not this engagement.** Investigated per rule 13; left
    untouched, excluded from every V3 commit via explicit path staging.
    The user should confirm its provenance and commit it separately.
- Pre-existing processes (NEVER terminated): PID 23004 on 127.0.0.1:8000,
  PID 24788 on 127.0.0.1:8011. V3 benchmarks use ports 8012/8013/8444 and
  refuse occupied ports.
- No secrets in tracked files (V2 scan clean; re-verified at Phase K).

## A.2 Architecture (current, verified by reading every source file)

```
browser (web/app.js, AudioWorklet 16 kHz PCM16) ──ws──┐
telephony gateway (8 kHz μ-law JSON) ─────────────────┤
                                                      ▼
call_server.py  FastAPI/uvicorn, single event loop
  ├─ /ws/voice, /ws/telephony  (token/ticket auth, Origin allowlist, caps)
  ├─ CallSession.feed → 512-sample VAD windows (Silero, 1 thread, ON LOOP)
  │    ├─ echo gate + barge-in (0.45 s sustained speech)
  │    ├─ StreamingSTT worker thread: gated partials + speculative decode
  │    │    during endpoint silence; final = authoritative full-buffer decode
  │    └─ endpoint → run_in_executor(default) → finalize/transcribe
  ├─ VoiceAgent.start_response → llm-tts worker thread
  │    ├─ LLMClient: Groq gpt-oss-20b (reasoning low), keep-alive socket, warm()
  │    ├─ SentenceSplitter → ensure_script → TTSPool.speak_sentences
  │    │    └─ per-model gen lock; tiny (ORT) / supertonic / MMS (sherpa)
  │    │       + Humanizer (pauses, jitter, room tone) + SeamBlender
  │    └─ AudioSink.push → resample → outbound queue (cap 4096)
  ├─ sender() task: run_in_executor(default) blocking queue.get(0.2 s) poll
  ├─ watchdogs: idle 180 s (4408), max session 1800 s (4410)
  └─ /health, /metrics (loop-lag probe via lifespan), /auth/ticket
```

- Models: 11× IndicConformer INT8 (sherpa-onnx 2.0.1, `as` = bn alias), en =
  Groq Whisper-large-v3-turbo with local script-drift fallback; 12× Indic Tiny
  TTS (onnxruntime 1.32); Supertonic-3 INT8 present (hi/en fallback); 12× MMS
  VITS fallback; Silero VAD; Whisper tiny/base on disk.
- Runtime: `.venv313` Python 3.13.18, numpy 2.5.5, scipy 1.18.1,
  fastapi 0.163.1, uvicorn 0.54.0, websockets 17.4.
- Rollback levels preserved: `?streaming=0` per call, `--no-streaming` per
  server, git revert (additive streaming code).

## A.3 Confirmed capabilities (evidence-backed)

| Capability | Evidence | Status |
|---|---|---|
| 12 language routes, models on disk | A.2 check: all 12 ASR file pairs + tiny voices present; VAD present | PASS (automated) |
| 161-test suite green | `full_regression_v2.log` (139.95 s, OK); 161 `def test_` counted today across 14 files | PASS (automated, V2 run) |
| Fast CI tier model-free | `ci_fast_tier_final.log` 141 OK / 1 skip via `INDICVOICE_MODELS_DIR` override | PASS (automated, local sim) |
| Streaming/block accuracy parity | counterbalanced A/B, 12/12 languages, twice (V1) | PASS (automated, synthetic corpus) |
| Security controls B1–B7 | 20 revalidation tests + 6 XSS tests (V2) | PASS (automated, local) |
| Concurrency reliability | capacity_v2: 33/33 turns at 1/2/3/5; cleanup + recovery OK; RSS 880.6→719.7 MB | PASS (automated) |
| E2E latency measured | latency_budget_v2: hi p50 ≈1.13 s, en ≈1.26 s (V1 live runs); V2 budget matrix | PASS (measured) — target NOT met |
| Benchmark artifact integrity | all 28 JSONs in production_v1/ + realworld_v2/ parse cleanly today | PASS (automated) |

## A.4 Existing defects & root-cause candidates (code-read findings)

Ordered by expected impact; each is a Phase B/C experiment, not yet proven:

1. **Thread oversubscription (primary CPU suspect).**
   `config.STT_NUM_THREADS = 8` (src/config.py:312) on a 4-physical-core /
   8-logical i7-8565U; the comment claims "an i7 with 8 cores" — this machine
   has 4. Tiny TTS is loaded via `TinyTTSOnnx.from_pretrained(dir)` **without
   `threads=`** (src/tts_engine.py:219), so onnxruntime uses its default
   intra-op pool (all cores). ASR decode + TTS synthesis can therefore run
   ~16 compute threads on 4 physical cores simultaneously (partials/speculation
   overlap the previous turn's playback). Matches V2's ~100 % CPU at one
   session and 401–1690 ms loop stalls during decode bursts.
2. **Sender polling shares the default executor with ASR.**
   `CallSession.sender` (src/call_server.py:403) does
   `run_in_executor(None, queue.get, 0.2)` — every session permanently occupies
   a default-executor worker in a blocking poll, and ASR `finalize`/`transcribe`
   (call_server.py:509–514) queue behind those polls in the same pool
   (max_workers = min(32, cpu+4) = 12 here). At 5 sessions, 5 workers poll
   full-time; decode latency becomes pool-contention-dependent.
3. **Quadratic inbound buffer copies.** `StreamingSTT.accept`
   (src/streaming_stt.py:128) does `np.concatenate([self._buf, chunk])` every
   32 ms frame; a 60 s utterance copies ~3.6 GB cumulatively. Also
   `CallSession.feed` re-concatenates `_inbuf` per client frame.
4. **VAD + gating + numpy on the event loop.** `_process_frame` runs Silero
   accept, RMS gate, barge-in logic synchronously on the loop thread; cheap
   per frame but GIL-contended when decode threads spin.
5. **Speculative streaming net-negative at median** (V2 measured: −172 ms
   1-session, −530 ms 3-session perceived overlap savings). Partial-decode
   lock contention + low hit rate. Not a defect to "fix" by deletion — the
   fallback and switches stay; Phase B re-measures under controlled threads.
6. **Per-session idle worker wakeups.** StreamingSTT `_cond.wait(timeout=0.1)`
   wakes 10×/s/session even when idle; sender polls 5×/s/session. Minor CPU
   tax, adds up at 5 sessions.
7. **Known V2 residuals** (unchanged): web client still legacy `?token=`
   (web/app.js:711); no per-message rate limit / ticket-endpoint lockout;
   self-signed TLS only; D9 race mitigation unverified under stress; no
   structured logs/turn IDs; `as` on bn alias; real corpus 0/240.

## A.5 Historical benchmark consistency

- 28/28 JSON artifacts parse; buggy runs preserved under descriptive names
  (`capacity_v2_run1_cpu_bug.json`, `lan_tls_check_v2_run1_checker_bug.json`).
- V2 numbers re-stated from artifacts, not memory: capacity 33/33 turns,
  e2e p50 2558→7482 ms across levels 1→5 (hi, TTS corpus, driver-side CPU
  contention caveat), loop-delay peaks 401→1690 ms, recommendation 0 under the
  strict smoothness bar (100 % success ∧ loop <250 ms ∧ CPU <95 %).
- V1 vs V2 score difference (63 vs 58) is methodology, not regression
  (documented in final_scorecard_v2.json).
- No historical artifact will be overwritten in V3; new evidence goes to
  `benchmarks/results/realworld_v3/` only.

## A.6 Outstanding V2 acceptance gates (carried into V3)

| Gate | V2 status | V3 disposition |
|---|---|---|
| Code integrity | PASS | re-verify at Phase K |
| Security (local) | PASS; CVE scan NOT TESTED | Phase G: pip-audit + review |
| Real audio corpus | NOT TESTED (0/240) | stays NOT TESTED; tooling ready |
| Multilingual quality | PARTIAL (synthetic only) | Phase D analysis; real metrics NOT TESTED |
| Performance | PARTIAL (E2E target missed; CPU-bound) | Phases B+C (highest priority) |
| CI on GitHub | PARTIAL (local sim only) | Phase H procedure; execution NOT TESTED |
| Controlled pilot | PARTIAL / NOT TESTED | Phase I guide; actual pilot NOT TESTED |
| Human listening | NOT TESTED | Phase E workflow; no MOS without humans |
| Physical mic/phone | NOT TESTED | Phase F operator procedures |

## A.7 Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Thread/pool changes alter decode timing → speculative hit-rate shifts, accuracy parity breaks | medium | high | A/B parity gate on every config; keep `?streaming=0` + `--no-streaming`; env knobs default to measured-best, old values reachable |
| R2 | Concurrent eval/ agent runs CPU-heavy renders during V3 benchmarks → contaminated measurements | high (active today) | high | check process CPU before each benchmark; never run two heavy benches at once; record machine state in every artifact |
| R3 | Thermal throttling on 15 W laptop skews comparisons | high | medium | cooldowns between levels (8 s+), counterbalanced order, repeat runs, report run order |
| R4 | Groq free-tier 429s during latency runs | medium | medium | small authorized budgets, document call counts, retry/backoff already present |
| R5 | Sender/executor refactor introduces audio-delivery regression | medium | high | full 161-test suite + new regression tests + live turn matrix before adoption |
| R6 | Accidental commit of eval/ concurrent work or secrets | medium | high | explicit path staging only; secret scan at every checkpoint |
| R7 | Optimizing stage timings while perceived E2E regresses | medium | high | acceptance only on measured end-to-end first-audio; never sum percentiles |
| R8 | Model swap temptation (Whisper/IndicF5) without real-corpus evidence | medium | high | Phase D/E are comparisons + routing analysis; no swap without measured evidence; real corpus NOT TESTED |

## A.8 Recommended execution order (approved plan)

1. **Phase B** (highest priority): thread-count sweep (STT 8/4/2, tiny-TTS
   threads), dedicated ASR executor + event-driven sender, buffer-append
   optimization; identical-condition 1/2/3/5 matrix per config; adopt only
   measured wins; regression tests for every change.
2. **Phase C**: full turn instrumentation (speech-end → endpoint → ASR → LLM
   TTFT → TTS → first audio), p50/p90/p95/max; endpointing/TTFT/warm-up levers
   evaluated against the Phase B winner; honest E2E acceptance.
3. **Phase D**: per-language ASR pipeline review + model-routing comparison
   (analysis + synthetic evidence only; real corpus NOT TESTED).
4. **Phase E**: TTS naturalness investigation + alternative CPU feasibility +
   listening workflow on the existing 96-sample package (MOS NOT TESTED).
5. **Phase F**: operator-ready physical procedures (NOT TESTED until humans).
6. **Phase G**: security review + pip-audit (network permitting).
7. **Phase H**: CI/CD activation procedure (no remote without authorization).
8. **Phase I**: pilot deployment guide (no public exposure).
9. **Phase J**: unified machine-readable benchmark report with full metadata.
10. **Phase K**: full regression, rollback/auth/WS/μ-law/monitoring checks,
    secret + artifact-integrity scans, final report + 100-point scorecard +
    changelog + architecture source + review bundle.

**Phase A verdict: PASS (automated inspection).** Baseline confirmed intact;
no code changes made in this phase. Proceed to Phase B.