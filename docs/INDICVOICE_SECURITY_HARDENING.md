# IndicVoice — Security Hardening (Production Hardening V1, Phase B)

Date: 2026-11-17 · Baseline commits: `5768a6d` → `c483f3d` → Phase B checkpoint
Status vocabulary: PASS (automated) / PASS — manually verified / PARTIAL / FAIL / NOT TESTED / NOT APPLICABLE.

## Threat model

The server holds a paid LLM API key and local ASR/TTS models. Assets: the
key (cloud spend), model/CPU availability, caller audio privacy, and the
browser DOM of anyone opening the call page. Adversaries considered:

1. **Network neighbors** on the same Wi-Fi/LAN when the server binds beyond localhost.
2. **Malicious web pages** attempting cross-origin WebSocket hijacking or XSS via transcripts/replies.
3. **Abusive clients**: oversized frames, malformed payloads, session flooding, unbounded utterances, slow-drain memory exhaustion.
4. **Token leakage** through URLs (browser history, proxy/access logs, Referer).

Out of scope today: authenticated multi-tenant identity, DDoS at the network
layer, compromised-host scenarios.

## B1 — Fail-closed authentication, explicit dev mode

| Control | Behavior | Status |
|---|---|---|
| Non-localhost bind without `INDICVOICE_TOKEN` | `main()` refuses startup, exit 1, `[security]` message | PASS (`TestBindSecurity`, 4 tests) |
| Empty / wrong `?token=` when a token is configured | close 4401 | PASS (`test_token_auth`, `test_empty_and_invalid_token_rejected`) |
| Constant-time token comparison | `hmac.compare_digest` | PASS (code inspection + tests) |
| Dev mode visibly marked | startup prints `[dev] no INDICVOICE_TOKEN set: open access, localhost development only…`; `/health` reports `"auth": "open-dev"` vs `"token"` | PASS (`test_health_reports_auth_mode`) |
| Localhost open mode | allowed, but only on 127.0.0.1/::1/localhost | PASS |

No insecure development shortcut exists in the production path: the open
mode is reachable only by explicitly binding to localhost, and it announces
itself at startup and in `/health`.

## B2 — Token transport: one-time tickets (migration design)

**Problem with `?token=`**: the long-lived secret appears in the URL, so it
lands in browser history, server/proxy access logs, and potentially Referer
headers. It cannot be revoked per-session.

**New flow (preferred):**

```
POST /auth/ticket
Authorization: Bearer <INDICVOICE_TOKEN>
→ 200 {"ticket": "<random 24-byte urlsafe>", "expires_in": 60}

GET /ws/voice?lang=hi&ticket=<ticket>     (single use, ≤60 s TTL)
```

- The long-lived token travels only in the `Authorization` header.
- Tickets are cryptographically random (`secrets.token_urlsafe(24)`),
  **single-use** (popped on first presentation), expire after
  `INDICVOICE_TICKET_TTL` (default 60 s), and expired entries are purged on
  issue. A leaked ticket is useless after one connection or one minute.
- Wrong/missing bearer → 401; endpoint without a configured token → 400.
- Cross-origin abuse: the endpoint requires a custom `Authorization` header,
  which triggers a CORS preflight; the app serves no CORS headers, so
  browsers block cross-origin reads. Non-browser clients are governed by the
  token itself.

**Backward compatibility / migration:** `?token=` continues to work
unchanged (no protocol break for existing phones/gateways). Migration path:
(1) update the web client to fetch a ticket before opening the socket,
(2) update gateway integrations, (3) optionally add a config flag to reject
legacy `?token=` once all clients have migrated. Step 3 is deliberately not
implemented yet — no client has been migrated, and breaking them would
violate the preserve-working-features rule.

**Limitation (documented, not hidden):** the ticket store is in-process
memory. A multi-worker deployment would need a shared store (Redis or
signed short-lived JWTs); see `INDICVOICE_DEPLOYMENT_V1.md`. Single-worker
is the supported deployment today.

Status: PASS (`test_ticket_endpoint_auth`, `test_ticket_single_use`,
`test_expired_ticket_rejected`, `test_ticket_endpoint_needs_token_configured`).
Client-side migration: NOT TESTED (no browser client change shipped yet).

## B3 — XSS regression protection

- Server fallback page (`_INDEX_HTML`): all dynamic text via `textContent`
  (defect D2, fixed in the baseline audit).
- **D22 (found and fixed in this phase):** `web/app.js` rendered the
  server-provided `v.backend` string from `/health` through an `innerHTML`
  template. A compromised or spoofed health response could inject HTML.
  Fixed: the backend tag is now filled via `textContent`.
- Message bodies, system messages, language names, latency chips, and LLM
  status already used `textContent`; verified by static regression tests.
- `tests/test_xss.py` pins the property: no `innerHTML` in the server page;
  every `innerHTML` template in `app.js` may interpolate only an allowlist
  of compile-time constants, locally computed booleans, and client-side
  timestamps; no `insertAdjacentHTML` / `document.write` / `outerHTML`.

Status: PASS (6 static tests). Browser-runtime XSS probing: NOT TESTED
(no headless browser run against a live malicious transcript).

## B4 — Origin allowlist

- Browser `Origin` must be localhost (always allowed) or an exact match in
  `INDICVOICE_ALLOWED_ORIGINS` (comma-separated, env-driven, lowercased).
- Foreign origin → close 4403. Missing Origin (telephony gateways, scripts)
  is governed by the token instead.

Status: PASS (`test_foreign_origin_rejected`, `test_localhost_origin_allowed`,
`test_allowlisted_origin_allowed`).

## B5 — Abuse limits (all configurable)

| Limit | Default | Env override | Enforcement |
|---|---|---|---|
| Voice binary frame | 64 KiB (2 s of 16 kHz PCM16) | constant | close 1009 |
| Telephony text message | 64 KiB | constant | close 1009 |
| Telephony base64 payload | 32 Ki chars | constant | close 1009 |
| Malformed telephony JSON/base64 | — | — | close 1003 |
| Sessions per IP | 8 | constant | close 4429; slot released on disconnect |
| Utterance length | 60 s | `INDICVOICE_MAX_UTTERANCE` | VAD segment truncated + `warning` event; streaming buffer stops growing at the cap (`StreamingSTT(max_buffer=…)`) |
| Session duration | 1800 s | `INDICVOICE_MAX_SESSION` | watchdog close 4410 |
| Outbound queue | 4096 items | `INDICVOICE_MAX_QUEUE` | `put_nowait`; on Full the session is closed (slow/malicious drain cannot exhaust memory) |

Status: PASS — frame/payload/JSON/per-IP limits and queue cap automated;
utterance cap automated at the `StreamingSTT` level
(`test_max_buffer_cap`); session-duration close automated
(`test_max_session_duration_closes_4410`). A >60 s live utterance through
the full VAD path: NOT TESTED (would need a 60 s+ recording).

## B6 — Idle lifecycle

- Watchdog polls every 5 s; no audio in either direction for
  `INDICVOICE_IDLE_TIMEOUT` (default 180 s) → close 4408, session closed,
  per-IP slot released.
- Max-duration check (B5) runs in the same watchdog → 4410.
- `session.close()` cancels the agent, streamer, and player; handler
  `finally` blocks always release the IP slot.

Status: PASS (`test_idle_watchdog_closes_4408`, `test_max_session_duration_closes_4410`,
`test_per_ip_session_limit` release check).

## B7 — Security regression suite

All security tests run in the standard suite (`python -m unittest discover -s tests`),
no cloud calls, no paid inference:

- `tests/test_ws_server.py`: token auth, empty/invalid token, ticket
  endpoint auth/single-use/expiry/unconfigured, origin allow/deny,
  oversized frames (voice + telephony), malformed JSON, per-IP limit +
  release, idle 4408, max-duration 4410, health auth mode, bind fail-closed
  (4 tests), outbound queue cap.
- `tests/test_xss.py`: 6 static injection-sink tests.
- `tests/test_streaming_stt.py::test_max_buffer_cap`: utterance buffer cap.

**Full suite result: 71/71 PASS in 136.0 s** (was 56 before Phase B; no
existing test was weakened or removed).

## Close-code contract

| Code | Meaning |
|---|---|
| 4401 | missing/invalid token or ticket |
| 4403 | origin not allowlisted |
| 4408 | idle timeout |
| 4410 | max session duration exceeded |
| 4429 | per-IP session limit |
| 1009 | message too big |
| 1003 | malformed telephony payload |

## Remaining gaps (honest list)

| Gap | Status |
|---|---|
| TLS: only self-signed local cert (`--tls`); no CA/proxy termination shipped | PARTIAL — documented in deployment guide |
| Ticket store not shared across workers | NOT APPLICABLE to single-worker deployment; documented |
| No per-message rate limit (only size/session caps) | NOT TESTED as a control; assessed low risk given caps |
| No brute-force lockout on `/auth/ticket` | mitigated by high-entropy token; lockout NOT IMPLEMENTED |
| Live browser XSS probe, external penetration test | NOT TESTED |
| Web client still uses `?token=` (ticket flow server-side only) | PARTIAL — migration path documented above |