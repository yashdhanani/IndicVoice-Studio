# IndicVoice production readiness report

Date: 2026-11-17 (re-scored after Production Hardening V1) · Assessor scope:
full codebase audit + streaming-ASR engineering pass + hardening phases A–J.
Every score below is justified by evidence in `docs/INDICVOICE_TECHNICAL_AUDIT.md`,
`docs/INDICVOICE_CHANGELOG.md`, `docs/PRODUCTION_V1_FINAL_REPORT.md` and
`benchmarks/results/` (baseline + `production_v1/`). Categories where nothing
was measured are scored on implementation state only and say so.

## Scorecard (0–100)

| Category | Weight | Score | Prev | Justification |
|---|---|---|---|---|
| Recognition accuracy | 20% | 72 | 70 | Streaming/block parity reproduced exactly in counterbalanced re-runs (12/12 languages, CER/WER identical). On the synthesized 36-clip set: CER 0.00–0.09 for 9/12 languages; `as` 0.268 (bn-model workaround), `en` 0.141 driven by one bad clip. Absolute values remain optimistic (TTS audio, n=3/lang); **real-recording accuracy is still unmeasured (0/240 collected)**. |
| Latency | 20% | 50 | 62 | Now measured end-to-end, and the measurement lowered the score: 2×40 live turns give e2e p50 1130 ms (hi) / 1264 ms (en), p95 2766 / 2887 ms. The 300–500 ms E2E target is **not met** (structural floor: endpoint silence + LLM first token). ASR-stage streaming gains are real but load-dependent — re-run 1 showed block-equivalent worst cases. Honesty requires scoring the measured E2E, not the best stage. |
| Voice naturalness | 10% | 45 | 45 | Humanizer, clause pauses, seam blending, room tone implemented; TTS speed measured (RTF p50 0.11–0.20, all 12 tiny voices). **No MOS or listener study exists** — score reflects implementation only, not verified quality. |
| Reliability | 15% | 68 | 60 | ASR errors survive (tested); watchdogs fixed (tested); abuse caps + bounded queue (tested); concurrency matrix 33/33 turns OK at 1/2/3/5 sessions, RSS stable at 732.5 MB. Still missing: D9 race under stress, multi-hour soak, physical device validation (C1–C5 NOT TESTED). |
| Security & privacy | 10% | 72 | 45 | Fail-closed non-localhost bind, constant-time compare, one-time ticket transport (server-side), Origin allowlist, frame/payload/session/utterance/queue caps, XSS sinks eliminated and statically pinned — all automated-tested. Residuals: web client still on legacy `?token=`, no per-message rate limit or ticket lockout, self-signed TLS only, no external pentest. Safe for trusted-network exposure with a token; not hardened for hostile public traffic. |
| Observability | 5% | 45 | 40 | Per-turn latency events, strategy info, truncation warnings, `/health` readiness incl. `auth` mode. Still no structured logs, turn IDs, metrics export, or alerting. |
| Testing & CI | 10% | 72 | 65 | 72 automated tests (was 45 at first scoring), all passing, none weakened; every fixed defect except D9 has a regression test. CI workflow authored with model-free fast tier + manual model tier, skip semantics verified locally — but **never executed on GitHub** (no remote). |
| Evaluation rigor | 5% | 60 | 45 | Real measurement pipeline expanded: live E2E benchmark (2 runs), concurrency matrix, TTS RTF bench, noise matrix, LLM script check, counterbalanced A/B with order groups. Corpus is still **synthesized TTS starter audio** (3/lang), not the ≥20 real recordings/language required; no human naturalness set. |
| Documentation & rollback | 5% | 85 | 75 | Git history with 6 checkpoints; inventory, audit, changelog, eval framework, roadmap, security/CI/deployment/E2E/concurrency/reliability reports, final report. Three rollback levels preserved; `git revert` not drilled. |

**Weighted total: 63 / 100** (prev 61). Hardening raised security, reliability,
testing and evaluation scores; the first honest E2E measurement lowered the
latency score. Net: a measurably safer, better-instrumented single-machine
system whose two biggest gaps are now *proven* rather than suspected —
real-world accuracy evidence and end-to-end latency. **Not production-ready
for public traffic.** Blockers and priorities: `PRODUCTION_V1_FINAL_REPORT.md`
§K/§L.

## What is verified vs not (summary)

- **Implemented + tested + measured**: pseudo-streaming ASR with reproducible
  accuracy parity (12/12 languages, counterbalanced re-runs); security controls
  B1–B7; 72-test suite; E2E latency (hi/en, 2×40 live turns); concurrency
  1/2/3/5 (33/33); TTS speed (12 langs); noise matrix (hi/gu/kn, synthetic
  noise); LLM script consistency (12/12).
- **Implemented + tested, not benchmarked**: telephony μ-law path, ticket
  auth, watchdogs, error survival, block-mode parity, outbound queue cap.
- **Implemented, not verified**: D9 race mitigation, humanizer naturalness,
  >60 s live utterance truncation, non-hi/en live E2E paths, browser-runtime
  XSS behavior.
- **Not implemented / not collected**: real corpus (0/240), MOS study, CI
  execution on GitHub, git remote, per-message rate limiting, ticket-endpoint
  lockout, client migration to tickets, native `as` ASR, structured
  observability.

## Deployment guide (single machine, current state)

```bash
# runtime: .venv313 (Python 3.13, sherpa-onnx 2.0.1). Do not use the old .venv.
cd "Voice model"
PYTHONIOENCODING=utf-8 .venv313/Scripts/python.exe -m src.call_server --port 8000 --warm hi en
```

- **Localhost open-dev mode** announces itself at startup and in `/health`
  (`auth: open-dev`). Any non-localhost bind **requires** `INDICVOICE_TOKEN`
  (fail-closed, tested). For LAN/phone access set the token in `.env` and start
  with `--tls`; prefer the ticket flow (`POST /auth/ticket` with
  `Authorization: Bearer …` → single-use `?ticket=`) over legacy `?token=`.
- **Capacity**: ≤2–3 concurrent calls recommended on the reference 4-core
  laptop (measured; level 5 verified survivable, level 10 untested by design).
- **Readiness**: `GET /health` — per-language backend/ready/asr flags,
  supertonic availability, LLM probe, `auth` mode. Alert if a production host
  reports `open-dev`.
- **Smoke after deploy**: `python tools/smoke_streaming.py eval_data/hi_01.wav hi`
  against the running server; expect identical transcripts in both modes and
  audio back.
- **Tests before deploy**: `python -m unittest discover tests` (≈2 min, no
  cloud calls). Full topology/env/rollback detail: `INDICVOICE_DEPLOYMENT_V1.md`.
- Models, language mappings and `.env` were **not modified** by this
  engagement; no model re-download is needed.

## Rollback guide

Three levels, cheapest first (all preserved):

1. **Per call**: connect with `?streaming=0` — exact pre-engagement block pipeline.
2. **Per server**: start with `--no-streaming` — streaming code never runs;
   all other fixes (error survival, auth, watchdogs, caps, health) remain.
3. **Full code rollback**: git history exists since `5768a6d` (baseline).
   `git revert <commit>` — the streaming work is additive
   (`src/streaming_stt.py`, eval `--mode ab`, tests) plus localized edits in
   `call_server.py`, `sts_pipeline.py`, `tts_engine.py`, `config.py` listed in
   the changelog. Revert has not been drilled (PARTIAL).

**Rollback triggers**: any CER/WER regression on the A/B gate, any call-drop
report, or p95 ASR latency worse than the block baseline on the expanded corpus.

## Top 5 actions before production

1. Collect the real corpus (0/240 today) and re-measure accuracy on it — tooling ready.
2. Structural E2E latency work (endpointing + LLM TTFT) — needs feature-freeze lift.
3. Activate CI on a remote; verify fast + model tiers on GitHub.
4. Execute physical validation C1–C5 + multi-hour soak at 2–3 concurrent calls.
5. Human MOS study + LLM content-quality rubric (script checks miss factual errors).