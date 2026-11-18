# CPU Profile (baseline, no new optimization this pass)

## Hardware

Intel Core i7-8565U, 4 cores/8 threads, 15.88 GB RAM, Windows 11, CPU-only. Python 3.13. venv `.venv313`. AVX2, no VNNI (per Intel spec).

## Current configuration (from config.py)

- STT_NUM_THREADS: default max(2, min(4, cpu_count)) = 4 (override INDICVOICE_STT_THREADS).
- TTS_NUM_THREADS: default 2 (override INDICVOICE_TTS_THREADS).
- ASR_WORKERS: default 2 (dedicated pool).
- ASR: IndicConformer INT8 via sherpa-onnx (STT_NUM_THREADS).
- TTS: tiny (onnxruntime, TTS_NUM_THREADS), supertonic, MMS.
- VAD: Silero, 1 thread.
- LLM: Groq cloud (no local CPU).
- Sender: event-driven (V3 Phase B), bounded queue 4096.

## Measured

- Stage-bench process RSS end: 1344.4 MB (all models loaded).
- E2E server working set peak: 845 MB (run2, hi+en warmed).
- Concurrency matrix: 1/2/3/5 sessions, 33/33 turns OK, RSS stable 732.5 MB peak; recommended ≤2–3 concurrent calls.
- TTS RTF: 0.07–0.12 (tiny) — well below 1.0, CPU-stable.
- ASR decode: 192.8–1876.8 ms p50 depending on language.

## Not measured (this pass)

- Per-stage CPU% (audio capture, preprocessing, VAD, ASR, LLM, TTS, encoding, playback, background).
- Idle CPU.
- CPU during speaking vs TTS generation.
- Thread contention analysis.
- INT8 vs FP32 comparison (no FP32 baseline run).
- Thread sweep 1/2/3/4 (not run).

## Optimization guidance (from research, not yet applied)

- Sweep intra-op threads 1/2/3/4 on this CPU; keep inter-op sequential for single stream.
- Benchmark FP32 vs INT8 on representative audio; compare WER/CER + latency.
- Warm up sessions; reuse sessions; bounded queues with backpressure.
- Avoid creating/destroying sessions per utterance.
- Do not change global thread settings without understanding which runtime they affect.

## Thread sweep (measured, 2026-11-18)

Script: `benchmarks/run_thread_sweep.py` (5 repeats, hi local IndicConformer + tiny TTS; en partial due to Groq RPM 429).
Raw: `runs/thread_sweep_20261118-113507.json`.

hi (local, no network) — median ms:

| STT threads | TTS threads | ASR decode ms | TTS render ms | RSS MB |
|---|---|---|---|---|
| 1 | 1 | 302.5 | 297.3 | 521.9 |
| 1 | 2 | 311.5 | 193.1 | 897.7 |
| 1 | 4 | 331.2 | 204.7 | 1249.7 |
| 2 | 1 | 327.5 | 311.3 | 1287.4 |
| 2 | 2 | 238.7 | 250.5 | 1640.0 |
| 2 | 4 | 277.0 | 248.0 | 1990.3 |
| 3 | 1 | 281.3 | 380.3 | 1973.6 |
| 3 | 2 | 279.1 | 311.9 | 2323.9 |
| 3 | 4 | 246.4 | 313.3 | 2694.3 |
| 4 | 1 | 176.8 | 418.3 | 1295.0 |
| 4 | 2 | 193.9 | 271.9 | 1641.6 |
| 4 | 4 | 286.6 | 464.7 | 2004.1 |

Findings:
- Best ASR decode: STT=4 (176.8–193.9 ms), matching current default STT_NUM_THREADS=4.
- Best TTS render: TTS=2 with STT=1 (193.1 ms), but ASR then 311.5 ms. Combined balance STT=2/TTS=2 (238.7/250.5) or STT=4/TTS=2 (193.9/271.9).
- Current default (STT=4, TTS=2) is near-optimal for hi local ASR; TTS cost 272 ms vs best 193 ms (~79 ms) due to CPU contention.
- RSS readings are noisy (521–2694 MB) and not comparable across runs; latency medians are the reliable signal.
- en (Groq Whisper, cloud) hit RPM 429 after 4 combos; thread sweep for cloud ASR not completable without rate-limit pacing/authorization. Local thread count does not affect cloud ASR latency materially (network dominates).

Conclusion: no config change warranted from this sweep; current defaults (STT=4/TTS=2) are supported by measurement for hi. Any change must re-run this sweep and compare.

Multi-language thread sweep (gu, mr, bn, ta, 4 repeats, STT {2,4} × TTS {2,4}):
- STT=4 consistently improves ASR decode across all 5 local languages vs STT=2 (gu 1896 vs 2224, mr 1690 vs 1959, bn 1564 vs 1221→1754, ta 1241 vs 1429). Supports STT_NUM_THREADS=4 default.
- TTS=2 is generally the safer choice: TTS=4 often degrades TTS render (bn 397 vs 245 ms, mr 344 vs 307) due to CPU contention, with inconsistent ASR gains. Current TTS_NUM_THREADS=2 default supported.
- Raw: runs/thread_sweep_20261118-113953.json.

VAD parameter sweep (synthetic TTS -> Silero VAD, 5 langs, threshold {0.3..0.6} x min_silence {0.15,0.20,0.26,0.35,0.45}):
- All combos: 0 false-positive segments on 5 s of digital silence (no phantom speech).
- hi/mr/bn/ta: current default (thr 0.5, ep 0.26) yields 0 turn splits.
- gu: current default (thr 0.5, ep 0.26) reproduces 1 turn split, endpoint fires 2240 ms early, captures 4.01/5.45 s speech. Raising min_silence to >=0.35 s eliminates the split (0 splits, captures 4.25+ s). This is synthetic (smooth TTS) evidence only; real Gujarati recordings (with natural pauses) still required before changing config.
- en at 0.45 s: 0 splits, endpoint +32 ms.
- Recommendation (NOT applied): add {"gu": 0.35} to ENDPOINT_SILENCE_BY_LANG, pending real recordings + regression test. Config unchanged this pass.
- Raw: runs/vad_sweep_20261118-114936.json (+ en run 20261118-115014).

No optimization applied this pass. Baseline captured above. Any future change must re-measure and append to `runs/`.