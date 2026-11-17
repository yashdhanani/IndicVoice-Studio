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
| Test suite: 39 unit tests + 6 WebSocket integration tests (stdlib `unittest`, real local hi ASR/TTS, stub LLM — no cloud calls in tests) | `tests/` | all passing |
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

## Measured: block vs streaming A/B (ASR-only, real recordings)

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

- **Eval corpus is 3 utterances/language (36 total)**, not the ≥20/language the brief
  targets. Numbers above are real but statistically thin; expanding the corpus is P1
  in the roadmap. No MOS/naturalness scores exist — nothing of the sort was measured.
- Latency numbers are ASR-stage only (`--asr-only`). Full E2E (LLM+TTS) streaming-vs-block
  A/B on the live server is not yet measured; the smoke test shows the pipeline works but
  is a single turn, not a benchmark.
- `as` uses the `bn` model (pre-existing mapping, unchanged); its CER 0.268 reflects that
  workaround, not a streaming regression.
- Tests cover hi locally; other languages' WS paths share the same code but were not
  individually integration-tested.
- D9 fix is code-inspection-verified only; the socket race is not deterministically reproducible.