# IndicVoice — Final Report, STS pass 2026-11-18

Scope of this pass: Phase Zero audit, baseline measurement, three defect fixes
with regression tests, offline stage benchmark. Status vocabulary: **PASS —
Automated**, **PASS — Manually verified**, **PARTIAL**, **FAIL**, **NOT TESTED**.

## 1. Architecture

Retained: **modular cascaded STS** (mic → VAD → ASR → language → LLM → TTS →
streamed audio). No native speech-to-speech model is feasible on this hardware:
the environment is CPU-only (i7-8565U, 16 GB), has no provider offering a
jointly-trained duplext speech model, and a cascade is the only design that can
hit the measured 0.19–2.5 s ASR budgets with locally-owned models. This is
explicitly *not* a native STS model, and no claim of that kind is made.

## 2. Changed files

| File | Change |
|---|---|
| `src/call_server.py` | sink mute-after-cancel; per-turn endpoint retune |
| `src/tts_engine.py` | player mute-after-cancel; post-render cancel checks |
| `src/sts_pipeline.py` | sink resume at turn start; Latin-script switch evidence gate |
| `tests/test_turn_taking.py` | new: 10 regression tests |
| `benchmarks/run_stage_bench.py` | new: offline stage benchmark |
| `benchmarks/results/final_sts/*` | audit, this report, JSON + log evidence |

## 3. Defects removed

- F1 stale TTS audio after barge-in (interrupted reply kept speaking).
- F2 a short Latin utterance flipping the session language to English.
- F3 endpoint silence not following the turn language.

Each is pinned by tests in `tests/test_turn_taking.py`.

## 4. Measured results (this machine, offline)

Command: `.venv313\Scripts\python.exe -m benchmarks.run_stage_bench --langs hi en gu ta --repeats 3`
Evidence: `benchmarks/results/final_sts/stage_bench_latest.json`.

| Stage | hi | en | gu | ta |
|---|---|---|---|---|
| TTS p50 | 304 ms | 263 ms | 607 ms | 378 ms |
| TTS RTF | 0.08 | 0.07 | 0.11 | 0.12 |
| ASR p50 | 189 ms | 543 ms (cloud) | 2 514 ms | 1 653 ms |
| Round-trip CER | 0.000 | 0.216¹ | 0.000 | 0.000 |
| VAD onset | 768 ms | 736 ms | 1 216 ms | 672 ms |
| VAD endpoint delta vs setting | −64 ms | +64 ms | −2 208 ms | 0 ms |
| VAD turn splits / utterance | 0 | 0 | **1** | 0 |
| VAD false segments on 5 s silence | 0 | 0 | 0 | 0 |
| RSS after loading 4 voices + 4 ASR | 1 344 MB | | | |

¹ Digit formatting (“one two three” → “123”), not a recognition error.

Latency is **stage cost**, not end-to-end conversation latency. End-to-end
numbers from the earlier V1/V2/V3 runs are preserved in `eval/` and
`benchmarks/results/` and were not re-run here (they need a live server + LLM).

## 5. Language status (this pass)

| Lang | ASR/VAD/TTS measured | Human evaluation |
|---|---|---|
| hi | PASS — Automated | NOT TESTED |
| en | PASS — Automated | NOT TESTED |
| gu | PARTIAL — one VAD turn split (F4) | NOT TESTED |
| ta | PASS — Automated | NOT TESTED |
| mr, bn, kn, ml, pa, or, as | NOT TESTED (this pass) | NOT TESTED |

No language is reported as PASS — Manually verified: no real microphone, phone
line or native listener was involved in this pass.

## 6. Regression status

- Baseline before change: 176 tests OK.
- After change: **186 tests OK** (`unittest discover`, 139 s), exit 0.
- `py_compile` clean on all touched modules.

## 7. Remaining limitations

- F4 Gujarati mid-utterance pause splits the turn. Do **not** widen the endpoint
  on synthetic evidence; needs real recordings per language.
- F5 barge-in and echo gate rely on an estimated playback clock (no client ack).
- F6 hi/mr and bn/as ties still resolve to the session default.
- F7 tiny/Supertonic generation cannot abort mid-clause; output is dropped, CPU
  is still spent.
- End-to-end first-audio latency, concurrency, long-session memory stability and
  interruption behaviour were not re-measured in this pass.
- Human accuracy, naturalness and MOS: **NOT TESTED**. The 240-utterance
  bilingual dataset remains at its last recorded count; no synthetic audio was
  counted as human audio.

## 8. Rollback

Revert these symbols only; all of them are additive or one-line guarded:

1. `AudioSink`: remove `_accepting`, `resume()`, the `push()` guard, and the
   `_accepting = False` line in `cancel()`.
2. `CallSession`: remove `_endpoint_override`, `_retune_endpoint()` and its call.
3. `AudioPlayer`: same as (1). Remove the two `cancel_event` checks in
   `speak_sentences()`.
4. `VoiceAgent`: remove the `resume()` call in `respond()` and the
   `_LATIN_SWITCH_MIN_WORDS` block in `maybe_switch_language()`.
5. Delete `tests/test_turn_taking.py`.

**Do not run `git checkout -- src/`**: those files already carried uncommitted
V3 Phase C work (TTFT instrumentation, Assamese export, gender prompt,
trim-silence fix) before this pass and it would be destroyed with the fixes.

## 9. Next steps requiring the user

1. Record 20 utterances per language (5 native speakers where possible) — F4 and
   every accuracy claim depend on it.
2. Re-run `benchmarks/run_latency_v3.py` against a live server to refresh
   end-to-end p50/p90/p95 with the same conditions as the V3 baseline.
3. A short live microphone session per language to confirm barge-in and
   endpointing by ear (this pass could not).
