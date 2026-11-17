# IndicVoice — Real-World Validation V2 — Final Report

**Engagement:** independent validation of IndicVoice under realistic conditions for
*controlled-pilot* readiness. This was a validation engagement, not a feature build:
the working implementation was preserved, no language route removed, no security
control weakened, no test removed or weakened.

**Headline verdict:** IndicVoice is **safe to expose on a trusted network with a token**
and is now extensively instrumented and reproducible — but it is **NOT ready for public
production traffic**. The three product promises that matter most remain unproven on
real-world evidence: **accuracy on real recordings (0/240 collected)**, **voice
naturalness (no listener study)**, and the **300–500 ms end-to-end latency target
(measured p50 ≈ 1.1–1.6 s)**. Physical microphone/phone validation and GitHub CI
execution are **NOT TESTED**. A controlled, authenticated, single-session internal
pilot with monitoring is feasible on suitable hardware; scaling is CPU-bound.

**Evidence-based validation score: ~58 / 100** (13-category scorecard, §M). This scores
*validated readiness*, not implementation completeness, and is deliberately not inflated.

Status vocabulary used throughout: **PASS (automated) / PASS — manually verified /
PARTIAL / FAIL / NOT TESTED / NOT APPLICABLE.**

All results: `benchmarks/results/realworld_v2/`. Git chain (this engagement):
`4a8156a` (A) → `fca6aab` (B) → `67a9054` (C+D) → `fa7886a` (E) → `ebb6082` (F+H) →
`252dc6a` (G+I+J) → Phase K commit. Branch `main`, no remote.

---

## A. Executive summary

**Delivered and verified in this environment:**
- Baseline/git integrity revalidated; `eval/shoot.mjs` restored after investigation;
  CI doc consistency fixed (Phase A).
- 240-recording corpus ingestion + validation + reporting tooling; honest **0/240** (B).
- Reproducible browser-microphone testing program: 17 scenarios + capability probes (C).
- Phone-over-LAN guide + automated local TLS/auth checker **9/9 PASS** (D).
- Human listening package: 96 anonymized/randomized/repeated samples, 10 dimensions,
  5-point scale, scoring + forms; **NOT TESTED** (no listeners) (E).
- Full latency budget matrix (6 conditions) + overlap-savings + structural-floor
  analysis; optimization alternatives without production changes (F).
- Capacity matrix (1/2/3/5 sessions) with CPU/RSS/queue/event-loop gauges; new
  token-gated `/metrics` endpoint; conservative capacity recommendation (G).
- CI fast tier proven model-free/key-free locally (**141 tests, 1 skip**); GitHub
  execution **NOT TESTED** with exact activation instructions (H).
- Security revalidation: **20 new model-free regression tests**, all controls intact (I).
- Controlled pilot guide + privacy-conscious monitor tool (**12 tests**, smoke-verified)
  + 9 incident scenarios with emergency rollback (J).
- Full regression: **161 tests pass** with models (model tier), none weakened (K).

**Left incomplete (honestly):** real human corpus (0/240); human listener study;
physical mic/phone/telephony validation; GitHub-hosted CI run; public-host/proxy
deployment; dependency CVE scan; multi-session performance on suitable hardware.

**Incidents found by execution (recorded, not hidden):** a TLS-checker greeting bug
(fixed, run 1 preserved); a `CPUSampler` `NameError` (fixed, run 1 preserved); a
Malayalam draft utterance containing Tamil codepoints (fixed, full script scan clean);
an embedded-Chromium cold-start probe timing issue (probe wait extended, check unchanged).

**Note on working tree:** uncommitted concurrent modifications to `eval/speak_check.py`
and its run outputs were observed during this engagement (not produced by it) and were
**left untouched**; they are not part of this engagement's commits.

## B. Phase A — Code integrity & baseline

- Git history intact; baseline preserved; three rollback levels retained (per-call
  `?streaming=0`, server `--no-streaming`, `git revert`).
- All **12 language routes** preserved; conservative ASR fallback preserved.
- `eval/shoot.mjs` restored after investigation; test-count doc consistency fixed.
- Doc: `REALWORLD_V2_BASELINE.md`. **Status: PASS (automated).**

## C. Phase B — Real-audio dataset

- Ingestion tool (11 detection checks, conversion preserving originals, human-verify
  flow), schema, recording guide, report tool; 17 new tests.
- **Collected: 0 / 240** (20/language × 12). No real recordings fabricated.
- Docs/results: `INDICVOICE_DATASET_STATUS_V2.md`, `dataset_report_v2.json/.md`,
  `dataset_validation_v2.json`. **Status: tooling PASS (automated); corpus NOT TESTED.**

## D. Phase C — Browser microphone validation

- `web/mic_validation.html`: 8 capability probes + 17 physical scenarios (M01–M17).
- Probes executed in **embedded Chromium** (Electron, Qoder) — 6 PASS / 2 INFO; this is
  a capability check, **not** physical microphone validation.
- All 17 physical scenarios **NOT TESTED** (no physical mic/device session).
- P8 cold-start incident recorded; probe wait extended (check itself unchanged).
- Doc: `INDICVOICE_MICROPHONE_VALIDATION.md`; result `mic_probes_embedded_chromium.json`.
- **Status: capability probes PASS (automated); physical validation NOT TESTED.**

## E. Phase D — Phone-over-LAN / telephony

- Guide: setup, ticket flow, firewall, self-signed vs public TLS separated; 12 items.
- Automated local checker `benchmarks/check_lan_tls.py`: **L1–L9 = 9/9 PASS**
  (HTTPS health auth=token, cert props, no-creds 4401, ticket 200/401/401, ticket
  admitted, replay 4401, legacy token admitted, plain-HTTP fails, insecure-bind refusal).
- 7 regression tests (`tests/test_lan_tls_check.py`). Checker greeting bug fixed; run 1
  preserved (`lan_tls_check_v2_run1_checker_bug.json`).
- Physical phone validation **NOT TESTED**. Telephony μ-law path is automated-tested
  end-to-end (`test_telephony_mulaw_turn` passes in the full regression).
- Doc: `INDICVOICE_PHONE_LAN_TEST.md`; result `lan_tls_check_v2.json`.
- **Status: local TLS/auth PASS (automated); physical phone NOT TESTED.**

## F. Phase E — Human voice quality evaluation

- Package: 6 utterance types × 12 languages × 2 repeats = **96 samples**, anonymized
  codes, seeded shuffle, private answer key, rating forms, listening interface.
- 10 dimensions, 5-point anchors; scorer reports mean/sample-SD/n-listeners/n-utterances
  and repeat consistency; explicitly **NOT ITU-T MOS**.
- 9 regression tests (`tests/test_human_eval.py`). Malayalam Tamil-codepoint defect fixed;
  full foreign-script scan of all 72 texts clean.
- **No listeners → NOT TESTED.** Doc: `INDICVOICE_HUMAN_EVALUATION.md`; results
  `human_eval_package_v2.json`, `human_eval_v2.json/.md` (status NOT TESTED).
- **Status: package + methodology PASS (automated); listening study NOT TESTED.**

## G. Phase F — Latency budget & optimization

- 6 conditions × 8 turns/lang (hi/en), real server, real LLM/TTS. Server RSS peak 1000 MB.
- **Central honest finding:** speculative streaming ASR overlap savings are **negative at
  the median** (1-session perceived saved p50 −171.9 ms; 3-session −530.3 ms). Lower ASR
  time ≠ equal E2E gain. Speculative hit rate, partial-decode lock contention and CPU
  starvation dominate; the en cloud path gets no speculation.
- **Structural floor:** hi ≈ 1.0 s (endpoint 260 + LLM TTFT ~550 + TTS ~200); en ≈ 1.2–1.3 s
  (two cloud round trips: ASR ~500 + LLM TTFT ~1000). LLM TTFT is the biggest lever.
- 9 optimization alternatives analysed (latency/accuracy/CPU/cost/complexity/risk); **no
  production change**; endpoint values **not** lowered for benchmarks.
- Doc: `INDICVOICE_LATENCY_OPTIMIZATION_V2.md`; results `latency_budget_v2.json`,
  `network_floor_v2.json`. **Status: PARTIAL (measured; 300–500 ms target not met).**

## H. Phase G — Capacity / concurrency

- Levels 1/2/3/5 × 4 turns (hi), CPU/RSS/queue/event-loop gauges via `/metrics`.
- **Reliability PASS:** 100% turn success (4/4, 8/8, 12/12, 20/20); cleanup
  `active_sessions→0`; recovery turn OK; RSS stable (peak 880.6 → final 719.7 MB); no
  queue backpressure (max 0–1).
- **Performance constrained:** CPU ~100% even at 1 session; event-loop stalls 401 ms
  (1) → 1690 ms (5); e2e p50 2.5 s → 7.5 s, p95 up to 15 s. Conservative smooth-audio
  recommendation **0**; practical pilot ceiling **1 session** on this 4-core/15 W laptop.
- `CPUSampler` bug fixed (run 1 preserved); 14 tests (`tests/test_capacity.py`).
- Doc: `INDICVOICE_CAPACITY_VALIDATION_V2.md`; results `capacity_v2.json`,
  `capacity_v2_run1_cpu_bug.json`. **Status: reliability PASS (automated); capacity PARTIAL.**

## I. Phase H — CI validation

- `ci.yml`: model-free/key-free `fast` tier (push/PR/dispatch) + manual `model-tier`
  (dispatch only, free local models, no paid cloud, no secrets).
- Heavy libs imported lazily; fast tier proven locally by hiding models:
  **141 tests, OK, 1 skip** (`ci_fast_tier_final.log`); `validate_dataset.py` exits 0.
- **GitHub execution NOT TESTED** (no remote, no `gh`); exact activation instructions given.
- Doc: `INDICVOICE_GITHUB_CI_VALIDATION.md`; result `ci_validation_v2.json`.
- **Status: PARTIAL (fast tier proven locally; GitHub NOT TESTED).**

## J. Phase I — Security revalidation

- **20 new model-free tests** (`tests/test_security_revalidate.py`): fail-closed auth,
  constant-time compare, single-use/expiring 192-bit tickets, Origin allowlisting
  (incl. `localhost.evil.com` rejection), frame caps, insecure-bind refusal, log redaction.
- All controls intact; **none weakened**. `/metrics` token-gated, privacy-conscious.
- uvicorn `log_level=warning` suppresses access logs; banner prints `<your-token>` only.
- **Dependency CVE scan NOT TESTED** (no `pip-audit`); activation instructions given.
- Doc: `INDICVOICE_SECURITY_REVALIDATION_V2.md`; result `security_revalidation_v2.json`.
- **Status: PASS (automated, local); CVE scan NOT TESTED.**

## K. Phase J — Controlled pilot readiness

- Guide: internal testers, authenticated only, small concurrency, documented languages,
  failure handling, no unauthorized recording; **13 privacy-conscious telemetry metrics**
  (counts/timings only); **9 incident scenarios** incl. emergency rollback.
- `tools/pilot_monitor.py`: token-redacting `/metrics` consumer, threshold alerts, JSONL
  series; **12 tests**, smoke-verified against a live server (loop 9–14 ms, RSS ~710 MB).
- Doc: `INDICVOICE_CONTROLLED_PILOT_GUIDE.md`; result `pilot_monitor_smoke.jsonl`.
- **Status: tooling/protocol PASS (automated); actual pilot NOT TESTED.**

## L. Phase K — Regression & test inventory

- **Full model-backed regression: 161 tests, OK** (0 failures/errors/skips),
  `full_regression_v2.log`. All WebSocket integration tests pass (streaming/block E2E,
  telephony μ-law, token/ticket auth, origin, frame caps, per-IP limit, idle 4408,
  max-duration 4410, ASR-error survival).
- **Fast tier (models hidden): 141 tests, OK, 1 skip** — model-free/key-free.
- Suite grew V1 72 → **161**; none removed or weakened; expectations never altered to
  get green (two fixture/checker bugs were fixed at the source, with run-1 evidence kept).
- 14 test files: capacity, codecs, dataset_tools, evaluate_ab, human_eval, lan_tls_check,
  latency_budget, metrics, pilot_monitor, security_revalidate, streaming_stt, text,
  ws_server, xss.
- **Status: PASS (automated).**

## M. Scorecard, acceptance gates & verdict

### M.1 Evidence-based validation scorecard (0–100, equal weight)

Scores reflect **validated readiness on real-world evidence**, not implementation
completeness. NOT TESTED physical/human/remote items are scored low deliberately.

| # | Category | Score | Evidence / rationale |
|---|---|---|---|
| 1 | Code integrity | 90 | Git chain intact; 12 routes + rollback + fallback preserved; 161 tests pass; baseline preserved. Not 100: `git revert` not drilled; concurrent out-of-engagement `eval/` edits observed. |
| 2 | ASR accuracy | 55 | Streaming/block parity proven on synthetic clips (V1 12/12); **real-recording accuracy NOT TESTED (0/240)**. Synthetic-only evidence caps the score. |
| 3 | TTS quality | 45 | Speed measured (RTF p50 0.11–0.20, 12 voices); humanizer implemented; **naturalness NOT TESTED** (no listeners; package ready). Implementation-only. |
| 4 | LLM quality | 50 | Groq gpt-oss-20b operational; script consistency checked (V1 12/12); no rigorous response-quality eval; stubbed in tests. Limited evidence. |
| 5 | E2E latency | 40 | Measured p50 ≈ 1.1–1.6 s (hi) / 1.2–1.3 s (en); **300–500 ms target NOT met**; streaming net-negative at median; structural floor = LLM TTFT + endpoint. |
| 6 | Browser audio | 30 | Capability probes pass (embedded Chromium); **17 physical scenarios NOT TESTED**; real browser/mic NOT TESTED. Tooling only. |
| 7 | Telephony | 55 | μ-law path automated-tested E2E; local TLS/auth 9/9; **physical phone/gateway NOT TESTED**. |
| 8 | Security | 80 | Fail-closed auth, constant-time compare, tickets, origin, caps, watchdogs, XSS eliminated, log redaction, `/metrics` gated; 20+ new tests. Capped: CVE scan NOT TESTED, no external pentest, self-signed TLS only. |
| 9 | Observability | 65 | `/metrics` (sessions, queues, loop delay, RSS), latency events, `/health` auth mode, pilot monitor. Still no structured logs/turn IDs/alerting backend. |
| 10 | Concurrency | 60 | 100% success 1–5 sessions; cleanup/recovery/memory stable; **CPU-bound, loop stalls, capacity-constrained** (smooth-audio rec 0). Reliable, not performant at scale. |
| 11 | CI | 55 | Fast tier proven model-free locally (141 tests); workflow authored; **GitHub execution NOT TESTED** (no remote). |
| 12 | Deployment | 50 | Guide, TLS, fail-closed bind, single-worker rationale; **public-host/proxy NOT TESTED**; multi-worker needs shared ticket store. |
| 13 | Evaluation maturity | 75 | Comprehensive honest tooling: dataset ingestion/validation, mic program, anonymized human-eval package, latency budget, capacity matrix, network floor, security revalidation, pilot monitor; NOT TESTED marking throughout. Execution on real humans/audio pending. |

**Equal-weight total: 750 / 13 ≈ 58 / 100.**

*Methodology note:* V1 reported 63/100 on a different 9-category weighted scale that
rewarded implementation. V2's 13-category scale scores **evidence-based validation
readiness**, so untested physical/human/remote items score low. The lower number reflects
honest evidence weighting, not a product regression — the implementation is preserved and
better instrumented than at V1.

### M.2 Seven acceptance gates

| Gate | Status | Basis |
|---|---|---|
| 1. Code integrity | **PASS (automated)** | Git intact; 12 routes + rollback + fallback preserved; 161 tests pass; nothing weakened. |
| 2. Security | **PASS (automated, local)** | Controls revalidated (20 new tests); none weakened. CVE scan NOT TESTED (noted). |
| 3. Real audio | **NOT TESTED** | 0/240 recordings; ingestion/validation tooling ready. Gate not met. |
| 4. Multilingual quality | **PARTIAL** | 12 routes preserved; synthetic parity 12/12; TTS speed 12 langs. Human naturalness + real-audio accuracy NOT TESTED. |
| 5. Performance | **PARTIAL** | Latency + capacity measured honestly; 300–500 ms E2E target NOT met; capacity CPU-constrained. |
| 6. CI | **PARTIAL** | Fast tier proven model-free locally; GitHub-hosted run NOT TESTED. |
| 7. Pilot | **PARTIAL / NOT TESTED** | Guide + monitor + incident procedures ready; actual controlled pilot NOT TESTED. |

### M.3 Final verdict & recommendations

**Not ready for public production traffic.** Safe for a **controlled, authenticated,
single-session internal pilot** on trusted hardware with monitoring, subject to the
Phase J boundaries. The biggest gaps are now *proven and instrumented*, not suspected.

**Next priorities (by impact, no unauthorized changes):**
1. **Collect real recordings** (Phase B flow, with consent) and measure real-audio
   accuracy — the single largest evidence gap (gate 3).
2. **Run the human listening study** (Phase E package) for voice naturalness — gate 4.
3. **Attack E2E latency structurally**: LLM TTFT is dominant; evaluate local en ASR
   (removes a cloud leg + unlocks speculation), partial-decode gating to raise speculative
   hit rate, and Groq connection reuse. Do **not** lower endpoint silence for benchmarks.
4. **Activate GitHub CI** (Phase H instructions) — gate 6.
5. **Validate on stronger hardware** before any multi-session pilot; the reference laptop
   is CPU-bound at 1 session (gate 5/7).
6. **Run a dependency CVE scan** (`pip-audit`) and a physical mic/phone session (gates 2/4).

**Do not** claim production readiness, fabricate metrics/MOS/recordings, mark untested
items as PASS, weaken security, remove routes/tests, or introduce paid providers/GPU
dependencies without authorization. All V2 non-negotiable rules were honoured.