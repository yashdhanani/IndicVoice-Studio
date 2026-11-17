# Production V1 — baseline revalidation (Phase A)

Date: 2026-11-17 · Purpose: establish the actual state before Hardening V1 changes.
Status vocabulary per the brief: PASS (automated), PASS (manual), PARTIAL, FAIL,
NOT TESTED, NOT APPLICABLE.

## Checkpoints

| Commit | Contents |
|---|---|
| `5768a6d` | Stable baseline: pseudo-streaming ASR, audit fixes D1–D3/D7–D9/D11/D15–D16, 45-test suite, six phase-1/2 docs, raw A/B results |
| `c483f3d` | P0 hardening: fail-closed bind, Origin allowlist, inbound caps, per-IP limit; 56-test suite; corpus-honesty doc corrections |
| `8b9efc1` | Hardening V1 Phase B+D: ticket auth, dev-mode marking, abuse caps (utterance/session/queue), D22 XSS fix, 71-test suite; 240-slot dataset manifest + validator |
| `4a84be9` | Preserved earlier visual-QA work (`[hidden]` CSS fix, screenshot tool) |
| `b033dd3` | Phase F/H/I: E2E benchmark (2×40 live turns, both runs preserved), CI tiers, deployment guide, Phase C checklists |
| `79cf74d` | Phase G: concurrency matrix 1/2/3/5 (33/33 turns, RSS 732 MB peak); counterbalanced A/B order in evaluate |
| `74da488` | Phase E: TTS/noise/LLM benches, 2 counterbalanced A/B re-runs (parity 12/12 twice), D23 fix + regression test (72-test suite), final report A–L, readiness re-score 63/100 |

Git initialised this engagement (was D4: no version control). Repo-local identity
`IndicVoice Dev <dev@indicvoice.local>` (user-approved placeholder). No remote configured;
nothing pushed. `.env`, models, venvs, certs, recordings excluded via `.gitignore`.

## Runtime environment (measured)

| Item | Value |
|---|---|
| OS | Windows 11 Pro (10.0.26300), Git Bash shell |
| CPU | Intel Core i7-8565U @ 1.80 GHz — **4 cores / 8 threads, 15 W laptop chip** |
| RAM | 15.9 GB total, ~4.2 GB available at assessment time |
| Python | 3.13.18 (`.venv313`, uv-created; `.python/` cpython standalone) |
| sherpa-onnx | 2.0.1 |
| onnxruntime | 1.32.0 (CPU) |
| numpy / scipy | 2.5.5 / 1.18.1 |
| fastapi / uvicorn | 0.163.1 / 0.54.0 |
| aiohttp | 3.14.5 |
| PyYAML | 6.0.3 |
| absent | pytest, httpx (httpx2 present), jiwer, pandas, psutil, soundfile, indic-nlp-library |

The 4-core/8-thread 15 W CPU explains the large run-to-run decode variance observed
in phase 1 (kn block 892 ms vs 2386 ms across runs). All latency claims must carry
this hardware context; concurrency tests are capped at 5 sessions for safety.

## Revalidation results

| Check | Status | Evidence |
|---|---|---|
| All previous modifications present | PASS | `git show 5768a6d`; source inspection of streaming_stt.py, call_server.py, sts_pipeline.py |
| 45 baseline tests still passing | PASS | full suite `Ran 56 tests … OK` (128.9 s) — 45 baseline + 11 hardening, none deleted or weakened |
| Streaming/block CER/WER parity | PASS (on synthetic corpus) | `benchmarks/results/ab_full.json` — identical CER/WER all 12 langs; reproducible re-run pending (Phase E) |
| `?streaming=0` restores block decoding | PASS | `test_block_turn_end_to_end` (no `asr_mode`, no partials, transcript + audio) |
| `--no-streaming` server flag | PASS (code path) | maps to `create_app(streaming=False)`, same path as the tested query param; flag itself not separately booted |
| Final decode uses complete buffer | PASS | `test_speculative_finalize`, `test_quiet_resume_below_rms_gate_discards_stale_spec` (fake engine); live smoke transcripts identical |
| Stale speculative results discarded | PASS | staleness-guard unit test + kn_02 A/B regression history |
| 12 language routes functional | PARTIAL | `/health` reports all 12 voices ready + ASR present (live probe); hi exercised end-to-end in tests; other languages share the code path but only ASR-decode-tested via A/B, not WS-tested individually |
| Tests rely on insecure defaults? | PASS (reviewed) | WS tests run open-access on localhost (the documented dev mode); auth tests explicitly patch `ACCESS_TOKEN`; no test depends on a production token |
| Token auth 4401 / watchdog 4408 | PASS | `test_token_auth`, `test_idle_watchdog_closes_4408` |
| Fail-closed non-localhost startup | PASS | `test_main_refuses_insecure_bind` + `TestBindSecurity` (4 cases) |
| Origin / frame / per-IP gates | PASS | 6 new WS tests (4403, 1009 ×2, 1003, 4429 + slot release) |
| A/B measurements reproducible | NOT TESTED yet | Phase E counterbalanced re-run scheduled |
| Physical microphone / phone / carrier | NOT TESTED | requires human hardware access; checklists in Phase C report |

## Baseline benchmark references (unchanged, not overwritten)

- `benchmarks/results/ab_full.{json,md}` — 12-language A/B, 2026-11-17 (synthetic corpus)
- `benchmarks/results/ab_mr_gu.{json,md}` — isolated mr/gu re-validation
- `benchmarks/results/smoke_live_hi.md` — live-server smoke, both modes
- `eval/*.json` — phase-1 history (accuracy, latency, backend comparisons)

## Security configuration at baseline

- `INDICVOICE_TOKEN` empty → open access **on localhost only**; non-localhost bind
  without token refuses startup (fail closed, `c483f3d`).
- Origin allowlist: localhost always; extras via `INDICVOICE_ALLOWED_ORIGINS`.
- Inbound caps: 64 KB voice frame, 64 KB telephony text / 32 K-char payload,
  8 sessions/IP. TLS opt-in (`--tls`, self-signed via `src/tls_cert.py`).
- Token still rides the query string when used (B2 migration in progress).

## Differences from the previous completion report (corrections)

1. **Corpus is synthesized, not real.** `eval_data/*.wav` are TTS-generated starter
   clips (`--make-manifest`; `.gitignore` comment and `make_manifest` docstring confirm).
   The earlier "real recordings" wording was wrong and has been corrected in all docs.
   Parity and latency measurements remain valid *on that corpus*; absolute CER is
   optimistic; the brief's real-recordings requirement is unmet (Phase D).
2. Readiness score revised 61 → **60.5** after re-scoring accuracy (78→70) and
   evaluation rigor (55→45) for the synthetic corpus; security score will be re-scored
   after Phase B completes.
3. Test count is now 56, not 45 (11 hardening tests added; none removed).
4. mr "regression" in the full A/B run did not reproduce in isolation — documented as
   load noise, consistent with the 15 W CPU above.

## Known limitations carried into V1

- n=3/language synthetic corpus; no p90; no E2E benchmark; no MOS; no concurrency data.
- `as` uses the bn model (mapping preserved per rules); CER 0.268 is a mapping artifact.
- D9 barge-in socket race: mitigation code-inspection-verified only.
- D10 tiny-TTS mid-clause cancel, D12 Latin loanwords in 8 languages, D13 executor
  pressure, D19 marks race, D20 playback-clock estimate, D21 script-tie language choice.
- No CI yet; no remote repository.