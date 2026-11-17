# IndicVoice changelog

Date: 2026-11-17 · Runtime: `.venv313` (Python 3.13, sherpa-onnx 2.0.1, onnxruntime 1.32.0)
All numbers below are measured on this machine (Windows, CPU-only) with
`PYTHONIOENCODING=utf-8`. Nothing is estimated or simulated. Raw reports:
[benchmarks/results/](../benchmarks/results/).

## Added

| Item | Where | Status |
|---|---|---|
| Pseudo-streaming ASR wrapper (partials + speculative authoritative decode) | `src/streaming_stt.py` | implemented, unit-tested, A/B-measured |
| Streaming integration in the call server (ring-buffer seed, partial events, `?streaming=0` / `--no-streaming` kill switch) | `src/call_server.py` | implemented, WS-integration-tested, live-smoke-tested |
| Real block-vs-streaming A/B evaluation (`--mode ab --asr-only`), real-time-pace feeding with server-matching endpoint semantics | `src/evaluate.py` | implemented, used for all numbers below |
| Live-server smoke client (same recording, both modes) | `tools/smoke_streaming.py` | implemented, run successfully |
| Test suite: 72 tests (unit + state-machine + WebSocket integration + security + static XSS + A/B sub-manifest regression; stdlib `unittest`, real local hi ASR/TTS, stub LLM — no cloud calls in tests) | `tests/` | all passing |
| Codebase inventory | `docs/INDICVOICE_CODEBASE_INVENTORY.md` | complete |
| Technical audit with defect register D1–D21 | `docs/INDICVOICE_TECHNICAL_AUDIT.md` | complete |

## Fixed (audit defect IDs)

| ID | Defect | Fix | Verified by |
|---|---|---|---|
| D1 | Unhandled ASR exception dropped the whole call | try/except around both ASR paths in `_process_frame`; emits `{"type":"error","stage":"asr"}` and keeps the socket | `test_asr_error_does_not_drop_call` (error event, then next turn works) |
| D2 | XSS in fallback call page (`innerHTML` with transcript text) | `createElement` + `textContent` | code inspection; main `web/app.js` already used `textContent` everywhere |
| D3 | Non-constant-time token comparison | `hmac.compare_digest` | `test_token_auth` (4401 without token, accepted with token) |
| D7 | `"एक"` (= "one") in Whisper hallucination filter dropped legitimate numeric answers | removed from `_HALLUCINATIONS`; comment explains why single common words must not be listed | `test_single_word_answer_preserved` |
| D8 | Idle watchdog only bumped on inbound frames; long outbound-only stretches could be killed | `last_activity` bumped in `_emit_audio` too | code inspection + `test_idle_watchdog_closes_4408` (still fires when truly idle) |
| D9 | Barge-in could race a draining LLM SSE socket | `LLMClient.abort_active()` closes keep-alive connections when the response worker outlives its join timeout | code inspection (race not reproducible deterministically in tests) |
| D11 | `/health` and `TTSPool.langs` assumed MMS model paths for every language | backend-aware readiness (`tiny_available` / `supertonic_available` / MMS path) | live `/health` shows correct per-language backends |
| D15 | `ENDPOINT_SILENCE` comment described the old 0.45 s value | comment corrected to 0.26 s (en 0.45 s) | — |
| D16 | Module docstring claimed 0.3 s barge-in | corrected to 0.45 s default | — |

Deferred to the roadmap (not fixed this pass): D4 (no version control), D5/D6 (eval corpus
size, no CI), D10 (tiny-TTS cancel_event ignored mid-sentence), D12–D14 (observability
gaps), D17–D21 (hardening items). See `docs/INDICVOICE_TECHNICAL_AUDIT.md`.

## Production Hardening V1 (2026-11-17, commits 5768a6d → c483f3d → 8b9efc1)

| Phase | Item | Status |
|---|---|---|
| A | Baseline preserved in git; revalidation + environment characterization | `docs/PRODUCTION_V1_BASELINE.md` |
| B1 | Fail-closed non-localhost bind; visible dev mode (startup banner + `/health` `auth` field); empty/invalid token rejected | PASS (automated) |
| B2 | One-time short-lived `?ticket=` via `POST /auth/ticket` (Authorization header); legacy `?token=` preserved; migration documented | PASS (automated); client migration NOT TESTED |
| B3 | **D22 fixed**: `/health`-derived `v.backend` string rendered via `innerHTML` in `web/app.js` → `textContent`; static XSS regression tests pin all sinks | PASS (automated) |
| B4 | Env-driven Origin allowlist (`INDICVOICE_ALLOWED_ORIGINS`), 4403 on foreign origins | PASS (automated) |
| B5 | Abuse caps: 64 KiB frames, 32 Ki-char telephony payloads, 8 sessions/IP, 60 s utterance cap (truncation + warning; `StreamingSTT(max_buffer=…)`), 1800 s session cap (4410), 4096-item bounded outbound queue (slow-drain close) | PASS (automated; >60 s live utterance NOT TESTED) |
| B6 | Idle watchdog 4408 + max-duration watchdog 4410; IP slot always released | PASS (automated) |
| B7 | Security regression suite; full suite 71/71 (was 56; none weakened) | PASS |
| D | 240-slot real-recording manifest (12 langs × 20, all NOT_COLLECTED), schema validator (self-tested 6/6), consent/recording guide | tooling PASS; dataset 0/240 NOT COLLECTED |
| H | GitHub Actions fast tier (model-free, cloud-free) + manual model tier; model-absent tests skip explicitly | authored; execution on GitHub NOT TESTED (no remote) |
| E | TTS RTF/first-audio bench (12 langs), noise matrix (hi/gu/kn), LLM script check (12 langs), counterbalanced A/B re-run | measured — see Phase E section below |
| F | E2E latency benchmark, 2 runs × 40 live turns (hi/en), RSS-corrected | `docs/INDICVOICE_E2E_LATENCY_REPORT.md`; 300–500 ms target NOT met |
| G | Concurrency matrix 1/2/3/5 sessions, 33/33 turns OK | `docs/INDICVOICE_CONCURRENCY_REPORT.md`; level 10 excluded by design |
| I | Single-worker deployment guide, LAN + TLS-proxy topologies, 3-level rollback | `docs/INDICVOICE_DEPLOYMENT_V1.md`; physical deployment NOT TESTED |
| J | **D23 fixed**: A/B sub-manifest audio paths broke when `--out` was outside the corpus dir; regression test added | PASS (automated) |

Details: `docs/INDICVOICE_SECURITY_HARDENING.md`, `docs/INDICVOICE_CI_GUIDE.md`,
`evaluation/dataset/README.md`.

## Production Hardening V1 — Phase E measurements (2026-11-17)

All raw outputs in `benchmarks/results/production_v1/`. Corpus caveat as below:
starter clips are TTS-synthesized, not human recordings.

### TTS synthesis speed (`tts_v1.json`, n=6/language, warm model excluded)

All 12 languages use the Indic Tiny backend. RTF = synthesis wall time / audio
duration (lower is faster; <1 means faster than real-time). First-sentence
render = time to produce the first sentence's audio, the number that matters
for first-audio latency.

| lang | RTF p50 | RTF max | first-sentence render p50 ms |
|---|---|---|---|
| hi | 0.110 | 0.140 | 215.7 |
| gu | 0.140 | 0.184 | 307.1 |
| mr | 0.193 | 0.275 | 574.2 |
| bn | 0.182 | 0.243 | 369.8 |
| ta | 0.139 | 0.145 | 289.1 |
| te | 0.169 | 0.196 | 453.3 |
| kn | 0.200 | 0.244 | 495.1 |
| ml | 0.194 | 0.210 | 345.5 |
| pa | 0.118 | 0.156 | 331.4 |
| or | 0.133 | 0.167 | 320.3 |
| as | 0.136 | 0.165 | 276.8 |
| en | 0.148 | 0.201 | 313.4 |

Every voice synthesizes 5–9× faster than real-time on the reference laptop.
**Naturalness is NOT measured** — no MOS or listener study exists; these are
speed numbers only.

### Noise robustness (`noise_matrix_v1.json`, hi/gu/kn, block decode)

Synthetic low-pass-shaped noise at SNR 20/10/5 dB on the synthesized clips.
Relative degradation only — **not** real-world acoustic validation.

| lang | mean CER clean | snr20 | snr10 | snr5 |
|---|---|---|---|---|
| hi | 0.047 | 0.065 | 0.047 | 0.047 |
| gu | 0.025 | 0.025 | 0.012 | 0.037 |
| kn | 0.012 | 0.000 | 0.000 | 0.000 |

Degradation is small and non-monotonic at n=3 — the clean clips are already
easy; this matrix cannot certify noisy-call behavior. Real noise recordings
are part of the Phase D corpus (slots 15–20 per language).

### LLM native-script consistency (`llm_script_check_v1.json`, Groq gpt-oss-20b)

12/12 languages replied fully in the expected script (letter fraction 1.00,
threshold 0.6; replies 279–716 ms). This is a script spot check, **not** a
quality eval: one mr reply was factually wrong ("capital = Mumbai") while
script-perfect — content quality needs the human eval protocol
(`INDICVOICE_EVALUATION_FRAMEWORK.md` §5), which has no scores yet.

### Counterbalanced A/B re-runs (`ab_v1.json`, `ab_v1_run2.json`)

Protocol: corpus split in half; group A block→streaming, group B
streaming→block (order groups tagged per row; sub-manifests preserved).
Two executions on 2026-11-17, the second after a machine cooldown.

- **Accuracy parity reproduced exactly in both re-runs**: 12/12 languages,
  CER/WER identical between modes and identical to the original full run.
- Re-run 1 showed inflated latencies in *both* modes (block p50 up to 2.4×
  the original) and streaming worse than block in 7/12 languages despite
  33/33 speculative hits — regressions appeared in both order groups.
- Re-run 2 (cooldown): block p50 back to baseline (kn 2040→916 ms,
  pa 1859→714 ms); streaming penalties shrank to ≤225 ms; streaming p50 ≤
  block in 6/12 languages, hi near-zero in every run (0–23 ms).
- **Conclusion**: the accuracy guarantee is robust; the latency benefit is
  real but load-dependent on the 15 W reference laptop. Capacity planning
  must assume block-equivalent worst-case decode times. Full analysis:
  `PRODUCTION_V1_FINAL_REPORT.md` §E + addendum.
- Executing the re-run exposed **D23** (sub-manifest audio paths resolved
  against the wrong directory when `--out` is outside the corpus dir) —
  fixed, regression-tested (`tests/test_evaluate_ab.py`).

## Measured: block vs streaming A/B (ASR-only, synthesized starter corpus)

**Corpus caveat**: `eval_data/*.wav` are TTS-synthesized starter clips (generated by
`--make-manifest`), not human recordings. The measurements below are real — real
models, real decodes, real-time feeding — but absolute CER values are optimistic
versus real callers, and the latency numbers reflect clean, canonical-pronunciation
audio. The streaming-vs-block *parity* claim is unaffected: both modes decode the
same audio. Replacing the corpus with ≥20 real recordings/language is P1.1.

`python -m src.evaluate --manifest eval_data/manifest.json --mode ab --asr-only`
n = 3 utterances/language, real-time-pace feeding, ASR latency measured from the
simulated VAD endpoint (same semantics as the live server). Full run 2026-11-17,
raw: `benchmarks/results/ab_full.{json,md}`.

**Accuracy gate: CER and WER are identical for every language in both modes** —
the final transcript always comes from a full-buffer decode, by construction.

| lang | CER (both modes) | block ASR p50 ms | streaming ASR p50 ms | delta |
|---|---|---|---|---|
| hi | 0.047 | 80 | 0 | −80 |
| gu | 0.025 | 681 | 672 | −9 |
| mr | 0.000 | 875 | 1052 * | +177 * |
| bn | 0.044 | 577 | 393 | −184 |
| ta | 0.000 | 621 | 395 | −226 |
| te | 0.000 | 830 | 396 | −434 |
| kn | 0.012 | 2386 | 528 | −1858 |
| ml | 0.029 | 1445 | 770 | −675 |
| pa | 0.042 | 775 | 517 | −258 |
| or | 0.088 | 902 | 447 | −455 |
| as | 0.268 | 814 | 406 | −408 |
| en | 0.141 | 413 | 438 | +25 (cloud path, unchanged) |

\* mr did not reproduce: an isolated mr+gu re-run the same day
(`benchmarks/results/ab_mr_gu.{json,md}`) measured mr block 819 → streaming 730 ms p50
(all 3 cases improved) and gu 662 → 628 ms p50. The full-run mr regression is attributed
to machine load — the block baseline itself varied up to 2.7× between runs
(kn block 892 ms in one run, 2386 ms in another). Treat single-run deltas under ~20%
as noise; the large improvements (kn, ml, te, or, as, bn, ta, pa, hi) are far outside it.

### How the result was reached (measure → one change → measure)

1. **Merge-based streaming** (partials merged with tail decode): abandoned — corrupted
   transcripts, kn CER 0.01 → 0.32. Violates the accuracy-first rule.
2. **Speculative full decode, ungated partials**: accuracy parity, but mr/kn/ta p50
   roughly doubled — slow-model partials held the engine lock at speech offset.
3. **Predicted-cost partial gating** (`partial_max_decode=0.4`, cost scaled by buffer
   length): most languages improved; a quiet-speech resume in kn_02 slipped under the
   RMS silence gate and a stale speculative result became the final transcript
   (CER 0.036 → 0.214). Unacceptable.
4. **Staleness guard + post-miss suppression**: accuracy parity restored everywhere;
   ta/te/kn/or/as/pa/bn then fell back to the conservative "full" strategy at ~2× latency.
   Root cause was the *eval harness*, not the wrapper: it fed the recordings' natural
   trailing silence past the simulated endpoint (the live server never does), so the
   guard correctly saw unexpected buffer growth.
5. **Eval endpoint semantics fixed** (`feed_end` stops at speech-end + endpoint):
   final run above. Acceptance gate passed: identical CER/WER for all 12 languages,
   no reproducible latency regression.

### Live-server smoke (hi_01.wav, both modes, real LLM/TTS)

Raw: `benchmarks/results/smoke_live_hi.md`. Final transcripts identical; live partials
observed during speech; audio returned in both modes. This recording has a mid-utterance
pause, so the safety mechanisms engaged and streaming finalized via the conservative
"full" strategy (asr 353.6 ms vs block 202.8 ms on that turn). On pause-heavy utterances
the guards trade latency for accuracy — documented limitation, tuning is a roadmap item.

## Known limitations (honest state)

- **Eval corpus is 3 synthesized utterances/language (36 total)**, not the ≥20 real
  human recordings/language the brief targets. Numbers above are real measurements
  on TTS-generated starter audio — statistically thin and optimistic in absolute
  terms; replacing and expanding the corpus is P1.1 in the roadmap. No MOS/naturalness
  scores exist — nothing of the sort was measured.
- Latency numbers are ASR-stage only (`--asr-only`). Full E2E (LLM+TTS) streaming-vs-block
  A/B on the live server is not yet measured; the smoke test shows the pipeline works but
  is a single turn, not a benchmark.
- `as` uses the `bn` model (pre-existing mapping, unchanged); its CER 0.268 reflects that
  workaround, not a streaming regression.
- Tests cover hi locally; other languages' WS paths share the same code but were not
  individually integration-tested.
- D9 fix is code-inspection-verified only; the socket race is not deterministically reproducible.