# Before / After Comparison

No optimization applied this pass. Baseline captured; this file will hold before/after deltas when changes are made.

## Baseline (current)

- Tests: 186 OK, 137.4 s.
- E2E p50: hi 1130.1 ms, en 1264.2 ms; p95: hi 2766.2, en 2886.6 ms.
- TTS RTF: 0.07–0.12.
- RSS: ~1.3 GB (stage bench), 845 MB (E2E server peak).
- Safe concurrency: ≤2–3 calls.
- ASR synthetic CER: hi 0.047, gu 0.025, mr 0.000, bn 0.044, ta 0.000, te 0.000, kn 0.012, ml 0.029, pa 0.042, or 0.088, as 0.268, en 0.141 (n=3/lang, prior).

## After

(No changes applied this pass. Future optimizations must append before/after deltas here with measurement conditions.)