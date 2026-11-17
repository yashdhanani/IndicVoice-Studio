# IndicVoice production readiness report

Date: 2026-11-17 · Assessor scope: full codebase audit + streaming-ASR engineering pass.
Every score below is justified by evidence in `docs/INDICVOICE_TECHNICAL_AUDIT.md`,
`docs/INDICVOICE_CHANGELOG.md` and `benchmarks/results/`. Categories where nothing was
measured are scored on implementation state only and say so.

## Scorecard (0–100)

| Category | Weight | Score | Justification |
|---|---|---|---|
| Recognition accuracy | 20% | 70 | Streaming preserves block accuracy exactly — measured. On the synthesized 36-clip set: CER 0.00–0.09 for 9/12 languages; `as` 0.268 (bn-model workaround), `en` 0.141 driven by one bad clip. Absolute values are optimistic (TTS audio, n=3/lang); real-recording accuracy is unmeasured. |
| Latency | 20% | 62 | ASR stage: streaming p50 0–530 ms on 10/12 languages (measured A/B). E2E EOU→first-audio not benchmarked; single live smoke turn showed 721–1074 ms. The brief's 300–500 ms E2E target is **not met / not proven**. |
| Voice naturalness | 10% | 45 | Humanizer, clause pauses, seam blending, room tone implemented and audible in smoke audio, but **no MOS or listener study exists** — score reflects implementation only, not verified quality. |
| Reliability | 15% | 60 | ASR errors no longer drop calls (tested); watchdog fixed (tested); barge-in socket race mitigated but not stress-tested; no load test, no multi-turn stability test, no concurrency data. |
| Security & privacy | 10% | 45 | Constant-time token compare, XSS fixed, no secrets in logs/reports, TLS available. But: default open access, token in query string, no inbound size/rate limits, no per-IP caps. Not safe beyond localhost as-is. |
| Observability | 5% | 40 | Per-turn latency events + strategy info + `/health` readiness (backend-aware). No structured logs, turn IDs, metrics, or alerting. |
| Testing & CI | 10% | 65 | 45 automated tests across unit/WS-integration layers, all passing, covering every fixed defect except D9. No CI, no git, other languages' WS paths not individually tested. |
| Evaluation rigor | 5% | 45 | Real measurement pipeline: real-time feeding, server-matching endpoint semantics, accuracy-gated A/B, honest noise handling. But the corpus is **synthesized TTS starter audio** (3/lang), not the real human recordings (≥20/lang) the brief requires; no robustness or naturalness sets. |
| Documentation & rollback | 5% | 75 | Inventory, audit, changelog, eval framework, roadmap, this report; runtime kill switch restores block behavior. No git history yet (P0.1). |

**Weighted total: 61 / 100** — a solid single-machine prototype with measured,
accuracy-safe streaming ASR; **not production-ready for public traffic**. The gap is
concentrated in security hardening (P0), measurement depth (P1), and untested
concurrency/quality (P2), all itemized in the roadmap.

## What is verified vs not (summary)

- **Implemented + tested + measured**: pseudo-streaming ASR with accuracy parity
  (12/12 languages), ASR-latency improvements (9 languages clearly, 2 flat, 1 noise),
  9 audit defect fixes, 45-test suite.
- **Implemented + tested, not benchmarked**: telephony μ-law path, token auth,
  watchdog, error survival, block-mode parity.
- **Implemented, not verified**: D9 race mitigation, humanizer naturalness,
  concurrency behavior, non-hi WS language paths.
- **Not implemented**: CI, git, inbound limits, header-token transport, MOS study,
  ≥20/lang corpus, E2E A/B, native `as` ASR.

## Deployment guide (single machine, current state)

```bash
# runtime: .venv313 (Python 3.13, sherpa-onnx 2.0.1). Do not use the old .venv.
cd "Voice model"
PYTHONIOENCODING=utf-8 .venv313/Scripts/python.exe -m src.call_server --port 8000 --warm hi en
```

- **Localhost only by default.** For LAN/phone access set `ACCESS_TOKEN` in `.env`
  and start with `--tls` (self-signed cert auto-generated via `src/tls_cert.py`);
  clients must then use `wss://` and `?token=…`. Until P0.2/P0.3 land, treat any
  non-localhost exposure as trusted-network-only.
- **Readiness**: `GET /health` — per-language backend/ready/asr flags, supertonic
  availability, LLM probe. `ok:true` requires all 12 voices ready.
- **Smoke after deploy**: `python tools/smoke_streaming.py eval_data/hi_01.wav hi`
  against the running server; expect identical transcripts in both modes and audio back.
- **Tests before deploy**: `python -m unittest discover tests` (≈2 min, no cloud calls).
- Models, language mappings and `.env` were **not modified** by this engagement;
  no model re-download is needed.

## Rollback guide

Three levels, cheapest first:

1. **Per call**: connect with `?streaming=0` — exact pre-engagement block pipeline.
2. **Per server**: start with `--no-streaming` — streaming code never runs;
   all other fixes (error survival, auth compare, watchdog, health) remain.
3. **Full code rollback**: no git history exists yet (D4/P0.1). Until P0.1 is done,
   keep a zip snapshot of `src/` before any further change. After P0.1:
   `git revert <commit>` — the streaming work is additive (`src/streaming_stt.py`,
   eval `--mode ab`, tests) plus localized edits in `call_server.py`,
   `sts_pipeline.py`, `tts_engine.py`, `config.py` listed in the changelog.

**Rollback triggers**: any CER/WER regression on the A/B gate, any call-drop report,
or p95 ASR latency worse than the block baseline on the expanded corpus.

## Top 5 actions before production

1. P0.1 git + snapshot discipline (0.5 d) — everything else depends on it.
2. P0.2/P0.3 auth transport + inbound limits (2 d) — public exposure is unsafe today.
3. P1.1/P1.2 corpus expansion + E2E A/B (≈1 wk) — replaces thin numbers with real ones.
4. P1.3 CI running the 45 tests + accuracy gate (1 d).
5. P2.3 concurrency load test (2–3 d) — single-call behavior is verified; multi-call is unknown.