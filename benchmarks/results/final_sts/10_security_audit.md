# 10 — Security Audit

## Controls present

- Auth: opt-in shared token `INDICVOICE_TOKEN`; fail-closed non-localhost bind without token (tested).
- Constant-time token compare; one-time `?ticket=` via `POST /auth/ticket` + `Authorization: Bearer` (server-side).
- Origin allowlist (`INDICVOICE_ALLOWED_ORIGINS`); localhost always allowed.
- Inbound limits: max frame size, telephony payload cap, utterance/session duration caps, bounded outbound queue (tested).
- XSS: fallback page + health backend string use textContent (tests/test_xss.py).
- TLS: self-signed RSA-2048/SHA-256, SANs localhost+LAN IPs, 825 days; private key unencrypted in `certs/` (git-ignored). Adequate for LAN; not for internet.
- Secrets: `.env` git-ignored, loaded without overriding real env; keys not logged (error strings carry HTTP status/body excerpts only).
- Audio privacy: no server-side per-call persistence; eval recordings git-ignored; `audio_out/` local smoke outputs.

## Gaps / not tested

- Web client still uses legacy `?token=` (migration to tickets planned).
- No per-message rate limiting or ticket-endpoint lockout.
- No per-user identity, no rate limiting by IP beyond connection.
- Self-signed TLS not sufficient for public production.
- No external penetration test.
- Development config exposure: `/health` reports auth mode; alert if production host reports `open-dev`.
- Cloud calls (Groq LLM + en ASR) send audio/text to third party — must be disclosed to callers.

## Conclusion

Security is adequate for trusted-network (LAN) exposure with a token and TLS. Not hardened for hostile public traffic. No production security claim.