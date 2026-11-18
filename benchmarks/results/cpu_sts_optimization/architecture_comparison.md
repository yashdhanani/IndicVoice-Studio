# Architecture Comparison

## A — CPU-Efficient Hybrid STS (PRIMARY, current design)

```
Mic → local capture → local VAD → streaming transport → ASR (local/cloud) → LID → LLM (Groq) → TTS (local/cloud) → jitter buffer → playback
```

- Local CPU preprocessing, VAD, TTS (tiny/supertonic/MMS) already measured.
- ASR: local IndicConformer (11 langs) + Groq Whisper (en).
- LLM: Groq gpt-oss-20b (cloud).
- Advantages: low local CPU, measured RTF 0.07–0.12, no GPU, existing tests pass.
- Disadvantages: network dependency for LLM + en ASR; E2E p95 2.8–7.1 s (LLM TTFT dominant).

## B — Full Local CPU STS

- All stages local (ASR + LLM + TTS).
- Not feasible for high-quality LLM on 4-core laptop without severe latency/quality loss; no local LLM currently integrated.
- Risk: unusable response quality or >10 s latency. NOT recommended without a small local LLM benchmark.

## C — Adaptive Hybrid (per-language routing)

- Per-language provider selection via registry (configurable, no core pipeline changes).
- Only justified if a cloud TTS/ASR shows measured advantage for specific languages.
- Must avoid mid-conversation provider switching.

## Decision

Keep **Architecture A (hybrid)** as primary. No architecture change this pass; current code already implements it. Adaptive routing (C) deferred until per-language benchmarks with authorized keys. Full-local (B) deferred (no local LLM).