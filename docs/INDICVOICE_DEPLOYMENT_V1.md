# IndicVoice — Deployment Guide V1 (Production Hardening V1, Phase I)

Date: 2026-11-17 · Applies to commits `5768a6d` → `8b9efc1` and later.

## Supported topology: ONE process, ONE worker

The server is deliberately single-worker. Do **not** add uvicorn/gunicorn
workers blindly:

1. **Models are process-wide caches.** `shared_stt`, the shared TTS voices
   and `TTSPool` live in one process's memory. Every extra worker duplicates
   the full model working set (hundreds of MB each — see measured RSS in
   `benchmarks/results/production_v1/concurrency_v1.json`).
2. **Security state is in-process.** The one-time ticket store
   (`_tickets`) and the per-IP session counter (`sessions_by_ip`) are plain
   in-memory dicts. With multiple workers, a ticket issued by worker A is
   unknown to worker B, and per-IP limits multiply by the worker count.
3. **CPU is the bottleneck, not I/O.** ASR/TTS are CPU-bound ONNX decodes;
   on the reference 4-core laptop, concurrency 3–5 already saturates it
   (Phase G report). More processes would thrash, not scale.

Horizontal scaling, when actually needed, requires: a shared ticket store
(Redis or signed short-lived tokens), a shared rate-limit store, and
per-instance model memory budgeting. That is a documented future project,
not a flag to flip.

## Deployment A — LAN phones (supported, scripted)

`start_voice_phone.bat` (Windows): HTTPS on 0.0.0.0:8443 with a self-signed
certificate, all 12 languages warmed.

Pre-flight:
1. `.env`: set `INDICVOICE_TOKEN` to a long random string (**required** —
   the server refuses a non-localhost bind without it).
2. `.env`: `GROQ_API_KEY` (or Ollama/OpenAI equivalents).
3. Phones open `https://<pc-ip>:8443/?token=<token>` and accept the
   certificate warning. Browsers grant mic access only on secure origins.
4. If the page is served from a different origin, add it to
   `INDICVOICE_ALLOWED_ORIGINS`.

Status: script present and fail-closed behavior automated-tested; physical
phone validation **NOT TESTED** (see `INDICVOICE_AUDIO_RELIABILITY_REPORT.md`).

## Deployment B — public host behind a TLS proxy (recommended shape)

Terminate TLS at a reverse proxy with a real certificate; run the app on
localhost only:

```
python -m src.call_server --host 127.0.0.1 --port 8000 --warm hi en <langs...>
```

nginx sketch (WebSocket upgrade + timeouts above the 180 s idle watchdog):

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
}
```

Required env: `INDICVOICE_TOKEN`, `INDICVOICE_ALLOWED_ORIGINS=https://your.domain`.
The proxy must forward `/auth/ticket` (POST) and both WebSocket endpoints.
Do not log query strings at the proxy if legacy `?token=` clients remain —
or migrate them to the ticket flow first (`INDICVOICE_SECURITY_HARDENING.md`, B2).

Status: configuration documented; **NOT TESTED** end-to-end (no public host
or proxy in this environment).

## Environment checklist

| Variable | Required | Purpose |
|---|---|---|
| `INDICVOICE_TOKEN` | for any non-localhost bind | fail-closed auth; ticket exchange |
| `GROQ_API_KEY` (or OpenAI/Ollama config) | for cloud LLM/ASR | `.env`, never committed |
| `INDICVOICE_ALLOWED_ORIGINS` | when page origin ≠ server origin | browser Origin allowlist |
| `INDICVOICE_STT_MODE` | optional | `fast` (cloud for ta/te/kn/en) vs `accurate` (all local) |
| `INDICVOICE_IDLE_TIMEOUT` / `MAX_UTTERANCE` / `MAX_SESSION` / `MAX_QUEUE` | optional | abuse caps (defaults 180 s / 60 s / 1800 s / 4096) |
| `INDICVOICE_TICKET_TTL` | optional | one-time ticket lifetime (default 60 s) |

## Startup, shutdown, restarts

- Startup warms the listed languages (~2–3 s each first time); first call
  otherwise pays model-load latency.
- No persistent state: restarting drops in-flight calls (clients see a
  socket close). There is no call state to migrate or corrupt.
- Shutdown: Ctrl+C / SIGTERM. Benchmark harnesses kill only their own
  process tree (`taskkill /T` on Windows because the venv python is a
  launcher with a child interpreter).
- Port conflicts: the app fails to bind; identify the owner
  (`netstat -ano`) before changing ports — never kill unknown processes.

## Rollback (three levels, preserved)

| Level | Action | Effect | Verification |
|---|---|---|---|
| Per call | `?streaming=0` on the WS URL | block ASR for that call only | PASS (automated: `test_block_turn_end_to_end`) |
| Server | `--no-streaming` flag | block ASR for all calls | PASS (flag path exercised in suite/smoke) |
| Code | `git revert` to `c483f3d` (P0 hardening) or `5768a6d` (streaming baseline) | full feature rollback | PARTIAL — git history exists; a revert has not been executed/drilled |

Accuracy is identical in both ASR modes by construction (final transcript
is always a full-buffer decode), so rollback never trades accuracy for
stability.

## Resources and capacity (reference machine)

Intel i7-8565U (4 cores/8 threads, 15 W), 16 GB RAM, Windows 11, Python
3.13. Measured numbers live in:

- `benchmarks/results/production_v1/e2e_v1.json` — single-session latency
  percentiles + server RSS series.
- `benchmarks/results/production_v1/concurrency_v1.json` — 1/2/3/5-session
  matrix, success rates, RSS peak. Level 10 deliberately excluded on this
  hardware.

Expect run-to-run variance on laptop CPUs (thermal/power limits); the
baseline doc records a 2.7× decode-time spread between runs. Capacity
planning must use the concurrency report's percentiles, not best-case runs.

## Monitoring today (and what's missing)

- `/health`: per-language voice/ASR readiness, LLM backend, and `auth`
  mode (`token` vs `open-dev`) — alert if a production host reports
  `open-dev`.
- Per-turn `latency` events (asr/llm/tts/first_audio) and `asr_strategy`
  on transcripts; `warning` events on utterance truncation.
- Missing: structured logs, turn IDs, metrics export, alerting. Roadmap P3.

## Pre-go-live checklist

1. Token set; `/health` reports `auth: token`; fail-closed bind verified.
2. TLS in front (proxy CA cert or `--tls` for LAN); no plain HTTP beyond localhost.
3. Origin allowlist matches the real page origin.
4. Caps reviewed for the expected traffic; per-IP limit sane for NAT'd callers.
5. Rollback level chosen and drilled (`--no-streaming` restart).
6. Real-device checklists C1–C5 executed (`INDICVOICE_AUDIO_RELIABILITY_REPORT.md`).
7. Real-recording dataset collected and CER/WER re-measured (Phase D gate).