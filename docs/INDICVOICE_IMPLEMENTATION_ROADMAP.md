# IndicVoice implementation roadmap

Priorities follow the audit defect register (`docs/INDICVOICE_TECHNICAL_AUDIT.md`)
and the measured A/B results (`docs/INDICVOICE_CHANGELOG.md`). Items marked **done**
were completed and verified this engagement (2026-11-17); everything else is planned.
Effort estimates are engineering judgment, not measurements.

## P0 — blocking for any real deployment

| # | Item | Why | Effort | Status |
|---|---|---|---|---|
| P0.1 | Initialise git, commit current state, fix `.gitignore` (`tools/` ignored, D18) | no rollback path exists today (D4); every future change is unrecoverable | 0.5 d | planned |
| P0.2 | Auth hardening for non-localhost: token out of the query string (header or subprotocol), refuse non-localhost bind without token + TLS (D3 remainder) | query-string tokens land in proxy logs; constant-time compare alone is not enough | 1 d | partial (compare fixed, transport not) |
| P0.3 | Inbound WS limits: max frame size, telephony payload cap, per-IP connection limit (D14) | one malicious client can exhaust memory today | 1 d | planned |
| P0.4 | ASR error survival | one Groq blip dropped the whole call (D1) | — | **done** (fix + regression test) |
| P0.5 | Streaming accuracy guards | stale speculative transcript corrupted kn_02 (D6) | — | **done** (guards + A/B parity all 12 langs) |

## P1 — measurement and regression safety

| # | Item | Why | Effort | Status |
|---|---|---|---|---|
| P1.1 | Replace the synthesized starter corpus with ≥20 **real** recordings/language (240 total) incl. short answers, code-switching, varied speakers/accents/speeds, noise and natural pauses | current wavs are TTS-generated; absolute CER is optimistic and the brief's real-recordings requirement is unmet; n=3 makes p95 meaningless | 3–5 d (recording + native review) | planned |
| P1.2 | Full E2E streaming-vs-block A/B on the live server (EOU→first-audio, p50/p95, ≥20 turns/lang) | only the ASR stage is A/B-measured; the user-perceived number is E2E | 2 d | planned |
| P1.3 | CI: run `unittest discover tests` + the A/B accuracy gate on every change (after P0.1) | 45 tests exist but nothing runs them automatically (D5 remainder) | 1 d | partial (suite **done**, CI planned) |
| P1.4 | Tune post-miss suppression for fast languages | live smoke: pause-heavy hi turn finalized "full" at 353 ms vs block 203 ms — guards are conservative where the model is fast enough to re-speculate safely | 1–2 d | planned |
| P1.5 | Rapid-barge-in stress test to reproduce/verify D9 | `abort_active()` mitigation is code-inspection-verified only | 1 d | planned |

## P2 — correctness and robustness

| # | Item | Why | Effort | Status |
|---|---|---|---|---|
| P2.1 | Latin loanword handling for bn/as/pa/or/ta/te/kn/ml (D12) | "WhatsApp"/"OTP" vanish or mispronounce in 8 languages | 2 d | planned |
| P2.2 | Tiny-TTS mid-generation cancel (D10) | up to one clause of extra speech after barge-in | 1–2 d | planned |
| P2.3 | Dedicated executor / queue for outbound audio; load test ≥10 concurrent calls (D13) | sender and ASR share the default thread pool; concurrency behavior unmeasured | 2–3 d | planned |
| P2.4 | Noise/reverb/8 kHz-μ-law robustness eval set | phone audio is not clean 16 kHz; telephony path is functionally tested only | 2 d (+P1.1 corpus) | planned |
| P2.5 | MOS or validated naturalness proxy, ≥10 native listeners/language | humanizer/seam-blending implemented but unmeasured; no quality claim is currently defensible | 3–5 d | planned |
| P2.6 | Native Assamese ASR (or honest `as` labeling) | `as` rides the bn model; CER 0.268 is a mapping artifact (mapping unchanged per rules) | research | planned |
| P2.7 | Multi-turn stability test (20+ turns, language switching, holds) | watchdog/barge-in/switching untested over long calls | 1–2 d | planned |

## P3 — hygiene

- D17: prune `requirements.txt` (`num2words` unused; `indic-nlp-library` optional and
  absent — document the silent fallback or install it).
- D19: snapshot `agent.marks` into the turn dict so a late latency event cannot read
  the next turn's marks.
- D20: `AudioSink.is_speaking` is wall-clock estimated, not client-playback aware;
  network jitter skews the echo gate/barge-in window. Needs a client playback ack.
- D21: hi/mr and bn/as are script-indistinguishable; session default wins ties.
  Consider a spoken language probe or explicit caller selection.
- Observability (audit §5): structured per-turn logging with a turn ID (no audio, no
  transcripts by default) and a counters endpoint for strategies/errors/latency.
- Keep `docs/INDICVOICE_CHANGELOG.md` current with every measured change.

## P4 — aspirational latency (only after P1 measurement exists)

Target from the brief: 300–500 ms EOU→first-audio under favorable conditions.
Current measured reality (ASR stage only, clean utterances): streaming p50 is 0–530 ms
for 10 of 12 languages; en cloud ~440 ms; the E2E number adds LLM TTFT (~0.6–0.8 s
observed in smoke) + TTS TTFA (~0.1–0.3 s). **The 300–500 ms E2E target is not met and
cannot be claimed until P1.2 measures it.** Plausible levers, in order:

1. LLM: smaller/faster model or local inference for the first sentence; prompt caching;
   the keep-alive socket already removes connection setup.
2. TTS: first-clause synthesis is already streamed; pre-warm per-language voices at
   call start (warm-up exists for hi/en only).
3. ASR: already near-zero for fast languages via speculation; remaining cost is the
   slow models (kn/ml full decode 1–2 s) — GPU/ONNX threading tuning, not algorithm.
4. Endpoint: 0.26 s silence is itself a large chunk of the budget; adaptive endpoints
   risk cutting off slow speakers — only with P1.1 corpus evidence.

Each lever: measure baseline → one change → measure again, accuracy gate first.

## Deployment / rollback guide

See `docs/INDICVOICE_PRODUCTION_READINESS.md` §Deployment. Short version: the streaming
path has a runtime kill switch (`?streaming=0` per call, `--no-streaming` per server)
that restores the exact pre-engagement block behavior without a redeploy; model files
and language mappings were not modified, so rollback is code-only.