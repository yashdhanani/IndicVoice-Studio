# IndicVoice evaluation framework

Status of every claim in this document: **measured** (real models, real decodes,
numbers in `benchmarks/results/`), **implemented** (code exists and runs), or
**planned** (not built yet). Nothing here is simulated. No MOS, WER-on-large-corpus,
or success-rate figures are claimed because none were measured.

**Corpus caveat (material)**: the current `eval_data/*.wav` clips are
**TTS-synthesized starter audio**, not human recordings. All published CER/WER and
latency numbers were measured on that corpus: the pipeline is real, but absolute
accuracy is optimistic versus real callers. The streaming-vs-block parity claim
holds regardless (same audio, both modes). Real recordings are the P1.1 gate.

## 1. What exists today (implemented + measured)

### 1.1 Accuracy + ASR-latency A/B harness — `src/evaluate.py`

```
python -m src.evaluate --manifest eval_data/manifest.json --mode ab --asr-only --out eval/ab_full.json
```

- **Input**: `eval_data/*.wav` (16 kHz mono, currently TTS-synthesized starter clips)
  with native-script reference texts in `eval_data/manifest.json`. Currently
  3 utterances × 12 languages. The harness consumes real recordings unchanged once
  they replace the wavs.
- **Block mode**: whole utterance → `STTEngine.transcribe` once; latency = decode time.
- **Streaming mode**: audio fed at real-time pace in 20 ms frames through
  `StreamingSTT`, exactly as the live server feeds it; feeding stops at
  speech-end + endpoint silence (the server never feeds past the endpoint — an earlier
  harness version did, which produced false staleness-guard triggers); latency is
  measured **from the simulated VAD endpoint** to the final transcript.
- **Metrics**: CER and WER (character/word error rate against the reference, computed
  in-harness — no jiwer dependency), ASR p50/p95, finalize strategy
  (speculative/full/cloud/empty), partial count.
- **Output**: JSON + Markdown report (`eval/ab_full.{json,md}`, copied to
  `benchmarks/results/`).
- **Acceptance gate used for the streaming work**: streaming CER/WER must equal block
  for *every* language (the final transcript is always a full-buffer decode), and no
  reproducible latency regression. Passed 2026-11-17; see `docs/INDICVOICE_CHANGELOG.md`.

### 1.2 Live-server smoke — `tools/smoke_streaming.py`

Streams one recording into a running `src.call_server` over WebSocket in both
modes and prints partials, final transcript, strategy, and the server's own latency
event (`asr_ms`, `llm_ms`, `tts_ms`, `first_audio_ms`). Verified 2026-11-17 on hi
(`benchmarks/results/smoke_live_hi.md`). This is a functional check, not a benchmark.

### 1.3 Automated tests — `tests/` (45 tests, stdlib unittest)

```
PYTHONIOENCODING=utf-8 .venv313/Scripts/python.exe -m unittest discover tests -v
```

- `test_codecs.py` — PCM16/μ-law round-trips, resampling, framing.
- `test_text.py` — normalizer (currency/dates/phones/OTP/markdown), sentence splitter,
  hallucination filter (incl. the D7 "एक" regression), silence trimming.
- `test_streaming_stt.py` — fake-engine state machine: speculation, loud-resume
  invalidation, quiet-resume staleness guard, post-miss suppression, cost gating,
  cancel/restart. Trailing silence is fed at real-time pace (fast-feeding starves the
  decode worker and is not a server-realistic scenario).
- `test_ws_server.py` — real uvicorn in a thread, real local hi ASR + tiny TTS, stub
  LLM (no cloud): streaming and block turns end-to-end, token auth 4401, ASR-error
  survival (D1), telephony μ-law 20 ms framing, idle watchdog 4408.

## 2. Known gaps (planned — not built)

| Gap | Why it matters | Priority |
|---|---|---|
| Corpus is **synthesized TTS audio**, not human recordings | absolute CER/WER are optimistic; no accent/noise/speed variation; the brief's "real recordings primary" requirement is unmet | P1 (top) |
| Corpus is 3 utterances/language, not ≥20 | p50/p95 on n=3 is noisy; single-run deltas <20% are not trustworthy (mr regression appeared in one run, vanished in the isolated re-run) | P1 |
| No full E2E (ASR+LLM+TTS) streaming-vs-block A/B on the live server | single-session E2E percentiles now measured (`benchmarks/run_e2e_latency.py`, streaming mode); a matched block-mode E2E A/B is still outstanding | P1 |
| No MOS / naturalness measurement | voice-quality work (humanizer, seam blending) is implemented but unmeasured; protocol below, ≥10 native listeners per language rating 1–5 | P2 |
| No noise/reverb/codec robustness set | labeled synthetic-noise matrix tool exists (`benchmarks/run_noise_matrix.py`); real babble/reverb and 8 kHz μ-law accuracy deltas still unmeasured | P2 |
| CI authored, not executed on GitHub | `.github/workflows/ci.yml` fast+model tiers exist; no remote configured, so cloud execution is NOT TESTED (see `INDICVOICE_CI_GUIDE.md`) | P1 |
| No long-call / multi-turn stability test | watchdog, barge-in, language switching over 20+ turns untested | P2 |
| `as` evaluated against the bn-model workaround | CER 0.268 is a mapping artifact; needs native Assamese references + ideally a real as model | P2 |

## 3. Protocol for future measurements (the rules used this pass)

1. Measure baseline first, change one thing, measure again on the same corpus.
2. Real-time-pace feeding; endpoint semantics identical to the server.
3. Accuracy gate before latency claims: any CER/WER regression rejects the change,
   regardless of latency wins.
4. Report n, p50 and p95; treat deltas within run-to-run noise as unproven.
5. Distinguish *implemented / tested / measured / manually verified* in every claim.
6. Never fabricate WER, CER, MOS, latency or success-rate figures; never mark an
   untested feature PASS.

## 4. Target corpus design (P1, planned)

- ≥20 utterances/language: 10 read sentences (numbers, dates, addresses, code-switched
  Hindi-English), 5 spontaneous-style prompts, 5 short answers ("हाँ", "एक", "नहीं")
  that specifically exercise the hallucination-filter and endpoint edge cases.
- Record at 16 kHz for the accuracy set; duplicate 5/language through the telephony
  path (8 kHz μ-law) for codec-robustness deltas.
- References double-checked by a native reader; store in `eval_data/manifest.json`
  format so the existing harness consumes them unchanged.
- Re-run the A/B gate on every change to `streaming_stt.py`, VAD, or endpoint config.

## 5. Human MOS protocol (workflow only — NOT conducted, no scores exist)

Naturalness claims require real listeners. Until this study is run, every
naturalness statement must say "implemented, unmeasured".

1. **Stimuli**: per language, 10 replies rendered by the current pipeline
   (humanizer on) and the same 10 with humanizer off, plus 2 anchor clips
   (a professional recording as high anchor, a robotic TTS as low anchor).
   Render offline at the voice's native rate; normalize loudness.
2. **Listeners**: ≥10 native speakers per language, normal hearing,
   recruited with consent; no affiliation with the project.
3. **Procedure**: randomized order, blind to condition; each clip rated
   1–5 (bad–excellent) for naturalness only; one sitting ≤20 minutes;
   headphones in a quiet room; repeat 10% of clips to check intra-rater
   consistency (drop raters with <0.7 correlation).
4. **Reporting**: mean MOS ± 95% CI per language per condition, n listeners,
   n ratings, dropout count. A condition difference is claimed only if the
   CIs do not overlap.
5. **Storage**: raw ratings CSV + consent records under `evaluation/mos/`
   (git-ignored if it contains listener identifiers); results summarized in
   the final report with the exact protocol version.

Fabricating MOS numbers, substituting TTS-vs-TTS "listening" by the
developer, or reporting a proxy metric as MOS are all prohibited.