# IndicVoice — Production Hardening V1 Final Report

Date: 2026-11-17 · Reference machine: Intel i7-8565U (4 cores / 8 threads, 15 W),
16 GB RAM, Windows 11, Python 3.13 (`.venv313`), sherpa-onnx 2.0.1, CPU-only.
Status vocabulary: **PASS (automated) / PASS — manually verified / PARTIAL /
FAIL / NOT TESTED / NOT APPLICABLE**. Raw results:
`benchmarks/results/production_v1/` (previous-phase results preserved untouched).

## A. Executive summary

**Inspected**: full codebase (server, pipeline, streaming STT, TTS, web client,
telephony path, config, tests), git state, prior audit register D1–D21, and the
existing 56-test suite. Two new defects were found by execution during this
engagement (D22 XSS sink, D23 A/B sub-manifest paths) — not by inspection alone.

**Implemented and verified in this environment**:
- Git baseline + 6 checkpoints (`5768a6d` → `79cf74d`); rollback preserved at
  three levels (per-call `?streaming=0`, server `--no-streaming`, `git revert`).
- Security hardening B1–B7: fail-closed non-localhost bind, one-time ticket
  transport, Origin allowlist, frame/payload/session/utterance/queue caps,
  dual watchdog, XSS sink elimination. All automated-tested.
- Test suite grown 56 → 72, none weakened or removed; all passing locally.
- Real-recording dataset tooling: 240-slot manifest, schema/audio validator
  (self-tested 6/6), consent + recording guide. **0/240 recordings collected.**
- Measurements: 2×40 live E2E turns (hi/en), 33-turn concurrency matrix
  (1/2/3/5 sessions), TTS speed bench (12 langs), noise matrix (hi/gu/kn),
  LLM script check (12 langs), counterbalanced A/B re-runs (12 langs).
- CI workflow authored (fast + manual model tiers, cloud-free); deployment
  guide with single-worker rationale and pre-go-live checklist.

**Left incomplete (honestly)**: real human corpus (0/240), human MOS/listener
study, physical mic/phone/telephony validation (checklists C1–C5 prepared,
NOT TESTED), CI execution on GitHub (no remote), public-host/proxy deployment
verification, >60 s live utterance test, browser-runtime XSS probe.

**Headline verdict**: the system is now *safe to expose on a trusted network
with a token*, measurable, and reproducible — but the 300–500 ms E2E target is
**not met** (measured p50 ≈ 1.1–1.3 s), accuracy is proven only on synthesized
audio, and no physical-device or human-quality validation exists. **Not ready
for public production traffic.** Readiness re-score: **63/100**
(`INDICVOICE_PRODUCTION_READINESS.md`).

## B. Security findings

| Finding ID | Severity | Root cause | Original behavior | Fixed behavior | Regression test | Final status |
|---|---|---|---|---|---|---|
| D2 | High | Transcript text interpolated via `innerHTML` in fallback page | Stored/reflected XSS from transcript or reply text | `createElement` + `textContent` | `tests/test_xss.py` (static sink pinning) | PASS (automated); browser-runtime probe NOT TESTED |
| D22 | High | `/health`-derived `v.backend` string rendered through `innerHTML` in `web/app.js` | Spoofed/compromised health response could inject HTML | Backend tag filled via `textContent`; allowlist pins every remaining interpolation | `tests/test_xss.py` (6 tests) | PASS (automated) |
| D3 | Medium | `==` token comparison | Timing side-channel on the shared secret | `hmac.compare_digest` | `test_token_auth`, `test_empty_and_invalid_token_rejected` | PASS (automated) |
| B1 | Critical | No auth required to bind beyond localhost | Any LAN neighbor could use the paid LLM key and models | Non-localhost bind without `INDICVOICE_TOKEN` refuses startup (exit 1); dev mode announced at startup and in `/health` (`auth: open-dev`) | `TestBindSecurity` (4 tests), `test_health_reports_auth_mode` | PASS (automated) |
| B2 | Medium | Long-lived secret in `?token=` query string | Token lands in history/proxy logs/Referer; not revocable per session | `POST /auth/ticket` (Bearer header) → single-use random ticket, 60 s TTL; legacy `?token=` preserved for existing clients | `test_ticket_endpoint_auth`, `test_ticket_single_use`, `test_expired_ticket_rejected`, `test_ticket_endpoint_needs_token_configured` | PASS (automated); client migration NOT TESTED (web client still uses `?token=`) |
| B4 | Medium | No Origin check on WebSocket upgrade | Cross-origin pages could open sockets (CSWSH) | Env-driven allowlist; foreign Origin → 4403 | `test_foreign_origin_rejected`, `test_localhost_origin_allowed`, `test_allowlisted_origin_allowed` | PASS (automated) |
| B5a | Medium | No inbound message size limits | Oversized frames/payloads could exhaust memory | 64 KiB voice frame / 64 KiB telephony text / 32 Ki-char base64 → 1009; malformed → 1003 | oversized-frame + malformed-JSON tests | PASS (automated) |
| B5b | Medium | No per-IP session cap | Session flooding from one host | 8 sessions/IP → 4429; slot always released | `test_per_ip_session_limit` (incl. release check) | PASS (automated) |
| B5c | Medium | Unbounded utterance buffer | Endless speech grows RAM without limit | 60 s cap: VAD segment truncated + `warning` event; `StreamingSTT(max_buffer=…)` stops growth | `test_max_buffer_cap`; >60 s live VAD path NOT TESTED | PARTIAL |
| B5d | Medium | Unbounded outbound queue | Slow/malicious client drain exhausts memory | 4096-item bounded queue; on Full the session closes | `TestOutboundQueueCap` | PASS (automated) |
| B6 | Low | Watchdog missed outbound activity; no session ceiling | Idle kills during long TTS playback; sessions could live forever | Activity bumped on emit; idle → 4408; 1800 s ceiling → 4410 | `test_idle_watchdog_closes_4408`, `test_max_session_duration_closes_4410` | PASS (automated) |

Remaining gaps (not hidden): no per-message rate limit, no brute-force lockout
on `/auth/ticket` (mitigated by token entropy), self-signed TLS only, no
external penetration test. Full detail: `INDICVOICE_SECURITY_HARDENING.md`.
**Automated auth tests passing does not make the system "secure"** — the
threat model is bounded (LAN neighbors, abusive clients, malicious pages);
network-layer DDoS and compromised-host scenarios are out of scope.

## C. Reliability findings

| Item | Change | Verification |
|---|---|---|
| D1 — ASR exception dropped the whole call | try/except around both ASR paths; `error` event emitted, socket survives, next turn works | PASS (automated: `test_asr_error_does_not_drop_call`) |
| D8 — watchdog killed outbound-only stretches | `last_activity` bumped in `_emit_audio` | PASS (automated + inspection) |
| D9 — barge-in vs draining LLM SSE socket race | `LLMClient.abort_active()` closes keep-alive connections when the worker outlives its join timeout | PARTIAL — code inspection only; race not deterministically reproducible, not stress-tested |
| D11 — `/health` assumed MMS paths for all languages | Backend-aware readiness (tiny/supertonic/MMS), `auth` mode field | PASS (automated + live `/health` observed) |
| D7 — hallucination filter dropped legitimate "एक" | Removed single common word from filter | PASS (automated: `test_single_word_answer_preserved`) |
| Session cleanup | `close()` cancels agent/streamer/player; `finally` releases IP slot; bounded queue closes slow drains | PASS (automated) |
| Benchmark lifecycle | Harnesses check port-free before bind, kill only their own process tree (`taskkill /T` — venv python is a launcher with a child interpreter) | PASS — manually verified (port 8010 freed after each run; pre-existing PID on 8000 never touched) |
| D23 — A/B sub-manifest paths | Audio paths rewritten absolute when sub-manifests live beside `--out` | PASS (automated: `tests/test_evaluate_ab.py`); found by executing the re-run |

Physical audio reliability (mic echo, phone speakers, telephony μ-law round
trip, noisy rooms, long calls): checklists C1–C5 prepared in
`INDICVOICE_AUDIO_RELIABILITY_REPORT.md`, all **NOT TESTED** — no physical
device loop was available in this environment. The μ-law codec path is
unit-tested (`tests/test_codecs.py`) but that is not a carrier validation.

## D. Dataset status (actual counts)

| Language | Real recordings collected | Slots defined |
|---|---|---|
| hi, gu, mr, bn, ta, te, kn, ml, pa, or, as, en | **0 each** | 20 each |
| **Total** | **0 / 240** | 240 |

Every manifest entry is `NOT_COLLECTED` with null reference/consent fields.
Tooling is verified: `benchmarks/validate_dataset.py` self-tested 6/6
(consent gate, duplicate IDs, missing file, format checks, completeness exit
code); `evaluation/dataset/README.md` documents consent, diversity targets
(5 speaker groups/language, 3 noise conditions), and the 16 kHz mono PCM16
recording procedure. All current accuracy numbers come from the
**TTS-synthesized starter corpus** (3 clips/language) and are labeled as such
everywhere. No recording was fabricated; no TTS clip is counted as real.

## E. Recognition quality (measured)

Baseline full A/B (`benchmarks/results/ab_full.json`, n=3/language,
synthesized corpus, real-time feeding, server-matching endpoint semantics):

| lang | CER (block = streaming) | WER (block = streaming) |
|---|---|---|
| hi | 0.047 | 0.170 |
| gu | 0.025 | 0.111 |
| mr | 0.000 | 0.000 |
| bn | 0.044 | 0.233 |
| ta | 0.000 | 0.000 |
| te | 0.000 | 0.000 |
| kn | 0.012 | 0.083 |
| ml | 0.029 | 0.111 |
| pa | 0.042 | 0.170 |
| or | 0.088 | 0.400 |
| as | 0.268 | 0.889 |
| en | 0.141 | 0.143 |

**Parity: CER and WER identical in both modes for 12/12 languages**, by
construction (the final transcript is always a full-buffer decode) and by
measurement. Known weaknesses: `as` uses the bn model (no native Assamese
ASR — CER 0.268 is a workaround cost, documented, no silent mapping change);
`en` CER is driven by one bad clip; `or` WER 0.400 is the weakest Indic
Conformer. Absolute values are optimistic (clean TTS audio, n=3).

**Counterbalanced A/B re-run (Phase E)**: corpus split in half; group A runs
block→streaming, group B streaming→block, to cancel order/thermal bias.
Raw: `benchmarks/results/production_v1/ab_v1.json` (+ `_orderA/_orderB`
sub-manifests).

- **Accuracy parity reproduced exactly**: all 12 languages, CER/WER identical
  between modes and identical to the baseline values above.
- **Latency improvement did NOT reproduce in re-run 1**: block baselines
  themselves inflated up to 2.4× vs the original run (e.g. pa block p50
  775 → 1859 ms), and streaming p50 was worse than block in 7/12 languages
  despite 33/33 local turns using the speculative strategy. The regressions
  appear in both order groups, so this is not a counterbalancing artifact;
  it matches the documented run-to-run variance of this 15 W laptop
  (block decode times varied up to 2.7× between earlier runs).
- Re-run 2 (after cooldown): block baselines returned to normal and streaming
  penalties shrank to ≤225 ms — confirming run 1 was machine state, not a code
  regression. Full comparison and cross-run conclusions in the addendum.

**Honest conclusion**: the *accuracy* guarantee is robust and reproducible;
the *latency* benefit of speculation is real but load-dependent and must be
capacity-planned from worst-case (block-equivalent) decode times, not
best-case runs. A larger real corpus (Phase D) is required before any
accuracy claim beyond this synthesized set.

## F. TTS quality (measured speed; naturalness NOT measured)

`benchmarks/results/production_v1/tts_v1.json` — n=6/language, warm model,
offline synthesis, Indic Tiny backend for all 12 languages (unchanged, per
the no-provider-replacement rule):

| lang | RTF p50 | RTF max | first-sentence render p50 (ms) |
|---|---|---|---|
| hi | 0.110 | 0.140 | 215.7 |
| gu | 0.140 | 0.184 | 307.1 |
| mr | 0.193 | 0.275 | 574.2 |
| bn | 0.182 | 0.243 | 369.8 |
| ta | 0.139 | 0.145 | 289.1 |
| te | 0.169 | 0.196 | 453.3 |
| kn | 0.200 | 0.244 | 495.1 |
| ml | 0.194 | 0.210 | 345.5 |
| pa | 0.118 | 0.156 | 331.4 |
| or | 0.133 | 0.167 | 320.3 |
| as | 0.136 | 0.165 | 276.8 |
| en | 0.148 | 0.201 | 313.4 |

All voices synthesize 5–9× faster than real-time; TTS is not the E2E
bottleneck. Live first-audio (server-side, from E2E runs): hi p50 806 ms,
en p50 1084 ms — dominated by endpoint wait + LLM first token, not TTS.

**Human evaluation: none exists.** No MOS, no listener study, no preference
test. The humanizer/clause-pause/seam-blending work is implemented and was
audible in smoke audio, but intelligibility is not naturalness and no score
is claimed. The MOS protocol is prepared (`INDICVOICE_EVALUATION_FRAMEWORK.md`
§5) awaiting real listeners.

## G. E2E latency (measured, live server, real LLM)

`benchmarks/run_e2e_latency.py`; 20 turns/language/run, real-time feeding,
Groq `openai/gpt-oss-20b`. Definition: `e2e_client_ms` = last speech frame
sent → first audio byte received (includes the endpoint-silence wait:
0.26 s hi-family / 0.45 s en). Stages overlap in the pipeline and are never
summed. Run 1's RSS series was invalid (venv launcher sampled instead of the
child interpreter — fixed, run 1 preserved as `e2e_v1_run1.json`); latency
numbers in both runs are valid.

| Run | Lang | n | e2e p50 | e2e p90 | e2e p95 | first-audio p50 (server) | failed |
|---|---|---|---|---|---|---|---|
| 1 | hi | 20 | 1882.8 | 4300.1 | 7052.8 | 1596.9* | 0 |
| 1 | en | 20 | 1195.8 | 1351.5 | 1416.4 | — | 0 |
| 2 (canonical) | hi | 20 | 1130.1 | 1937.2 | 2766.2 | 806.1 | 0 |
| 2 (canonical) | en | 20 | 1264.2 | 1589.8 | 2886.6 | 1084.4 | 0 |

\* run-1 console value; per-turn data in `e2e_v1_run1.json`.

Stage medians (run 2): hi — ASR 0.9 ms (speculation hits), LLM 512 ms,
TTS 214 ms; en — ASR 466 ms (cloud), LLM 943 ms, TTS 115 ms.

**The 300–500 ms E2E target is NOT met.** Structural floor: endpoint silence
(260–450 ms) + LLM first token (≈0.5–1 s) + first-clause TTS (≈0.1–0.3 s).
Hi variance is driven by speculation coverage (10/20 vs 14/20 turns across
runs): pause-heavy digit utterances fall back to full decode. Reaching the
target requires semantic endpointing and/or faster LLM TTFT — a feature
change, deliberately out of scope under the feature freeze. Full analysis:
`INDICVOICE_E2E_LATENCY_REPORT.md`. Other languages: NOT TESTED end-to-end
(only hi/en have live E2E data; ASR-stage A/B covers all 12).

## H. Concurrency (measured)

`benchmarks/results/production_v1/concurrency_v1.json` — hi, 3 turns/session,
levels 1/2/3/5 simultaneous sessions, live Groq LLM:

| Level | Turns | OK | Success | e2e p50 (ms) | e2e p95 (ms) | ASR p50 (ms) |
|---|---|---|---|---|---|---|
| 1 | 3 | 3 | 100% | 1032.7 | 1465.8 | 0.4 |
| 2 | 6 | 6 | 100% | 1334.1 | 1888.0 | 1.4 |
| 3 | 9 | 9 | 100% | 1990.1 | 3822.8 | 1.2 |
| 5 | 15 | 15 | 100% | 3703.3 | 6649.0 | 1921.0 |

- **Highest verified level: 5** (33/33 turns, zero failures, zero errors).
- Hardware: i7-8565U 4C/8T 15 W, 16 GB RAM. Server RSS peak **732.5 MB**
  (hi+en warmed), stable across levels — no leak signature in this window.
- CPU saturates between 3 and 5 sessions: ASR p50 jumps 1.2 → 1921 ms as
  speculative decodes queue. **Recommended operational ceiling on this
  hardware: 2–3 concurrent calls**; level 5 is survivable, not comfortable.
- Level 10 deliberately excluded (hardware-safe rule); multi-hour soak,
  mixed-language concurrency, and telephony concurrency: NOT TESTED.
- Full report: `INDICVOICE_CONCURRENCY_REPORT.md`.

## I. CI status (actual)

- `.github/workflows/ci.yml` exists with two jobs:
  - **fast** (push/PR/dispatch): ubuntu, Python 3.13, `apt libportaudio2`,
    `requirements-ci.txt` (numpy/scipy/fastapi/uvicorn/websockets/aiohttp/
    sounddevice — no models, no cloud keys), `unittest discover`, dataset
    schema validation.
  - **model** (manual `workflow_dispatch` only): full requirements, downloads
    hi/en/VAD models in-job, full suite with StubLLM — still cloud-free.
- Dependency checks: `requirements-ci.txt` is a strict subset of
  `requirements.txt`; CI never receives `GROQ_API_KEY`/`OPENAI_API_KEY`.
- Tests: **72 local, all passing** (unit, streaming state machine with fake
  engine, real-model WS integration, security, static XSS, A/B path
  regression). Model-absent behavior verified locally: WSTests raises
  `SkipTest` (simulated missing VAD → `OK (skipped=1)`), never fake-passes.
- **Executed on GitHub Actions: NOT TESTED** — no remote configured.
  Linux wheel behavior of the model tier: NOT TESTED.
- Guide: `INDICVOICE_CI_GUIDE.md`.

## J. Deployment readiness

| Requirement | Status |
|---|---|
| Fail-closed auth on non-localhost bind | PASS (automated) |
| Token/ticket auth + Origin allowlist + abuse caps | PASS (automated) |
| TLS available (`--tls` self-signed; proxy termination documented) | PARTIAL — no CA cert shipped |
| Single-worker topology rationale (model caches, in-process ticket/IP state) | documented; PASS as design constraint |
| LAN phone deployment (`start_voice_phone.bat`) | script present; physical phone validation NOT TESTED |
| Public host behind TLS proxy | configuration documented; NOT TESTED end-to-end |
| `/health` readiness incl. `auth` mode | PASS (automated + live observed) |
| Rollback: per-call / server flag | PASS (automated / exercised in suite+smoke) |
| Rollback: `git revert` | PARTIAL — history exists; revert not drilled |
| Real-device audio checklists C1–C5 | NOT TESTED |
| Real-corpus accuracy gate | NOT TESTED (0/240 collected) |
| Load ceiling documented (2–3 calls on reference hardware) | PASS — measured basis |

Guide: `INDICVOICE_DEPLOYMENT_V1.md` (env checklist, nginx sketch, pre-go-live
checklist). Supported today: **single machine, trusted network, token set,
TLS in front, ≤2–3 concurrent calls**.

## K. Remaining critical risks / blockers

1. **No real-recording accuracy evidence** (0/240). All CER/WER is from
   synthesized audio; real callers (accents, noise, disfluency) are
   unmeasured. Blocks any production accuracy claim.
2. **E2E latency 2–4× over target** (p50 ≈ 1.1–1.3 s vs 300–500 ms).
   Structural: endpoint wait + LLM TTFT. Blocks the product's latency promise.
3. **No physical validation**: mic/phone/telephony/noise/long-call checklists
   unexecuted; D9 race mitigation unverified under stress.
4. **No human quality evidence**: no MOS; one LLM reply was factually wrong
   while script-perfect (mr "capital = Mumbai") — content quality is
   unmeasured and the script check cannot catch it.
5. **Capacity ceiling**: 4-core laptop saturates at 3–5 calls; no
   multi-worker path exists without a shared ticket/rate-limit store.
6. **CI never executed**; no remote; Linux model-tier wheels unverified.
7. **Security residuals**: legacy `?token=` still the default client
   transport, no per-message rate limit, no ticket-endpoint lockout,
   self-signed TLS only, no external pentest.
8. **`as` recognition is a bn-model workaround** (CER 0.268); `en` ASR
   depends on a paid cloud provider (cost + availability + privacy surface).
9. **Observability gaps**: no structured logs, turn IDs, metrics, alerting;
   production incidents would be hard to diagnose.

## L. Next five engineering priorities (by technical impact)

1. **Collect the real corpus (Phase D gate) and re-measure CER/WER + A/B on
   it.** Every accuracy claim currently rests on 36 TTS clips; this is the
   single largest evidence gap. Tooling is ready; needs consented speakers
   (≈1 week of coordinated recording).
2. **Attack E2E latency structurally**: semantic/VAD-light endpointing to cut
   the 260–450 ms silence wait, and LLM TTFT reduction (prompt shortening,
   provider/model comparison with documented justification). Measured stage
   medians show these two dominate; TTS and ASR are already fast. Requires
   lifting the feature freeze with the user's approval.
3. **Activate CI**: create the remote, push, verify the fast tier green on
   GitHub, trigger the model tier once; add the accuracy gate as a local
   pre-release command. Converts "72 tests pass on one laptop" into
   continuous, reproducible verification.
4. **Execute physical validation C1–C5** (real mic, phone speaker, telephony
   gateway round trip, noisy room, 30-min call) and a multi-hour soak at
   2–3 concurrent sessions. Converts the reliability report from checklists
   into evidence; exercises D9 under real barge-in load.
5. **Human quality evaluation**: run the prepared MOS protocol (≥5 listeners,
   ≥20 utterances/language subset) and an LLM content-quality rubric (the
   mr factual error shows script checks are insufficient). Naturalness and
   content quality are currently unmeasured product risks.

---

## Addendum: A/B re-run 2 (counterbalanced, after cooldown)

Raw: `benchmarks/results/production_v1/ab_v1_run2.json` (+ order sub-manifests).
Same protocol as re-run 1, executed after a machine cooldown.

| lang | block p50 run1 → run2 | streaming p50 run1 → run2 | stream−block (run2) |
|---|---|---|---|
| hi | 99 → 204 | 23 → 0 | −204 |
| gu | 933 → 798 | 820 → 681 | −117 |
| mr | 902 → 939 | 1767 → 953 | +14 |
| bn | 791 → 678 | 964 → 612 | −66 |
| ta | 653 → 667 | 730 → 633 | −34 |
| te | 738 → 684 | 1385 → 909 | +225 |
| kn | 2040 → 916 | 2964 → 871 | −45 |
| ml | 2020 → 828 | 3030 → 956 | +128 |
| pa | 1859 → 714 | 1070 → 781 | +67 |
| or | 1142 → 743 | 914 → 828 | +85 |
| as | 920 → 845 | 1627 → 691 | −154 |
| en | 452 → 424 | 410 → 436 | +12 |

(all values ms; CER/WER again identical between modes and to the baseline,
12/12 languages.)

**Cross-run conclusions (3 counterbalanced/ordered runs total):**

1. **Accuracy parity is robust**: reproduced in every run, every language —
   36/36 language-run pairs with identical CER and WER.
2. **Run 1's latency regression was machine state, not a code regression**:
   after cooldown, block p50 returned to baseline levels (kn 2040 → 916 ms,
   pa 1859 → 714 ms) and streaming penalties shrank from up to +2265 ms to
   at most +225 ms. The 15 W laptop's thermal/load variance (documented 2.7×
   in the baseline) dominates single-run latency deltas.
3. **Streaming latency benefit is real but modest and load-dependent**:
   after cooldown, streaming p50 ≤ block in 6/12 languages, with hi
   consistently near-zero (0–23 ms across all runs) and gu/as clearly
   improved; the original full run's larger gains (9 languages clearly
   improved) represent a favorable machine state. Worst-case planning must
   assume block-equivalent decode time.
4. The counterbalancing itself works as designed: regressions in run 1
   appeared in both order groups, and run 2's mixed deltas show no
   systematic order bias.