# IndicVoice — Security Revalidation (Real-World Validation V2, Phase I)

**Bottom line:** All previously hardened security controls were independently
re-verified and remain intact; **none was weakened**. 20 new model-free regression
tests pass (`tests/test_security_revalidate.py`), on top of the existing
`test_ws_server`, `test_xss`, `test_metrics` and `test_lan_tls_check` suites. The
only gap is a **dependency CVE scan — NOT TESTED** (no `pip-audit`, no authorized
network audit). All work was safe and local-only; no exploitation or external
scanning was performed.

Status vocabulary: PASS (automated) / PASS — manually verified / PARTIAL / FAIL /
NOT TESTED / NOT APPLICABLE.

Evidence: `benchmarks/results/realworld_v2/security_revalidation_v2.json`,
`lan_tls_check_v2.json`. Tests: `tests/test_security_revalidate.py` (20).

---

## 1. Controls re-verified

| Control | Status | Evidence |
|---|---|---|
| Fail-closed token auth | PASS (automated) | `_authorised` rejects missing/wrong/empty token when set; `AuthorisedTests` (6) |
| Constant-time token compare | PASS — code verified | `hmac.compare_digest` at `call_server.py:103,777,847` |
| Credential transport | PASS (automated) | `/auth/ticket` takes Bearer **header**, returns single-use `?ticket=`; legacy `?token=` documented as URL-visible |
| Single-use expiring tickets | PASS (automated) | `_consume_ticket` pops on first use; expiry enforced; stale purged; 192-bit `secrets.token_urlsafe(24)`; `TicketTests` (4) |
| Origin allowlisting | PASS (automated) | hostname parsed; `localhost.evil.com` rejected; no-Origin allowed for non-browser; `OriginTests` (4) |
| XSS / injection sinks | PASS (automated) | `test_xss` (6): `textContent` not `innerHTML`; fallback page safe |
| Inbound frame caps | PASS (automated) | 64 KB voice / 64 KB telephony text / 32 KB payload; oversize → 1009; `FrameCapTests` guards values |
| Per-IP session limit | PASS (automated) | `MAX_SESSIONS_PER_IP=8`; excess → 4429; slots released on disconnect |
| Idle watchdog / max duration | PASS (automated) | idle → 4408; max session → 4410 |
| Insecure-bind refusal | PASS (automated) | non-localhost without token → exit 1; `BindSecurityTests` (3) |
| TLS for phone access | PASS (automated, local) | `check_lan_tls` L1–L9 = 9/9; physical phone NOT TESTED |
| Log redaction | PASS (automated) | uvicorn `log_level=warning` suppresses access logs; banner prints `<your-token>` placeholder; `LogRedactionTests` (2) |
| `/metrics` auth + privacy | PASS (automated) | token-gated fail-closed; counts/timings only; `test_metrics` (3) |
| ASR-error survival (D1) | PASS (automated) | error event `stage=asr`, message truncated 200 chars; socket usable next turn |
| Dependency CVE scan | **NOT TESTED** | `pip-audit` absent; see §3 |

## 2. New regression tests (20, model-free)

`tests/test_security_revalidate.py` — runs without models or cloud keys:

- **AuthorisedTests (6):** open-dev when no token; fail-closed without creds;
  wrong/truncated/extended token rejected; correct token accepted; valid ticket
  accepted exactly once; unknown ticket rejected.
- **TicketTests (4):** 200 tickets unique & ≥32 chars (~192 bits); single use;
  expired (TTL 0) rejected; stale tickets purged on next issue.
- **OriginTests (4):** no-Origin allowed; localhost/127.0.0.1/[::1]/case-insensitive
  allowed; `evil.example`, `localhost.evil.com`, `127.0.0.1.evil.com` rejected;
  allowlist honoured.
- **FrameCapTests (1):** caps not weakened (guards against accidental regression).
- **BindSecurityTests (3):** non-localhost (incl. `::`) without token fails closed;
  with token OK; localhost open OK.
- **LogRedactionTests (2):** `main()` run with models/uvicorn mocked and a secret
  token — asserts the token value **never** appears in stdout, the `<your-token>`
  placeholder does, and uvicorn `log_level=="warning"`; open-dev warning printed
  when no token.

Result: **Ran 20 tests — OK.**

## 3. Dependency security — NOT TESTED + activation

`requirements.txt` is mostly pinned: `sherpa-onnx==2.0.1`, `numpy==2.5.5`,
`scipy==1.18.1`, `fastapi==0.163.1`, `uvicorn==0.54.0`, `websockets==17.4`,
`num2words==0.5.14`, `indic-nlp-library==0.92`, `huggingface_hub==2.4.0`,
`onnx==1.23.2`. Floors (not pinned): `onnxruntime>=1.20`, `cryptography>=42`,
`aiohttp>=3.9`.

No CVE database scan was run (`pip-audit` not installed; network audit not
authorized). To activate:

```
pip install pip-audit
pip-audit -r requirements.txt
pip-audit -r requirements-ci.txt
```

Review any reported advisories; prefer bumping the floor versions over loosening
pins. Do **not** add inference keys to CI to run this.

## 4. Considerations (not vulnerabilities)

- `/health` is unauthenticated by design for monitoring; it exposes backend/model
  names and readiness, **not secrets**. Acceptable on localhost; for a public
  deployment consider gating or minimizing it.
- ASR error events send `str(exc)[:200]` to the connected caller. Cloud SDK errors
  do not embed API keys; truncation limits accidental detail.
- Tickets are single-process in-memory; a multi-worker deployment needs a shared
  store (documented in DEPLOYMENT_V1).

## 5. Acceptance gate (security)

**PASS (automated, local)** for auth, origin, frame/session/duration limits,
watchdog, TLS, log redaction, XSS and `/metrics` privacy. **Dependency CVE scan
NOT TESTED.** No security control was removed or weakened; all 12 language routes
and the conservative ASR fallback / streaming rollback switches are preserved.