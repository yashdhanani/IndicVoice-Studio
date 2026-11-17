# IndicVoice — Physical Phone-over-LAN Test Guide (Real-World V2, Phase D)

Date: 2026-11-17
Status vocabulary: PASS (automated) / PASS — manually verified / PARTIAL / FAIL / NOT TESTED / NOT APPLICABLE.

**Honesty statement:** no physical smartphone was available in this
environment. All 12 physical verification items below are **NOT TESTED** and
are written as a reproducible procedure for the person who has a phone.
What *was* executed here is an automated localhost check of the TLS/auth
plumbing (§3) — it proves the server side of the phone path, not the phone
experience.

## 1. Setup (reproducible)

Prerequisites: Windows dev machine with `.venv313`, models downloaded,
`INDICVOICE_TOKEN` set in `.env` (a long random secret), phone and PC on the
same Wi-Fi network (client isolation must be off on the router).

1. **Start the HTTPS server** (binds all interfaces, port 8443, warms all 12
   languages):
   ```bat
   start_voice_phone.bat
   ```
   Equivalent: `.venv313\Scripts\python.exe -m src.call_server --host 0.0.0.0 --port 8443 --tls --warm hi gu mr bn ta te kn ml pa or as en`
   The server **refuses to start** on a non-localhost bind without a token
   (fail-closed; verified automated, L9 below). Never bypass this.
2. **Find the LAN address**: `ipconfig` → IPv4 of the Wi-Fi adapter
   (e.g. `192.168.1.6`). The generated certificate automatically includes
   this IP in its SANs (`src/tls_cert.py`); if the IP changed since the cert
   was created, delete `certs/` and restart to regenerate.
3. **Firewall**: allow inbound TCP 8443 for the Python interpreter on the
   *Private* profile only:
   ```powershell
   New-NetFirewallRule -DisplayName "IndicVoice LAN 8443" -Direction Inbound -Protocol TCP -LocalPort 8443 -Profile Private -Action Allow
   ```
   Remove the rule after testing (`Remove-NetFirewallRule -DisplayName "IndicVoice LAN 8443"`).
   Do not open the port on Public/Domain profiles.
4. **On the phone**: open `https://<pc-ip>:8443/` — accept the self-signed
   certificate warning once (see §4 for what this does and does not mean).
5. **Authenticate**: preferred flow is the page's ticket exchange (the token
   travels in an `Authorization` header via `POST /auth/ticket`, then the WS
   uses a single-use 60 s `?ticket=`). Legacy fallback:
   `https://<pc-ip>:8443/?token=<token>` — works, but the token then sits in
   browser history and URL logs; use only on a trusted LAN and rotate after.
6. Grant the microphone permission when prompted.

Record for every item: date, phone model + OS version, browser + version,
PC build/commit, Wi-Fi band (2.4/5 GHz), observed behavior, status.

## 2. The 12 verification items (all NOT TESTED)

| # | Item | Procedure | Expected | Status |
|---|---|---|---|---|
| 1 | Server network binding | `netstat -ano \| findstr 8443` on the PC while server runs | listening on `0.0.0.0:8443` (not only 127.0.0.1) | NOT TESTED |
| 2 | LAN address discovery | phone browser reaches `https://<pc-ip>:8443/` | page loads; correct PC IP from `ipconfig` | NOT TESTED |
| 3 | Firewall settings | with rule absent, page must fail to load; with Private-profile rule, loads | no silent exposure on public networks | NOT TESTED |
| 4 | HTTPS certificate behavior | observe the warning; accept; reload | warning appears once per browser; after acceptance mic prompt is offered (secure context); note exact warning text per browser | NOT TESTED |
| 5 | WSS connectivity | start a call; watch state chip / devtools remote inspect if available | WSS upgrade succeeds through the same accepted cert; no mixed-content block | NOT TESTED |
| 6 | Authentication | (a) no token → rejected; (b) wrong token → rejected; (c) valid ticket flow → connected | close code 4401 on (a)/(b); page shows a clear auth error, not a hang | NOT TESTED |
| 7 | Microphone permissions | accept prompt; then repeat with permission denied (site settings) | accept: mic meter moves; deny: clear error, no crash (mirrors M01/M02) | NOT TESTED |
| 8 | Audio transmission | speak 5 sentences per language family (Indic local, Dravidian cloud, en); note transcripts | native-script transcripts, no mojibake; partials appear while speaking | NOT TESTED |
| 9 | Audio playback | listen to replies; on iOS verify playback starts after a user tap | audible, undistorted reply; note first-audio delay subjectively and with the page timer if shown | NOT TESTED |
| 10 | Session disconnect | end call via UI; then force-close the browser tab | server releases session and per-IP slot (server log); new call connects immediately | NOT TESTED |
| 11 | Idle timeout | connect, stay silent past `INDICVOICE_IDLE_TIMEOUT` (default 180 s) | server closes with 4408; page surfaces the close, reconnect works | NOT TESTED |
| 12 | Recovery after network loss | toggle phone Wi-Fi off 10 s mid-call, back on | old socket closes cleanly; fresh call connects; no stuck "connected" state | NOT TESTED |

Also record (carried from the V1 reliability checklist C2): phone lock/unlock
mid-call behavior — session survival vs clean reconnect differs by OS;
document what actually happens rather than assuming.

## 3. What WAS verified here (automated, localhost only)

Tool: `benchmarks/check_lan_tls.py` (new in V2; regression tests in
`tests/test_lan_tls_check.py`, 7 tests). It starts a task-owned
`src.call_server --tls` on a free localhost port with a **random throwaway
token** (never the real `.env` token), runs real HTTPS/WSS requests, and
tears the server down. No credential value is written to the report.

Evidence: `benchmarks/results/realworld_v2/lan_tls_check_v2.json` (all 9 PASS,
2026-11-17). Certificate observed: CN=IndicVoice local, self-signed,
SANs `localhost, 127.0.0.1, 192.168.1.6`, expires 2029-02-19.

| Check | Result |
|---|---|
| L1 HTTPS `/health` responds, `auth=token` enforced | PASS |
| L2 Self-signed cert properties (SANs include loopback + LAN IP, unexpired) | PASS |
| L3 WSS without credentials → close 4401 (fail-closed) | PASS |
| L4 `POST /auth/ticket`: valid Bearer→200, wrong→401, missing→401 | PASS |
| L5 WSS with one-time ticket admitted (socket stays open) | PASS |
| L6 Ticket replay rejected (single-use) → 4401 | PASS |
| L7 WSS with legacy `?token=` admitted | PASS |
| L8 Plain HTTP on the TLS port fails | PASS |
| L9 Non-localhost bind without token refuses startup (exit 1) | PASS |

Checker incident (recorded): the first run reported L5/L7 FAIL because the
checker waited for a `connected` greeting on `/ws/voice` — that endpoint
sends no greeting (only `/ws/telephony` does); admission means the socket
stays open. The checker was fixed (not the server, not the expectation);
first-run report preserved as `lan_tls_check_v2_run1_checker_bug.json`.

These checks cover items 1 (partially: localhost bind only), 4 (cert
properties, not browser warning UX), 5 (WSS over TLS, localhost), 6 (auth
matrix) at the protocol level. Items 2, 3, 7–12 are inherently physical and
remain NOT TESTED.

## 4. Self-signed vs publicly trusted TLS — do not conflate

| Aspect | Self-signed (this guide) | Publicly trusted (production) |
|---|---|---|
| Browser warning | yes, once per browser/device; user must accept | none |
| Secure context / mic eligibility | yes **after** acceptance (`https://` is what matters) | yes |
| Protection against MITM on the LAN | **none** — anyone can impersonate the cert; accept only on a trusted network, verify the fingerprint if in doubt | yes (CA-validated) |
| Token in URL risk | same as production; prefer the ticket flow | prefer ticket flow; token only via header |
| iOS quirks | some iOS versions require installing/trusting the cert profile for full trust; document observed behavior | not needed |
| Setup | `--tls` auto-generates `certs/` (git-ignored) | real cert + key via `--cert/--key`, or a reverse proxy (see DEPLOYMENT_V1) |

**Do not weaken browser security to make testing easier**: no disabling
certificate checks in the phone browser, no `http://` mic hacks, no
`--ignore-certificate-errors` flags as a "fix". The only sanctioned path is
accepting the self-signed warning once on a trusted LAN, or deploying a
trusted certificate.

## 5. Completion gate

Phase D is complete only when items 1–12 are executed on at least one real
Android phone and one real iPhone (Safari), each row updated with date,
device, browser and observed notes, and the results filed under
`benchmarks/results/realworld_v2/`. Until then: server-side plumbing
PASS (automated); physical phone validation **NOT TESTED**.