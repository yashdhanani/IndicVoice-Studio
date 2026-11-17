# IndicVoice — E2E Latency Report V1 (Production Hardening V1, Phase F)

Date: 2026-11-17 · Harness: `benchmarks/run_e2e_latency.py`
Raw data: `benchmarks/results/production_v1/e2e_v1.json` (run 2, canonical),
`e2e_v1_run1.json` (run 1), `e2e_smoke.json` (1-turn harness check).

## What is measured (definitions, no double-counting)

- **`e2e_client_ms`** — client clock: last speech frame sent → first reply
  audio byte received. This is the caller-perceived wait after they stop
  talking. It **includes** the endpoint-silence wait (0.26 s hi-family,
  0.45 s en) and localhost transport.
- **`first_audio_ms`** — server clock: VAD end-of-speech → first audio
  emitted. `e2e_client_ms ≈ endpoint_silence + first_audio_ms + transport`;
  the ~300–450 ms offset between the two columns is exactly that, not loss.
- **`asr_ms` / `llm_ms` / `tts_ms`** — server-reported stage timings.
  These stages **overlap** (LLM socket warmed during speech; TTS starts on
  the first sentence; speculative ASR runs during endpoint silence). They
  are reported separately and **never summed** into an E2E figure.
- ASR-stage latency ≠ E2E latency. The earlier A/B tables measured ASR
  only; this report measures the full chain on a live server.

## Setup

- Real pipeline, no stubs: local Indic ASR (hi), Groq cloud ASR (en),
  Groq LLM (`openai/gpt-oss-20b`, reasoning effort low), Indic Tiny TTS.
- Server started by the harness on 127.0.0.1:8010, `--warm hi en`,
  streaming on, backchannel off, one fresh WebSocket per turn, turns
  strictly sequential (controlled single-session load).
- Audio: `eval_data/{hi,en}_0{1..3}.wav` cycled, fed at real-time pace
  (20 ms frames) + 1 s trailing silence. **Corpus caveat: TTS-synthesized
  starter clips, not real recordings.**
- Machine: i7-8565U (4C/8T, 15 W), 16 GB RAM, Windows 11, Python 3.13.
- n = 20 turns/language/run; two independent runs ~15 minutes apart.

## Results — client-perceived E2E (ms)

| Lang | Run | n | min | p50 | p90 | p95 | max | failed |
|---|---|---|---|---|---|---|---|---|
| hi | 1 | 20 | 752.9 | 1882.8 | 4300.1 | 7052.8 | 7052.8 | 0 |
| hi | 2 | 20 | 802.4 | 1130.1 | 1937.2 | 2766.2 | 2766.2 | 0 |
| en | 1 | 20 | 879.7 | 1195.8 | 1351.5 | 1416.4 | 1416.4 | 0 |
| en | 2 | 20 | 929.8 | 1264.2 | 1589.8 | 2886.6 | 2886.6 | 0 |

Both runs: 40/40 turns OK (transcript + audio + no error events).

Server-side `first_audio_ms` p50: hi 1544 (run 1) / 806 (run 2);
en 1041 / 1084. Stage p50s (run 2): hi asr 0.9, llm 512, tts 214;
en asr 467, llm 943, tts 115.

## Analysis (honest)

1. **The brief's 300–500 ms E2E target is NOT met.** Best-case hi turns
   reach ~750 ms client-side; p50 is 1.1–1.9 s. The floor is structural:
   endpoint silence (260–450 ms) + LLM first token (280–950 ms) + TTS first
   sentence (85–215 ms). Sub-500 ms E2E would require native streaming ASR
   with earlier endpointing and a faster/local LLM — roadmap P4, not a tuning
   flag.
2. **Speculation coverage drives hi variance.** Run 1: 10/20 turns
   speculative (p50 asr 163 ms) vs 10 full (p50 asr 1435 ms). Run 2: 14/20
   speculative → asr p50 0.9 ms. Pause-heavy digit utterances (hi_01,
   hi_03) trigger post-miss suppression and fall back to full decode —
   accuracy-safe by design, but the latency tail. hi_02 was speculative in
   7/7 appearances across runs.
3. **Run-to-run variance is large on this 15 W laptop** (hi p95 7053 →
   2766 between runs; consistent with the 2.7× decode variance documented
   in the baseline). Single-run percentiles must not be quoted as stable
   capacity numbers; both runs are preserved.
4. **en is stable** (cloud ASR ~400–530 ms every turn); its tail is LLM
   first-token jitter (groq free-tier queueing: llm p95 1090 run 1,
   2514 run 2).
5. **Memory**: server working set peaked at **845 MB** (hi+en warmed,
   run 2, 2 s sampling of the actual interpreter child process). Run 1's
   sampler measured the venv launcher (5.9 MB) — a harness defect, fixed
   before run 2; run-1 latency data is unaffected.

## Status

| Item | Status |
|---|---|
| Harness + 2×40 live turns, all stages real | PASS (automated measurement) |
| hi/en E2E percentiles under controlled single-session load | PASS |
| Other 10 languages E2E | NOT TESTED (ASR-stage A/B exists for all 12) |
| Block-mode E2E for a matched A/B | NOT TESTED (P1.2 remainder) |
| Real-mic / phone-network E2E | NOT TESTED (Phase C checklists) |
| Concurrent-load E2E | see `INDICVOICE_CONCURRENCY_REPORT.md` |

## Reproduce

```bash
.venv313/Scripts/python.exe benchmarks/run_e2e_latency.py --langs hi en --turns 20
```

The harness refuses occupied ports, samples the server's real working set,
and kills only its own process tree. Never overwrite prior results: write
new runs to new `--out` paths.