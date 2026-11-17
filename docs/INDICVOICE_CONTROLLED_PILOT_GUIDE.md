# IndicVoice — Controlled Pilot Guide (Real-World Validation V2, Phase J)

**Scope:** a small, internal, authenticated pilot — not a public launch. This guide
covers tester onboarding, safe operating limits, privacy-conscious telemetry, failure
handling, and incident/rollback procedures. It assumes the security controls verified
in Phase I are intact and the capacity limits measured in Phase G are respected.

Status vocabulary: PASS (automated) / PASS — manually verified / PARTIAL / FAIL /
NOT TESTED / NOT APPLICABLE. **A physical pilot with real testers is NOT TESTED until
it actually runs**; this document is the protocol, not a claim of execution.

---

## 1. Pilot boundaries (non-negotiable)

- **Internal testers only.** Named, consenting participants; no public exposure.
- **Authenticated only.** Set `INDICVOICE_TOKEN`; never run open-dev on a network.
  A non-localhost bind without a token is refused at startup (fail-closed).
- **Small concurrency.** Respect the Phase G conservative limit (see
  `INDICVOICE_CAPACITY_VALIDATION_V2.md`). On the 4-core/15 W reference laptop,
  start at **1 concurrent session** and increase only while latency and event-loop
  delay stay acceptable. Do not exceed the measured safe level.
- **Documented languages only.** Pilot the languages whose models are downloaded and
  whose quality has been reviewed. All 12 routes exist, but only enable those you have
  validated. Do not silently map one language to another.
- **No unauthorized recording.** Do not record, store or upload tester audio without
  explicit consent. The server does not persist transcripts or audio by default; keep
  it that way. Any recording for evaluation needs consent + the Phase B ingestion flow.
- **No expensive cloud inference without authorization.** The pilot uses the configured
  LLM; do not switch to paid providers or raise volume without approval.

## 2. Starting the pilot server

Localhost (development / single tester):

```
.venv313/Scripts/python.exe -m src.call_server --host 127.0.0.1 --port 8000 --warm hi en
```

Authenticated LAN (phones need TLS for microphone access):

```
set INDICVOICE_TOKEN=<long-random-secret>
.venv313/Scripts/python.exe -m src.call_server --host 0.0.0.0 --port 8443 --tls --warm hi en
```

- Prefer the **ticket flow**: tester backend does `POST /auth/ticket` with
  `Authorization: Bearer <token>`, then the browser connects with `?ticket=<one-time>`.
  The long-lived token stays out of URLs/history/proxy logs.
- Self-signed TLS is fine for internal phones (accept the cert warning once). For any
  broader use, put a real certificate / reverse proxy in front — do not weaken browser
  security. See `INDICVOICE_PHONE_LAN_TEST.md`.
- Verify `GET /health` reports `auth: "token"` and the intended voices `ready: true`.

## 3. Tester onboarding checklist

1. Confirm consent and the language(s) they will test.
2. Give them the pilot URL (with ticket flow), not the raw token.
3. Walk through one call: speak, wait for the reply, confirm audio playback.
4. Tell them how to report a problem (timestamp, language, what happened — **not**
   a recording unless consented).
5. Record results against the Phase C microphone scenarios / Phase E listening forms
   as applicable; mark anything not physically performed as NOT TESTED.

## 4. Privacy-conscious telemetry (13 metrics)

Collect **counts and timings only**. Never collect transcripts, audio, raw client IPs,
speaker identity, or utterance content. The monitor tool (`tools/pilot_monitor.py`)
polls `GET /metrics` and redacts the token from all output.

| # | Metric | Source | Why it is safe |
|---|---|---|---|
| 1 | active_sessions | /metrics | count only |
| 2 | client_ips (distinct count) | /metrics | count, not addresses |
| 3 | outbound_queue_total | /metrics | depth count |
| 4 | outbound_queue_max | /metrics | depth count |
| 5 | asr_executor_queue | /metrics | backlog count |
| 6 | event_loop_delay_ms | /metrics | timing |
| 7 | rss_mb | /metrics | memory size |
| 8 | uptime_s | /metrics | timing |
| 9 | turns_completed | operator aggregate of turn events | count |
| 10 | turn_success_rate | operator aggregate | ratio |
| 11 | first_audio_ms p50/p95 | server latency events | timing |
| 12 | asr_error_count | server error events (stage=asr) | count |
| 13 | close_code_counts (4401/4403/4408/4410/4429/1009/1003) | operator aggregate | counts |

Metrics 1–8 are exposed directly by `/metrics` (token-gated, fail-closed). Metrics
9–13 are aggregated by the operator from the server's per-turn `latency`/`error`
events and WebSocket close codes — still counts/timings, no content. `/metrics`
itself carries **no transcripts, audio, or client IPs**.

Run the monitor:

```
INDICVOICE_TOKEN=<secret> python tools/pilot_monitor.py --port 8443 --tls \
    --interval 2 --duration 600 --out pilot_metrics.jsonl \
    --alert-loop-ms 250 --alert-rss-mb 1500 --alert-sessions 5
```

It prints one secret-free status line per poll, raises `[ALERT]` on threshold
breaches, and appends a JSONL time series. Tests: `tests/test_pilot_monitor.py` (12).

## 5. Failure handling (what the server already does)

| Condition | Server behaviour | Operator action |
|---|---|---|
| Bad/missing token | close 4401 | check token/ticket flow; rotate if leaked |
| Foreign Origin | close 4403 | fix `INDICVOICE_ALLOWED_ORIGINS`; never disable the check |
| Per-IP limit (8) | close 4429 | reduce concurrent tabs/testers per IP |
| Idle timeout | close 4408 | normal; tester reconnects |
| Max session duration | close 4410 | normal; long calls are capped |
| Oversized frame/payload | close 1009 | check client/gateway framing |
| Malformed telephony JSON | close 1003 | check gateway payload format |
| ASR decode/cloud error | `error` event (stage=asr), **call survives** | watch asr_error_count; see incident 6 |

The conservative ASR fallback and the streaming rollback switches are preserved:
append `&streaming=0` per call, or start with `--no-streaming`, to force block decode.

## 6. Incident procedures (9 scenarios)

1. **Auth-failure spike (4401).** Token misconfigured or leaked. Verify fail-closed
   behaviour, rotate `INDICVOICE_TOKEN`, re-issue tickets, confirm `/health` auth=token.
2. **Origin rejections (4403).** Allowlist misconfigured. Correct
   `INDICVOICE_ALLOWED_ORIGINS` to the exact pilot origin; do **not** widen to `*`.
3. **Sustained event-loop delay > 250 ms.** CPU saturation; audio stutters. Reduce
   concurrency to the Phase G safe level; consider `--no-streaming` to drop partial
   decodes; let the machine cool.
4. **Outbound queue backpressure (queue_max high).** Slow client/network. Cap sessions,
   check for 1009 closes, verify tester bandwidth; do not raise the queue cap to hide it.
5. **RSS climbing toward the limit.** Memory pressure / over-long sessions. Enforce
   `INDICVOICE_MAX_SESSION`, recycle the server during a quiet window, watch rss_mb.
6. **ASR error rate up (cloud timeout).** Groq outage/degradation. The call survives via
   the error event; switch en to a local model or block mode, pause cloud-heavy turns,
   confirm no key is exposed in error messages (truncated to 200 chars).
7. **Latency degradation (e2e p95 up).** Thermal/load. Reduce concurrency, add cooldown,
   re-measure; compare against the Phase F budget. Do not lower endpoint silence to fake
   an improvement.
8. **Security incident (token leaked / unauthorized access) — EMERGENCY ROLLBACK.**
   Stop the pilot server you started, rotate the token, re-bind to 127.0.0.1, audit
   access, and only re-expose after the cause is fixed. Never terminate pre-existing
   processes you did not start.
9. **Bad deployment / regression — EMERGENCY ROLLBACK.** Revert to the last known-good
   commit, restart with `--no-streaming` (conservative block ASR) bound to localhost with
   a token, verify `/health` and one test turn, then re-enable streaming gradually.

### Emergency rollback (exact steps)

```
# 1. Stop ONLY the pilot server you started (identify its PID first; never kill others)
# 2. Revert to the last known-good commit
git log --oneline -5
git revert --no-edit <bad-commit>        # or checkout the known-good tag
# 3. Restart conservative, localhost, authenticated
set INDICVOICE_TOKEN=<new-secret>
.venv313/Scripts/python.exe -m src.call_server --host 127.0.0.1 --port 8000 --no-streaming --warm hi
# 4. Verify
curl http://127.0.0.1:8000/health        # auth=token, voices ready
# 5. Run one test turn, confirm audio, then re-enable streaming gradually
```

## 7. Pilot exit criteria

- 100% of pilot turns complete without dropped calls (errors surfaced, not fatal).
- Event-loop delay and RSS stay within alert thresholds at the chosen concurrency.
- No security control weakened; no unauthorized recording; no secret in logs/output.
- Tester feedback captured against the Phase C/E instruments; physical results marked
  PASS — manually verified only where actually performed, otherwise NOT TESTED.

## 8. Acceptance gate (pilot)

**PARTIAL / NOT TESTED.** The protocol, monitoring tool (12 tests) and incident
procedures are delivered and verified locally. An actual pilot with real testers has
**not** been run in this environment; the gate becomes PASS only after a controlled
pilot executes against these criteria with recorded, honest results.