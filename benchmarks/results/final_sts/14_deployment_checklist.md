# 14 — Deployment Checklist

## Pre-deploy (required)

- [ ] Run `.venv313/Scripts/python.exe -m unittest discover -s tests -t .` → must be 186 OK.
- [ ] Set `INDICVOICE_TOKEN` in `.env` for any non-localhost bind.
- [ ] Confirm `/health` reports `auth` mode appropriate to environment (never `open-dev` in production).
- [ ] TLS: use `--tls` with cert in `certs/`; self-signed only for LAN/trusted networks.
- [ ] Warm models: `--warm hi en` (or target languages).
- [ ] Capacity: ≤2–3 concurrent calls on reference 4-core laptop.
- [ ] Disclose to callers that audio/text goes to Groq (LLM + en ASR).
- [ ] Confirm no API keys in repo / logs.

## Runtime

- Command: `PYTHONIOENCODING=utf-8 .venv313/Scripts/python.exe -m src.call_server --port 8000 --warm hi en`
- LAN/phone: add `--tls` and `INDICVOICE_TOKEN`.
- Disable streaming if needed: `--no-streaming` (restores block pipeline; other fixes remain).
- Per-call kill switch: `?streaming=0`.

## Rollback

1. Per call: `?streaming=0`.
2. Per server: `--no-streaming`.
3. Full code: `git revert <commit>` (history since 5768a6d); not drilled (PARTIAL).

## Monitoring (minimal)

- `/health` (per-language backend/ready/asr, supertonic availability, LLM probe, auth mode).
- Per-turn `latency` events (asr/llm/tts/first_audio).
- Watch for 4408 (idle), 4410 (session max), queue drops.

## NOT included

- No production deployment, DNS, firewall, or public exposure performed by this audit.
- No remote CI executed.