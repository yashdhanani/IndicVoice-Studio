# 01 — Project Audit (IndicVoice)

Date: 2026-11-18 · Auditor: this engagement · Method: full read of `src/`, `web/`, `tests/`, `benchmarks/`, `docs/`, plus live test execution.

## 1. Repository shape

- Python package: `src/` (call_server, sts_pipeline, streaming_stt, tts_engine, config, text_normalizer, translit, humanizer, asr_ctc, evaluate, tls_cert, quality_console).
- Web client: `web/` (index.html, app.js, quality/).
- Tests: `tests/` — 17 files, 186 tests (this run).
- Benchmarks: `benchmarks/` (run_stage_bench, run_e2e_latency, run_latency_v3, run_concurrency, run_capacity, run_noise_matrix, run_tts_bench, run_llm_script_check, plus audit_conversational, language_matrix, quality_baseline).
- Docs: `docs/` (technical audit, roadmap, production readiness, E2E latency report, changelog, production V1 final report, realworld V2 final report).
- Models: `models/` (local, git-ignored; VAD, Whisper, IndicConformer per lang, MMS/tiny/supertonic TTS).
- No git remote; git history exists locally since 5768a6d.

## 2. Entry points

- `src/call_server.py` — FastAPI app: `/health`, `/auth/ticket`, `/ws/voice`, `/ws/telephony`, optional TLS, warm-up, watchdog, abuse caps.
- `src/sts_pipeline.py` — `VoiceAgent` (LLM→TTS), `shared_stt`, `maybe_switch_language`, `TTSPool`.
- `src/streaming_stt.py` — speculative/partial ASR state machine.
- `src/tts_engine.py` — `TTSEngine` (tiny/supertonic/MMS), `AudioPlayer`, `AudioSink`.
- `src/config.py` — language tables, model paths, endpoints, thread counts.
- Tools: `tools/smoke_streaming.py`, `tools/pilot_monitor.py`.
- Web: `web/index.html` + `web/app.js`.

## 3. Complete architecture (cascaded, not native STS)

Browser/phone audio (PCM16 / μ-law) → WebSocket → `CallSession.feed` → Silero VAD → `StreamingSTT` (speculative + authoritative decode) → `_clean_transcript` → `maybe_switch_language` → `VoiceAgent.start_response` (worker thread) → `LLMClient.stream_chat` (Groq, gpt-oss-20b, reasoning low) → `SentenceSplitter` → `TTSPool.speak_sentences` (tiny/supertonic/MMS) → `AudioSink`/`AudioPlayer` → resample → PCM16/μ-law frames → WebSocket → playback.

This is a **modular cascaded Speech-to-Speech system** (separate ASR, LLM, TTS). It is NOT a native end-to-end speech-to-speech model. No jointly trained STS foundation model is used; none is feasible on the target CPU.

## 4. Defect register (summary)

Full register: `docs/INDICVOICE_TECHNICAL_AUDIT.md` (D1–D23) and `03_pipeline_validation.md`.

Resolved this engagement (prior): D1 ASR error survival, D2 XSS fallback, D3 token hardening, D5 tests, D6 streaming accuracy guard, D14 inbound limits, D22 XSS health, D23 eval path fix.

Open: D4 (no remote — still no git remote), D7 hallucination filter eats "एक", D8 idle watchdog inbound-only, D9 barge-in race (suspected), D10 tiny TTS mid-gen cancel, D11 backend-availability MMS-only, D12 Latin loanwords 8 langs, D13 sender pool pressure, D15–D21 hygiene. New (this audit): F4 Gujarati VAD turn split (1 split on synthetic clip), F5 endpoint retune per language (now implemented), F6 sink mute-after-cancel (now implemented), F7 Latin-switch evidence gate (now implemented).

## 5. Baseline measurements (this run)

- Tests: 186 OK, 137.4 s.
- Stage bench (latest run, 2 repeats): 6 languages measured, 6 skipped (no test phrase in tool); see `stage_bench_20261118-112145.json`.
- RSS end: 1344.4 MB (stage bench process).
- E2E (prior, 2×40 live turns): hi p50 1130 ms, p95 2766 ms; en p50 1264 ms, p95 2887 ms.
- Port 8000: closed at audit time (no user process touched).

## 6. Component connection check

All pipeline stages are connected and exercised by `tests/test_ws_server.py` (end-to-end with stub LLM) and `tests/test_streaming_stt.py`. Real provider integration (Groq LLM/ASR) is exercised by benchmarks with disclosure; no paid-tier calls triggered beyond free tier.