# IndicVoice — Technical Audit (Phase 2)

Date: 2026-11-17 · Auditor method: full read of every `src/` module and the
browser client's render paths; claims below are marked **verified (code)**,
**measured**, or **suspected (needs test)**. Baselines: `eval/manifest_report.md`
(n=3/language, full pipeline) and this engagement's A/B runs (`eval/ab_full.*`).

## 1. Pipeline walkthrough (as built)

```
mic/phone → [echo gate −32 dBFS while speaking] → 512-sample VAD windows
  → Silero VAD (threshold 0.5, min_speech 0.25 s, min_silence 0.26 s / en 0.45 s)
  → segment ≥0.3 s → ASR
       local: IndicConformer INT8 (greedy CTC, silence-trimmed, engine lock)
       en:    Groq whisper-large-v3-turbo (script-guard → local fallback)
       streaming mode: partials during speech + speculative full decode
                       in the endpoint silence window (src/streaming_stt.py)
  → _clean_transcript (hallucination filter)
  → maybe_switch_language (script-based, session default breaks hi/mr, bn/as ties)
  → VoiceAgent.respond on worker thread:
       system prompt pinned to turn language + script rule
       LLM SSE stream (gpt-oss-20b, reasoning low, keep-alive socket)
       SentenceSplitter → ensure_script → ≤2 sentences
       TTSPool.speak_sentences: head-clause split, per-sentence script routing,
       tiny (24 kHz) / supertonic (44.1 kHz) / MMS (16 kHz) → Humanizer →
       SeamBlender → AudioSink → resample → PCM16 / μ-law frames
  barge-in: 0.45 s sustained VAD speech while speaking → cancel + flush
  backchannel: filler clip after 0.35 s if no audio yet
  watchdog: 180 s without inbound audio → close 4408
```

Latency budget (measured baseline, p50, ms): ASR 160 (hi) – 1485 (ml);
LLM TTFT 404 (kn) – 1277 (ml); TTS TTFA 134 (mr) – 530 (ta);
E2E 769 (hi) – 2074 (ml). The 260 ms endpoint silence precedes all of these
and is not included in `asr_ms`/E2E — true EOU-to-first-audio is ~260 ms higher.

## 2. Defect register

### P1 — fix before any shared/LAN deployment

| # | Defect | Evidence | Impact |
|---|---|---|---|
| D1 | **ASR exception kills the call.** `_process_frame` awaits `streamer.finalize` / `stt.transcribe` with no try/except; the WS handlers only catch `WebSocketDisconnect`. A Groq timeout/HTTP error (`_GroqWhisper` raises `RuntimeError`) or any decode error propagates out of `feed()` and drops the socket. LLM/TTS errors *are* caught (`start_response._run`); ASR is the unprotected stage. | verified (code): [call_server.py:377-383](../src/call_server.py), [sts_pipeline.py:330-334](../src/sts_pipeline.py) | one network blip mid-call disconnects the user |
| D2 | **XSS in fallback call page.** `_INDEX_HTML`'s `log()` does `el.innerHTML += …${msg}` with transcript/reply text. Served only when `web/index.html` is missing; the real client uses `textContent` everywhere (verified). | verified (code): [call_server.py:447-451](../src/call_server.py) | script injection via crafted transcript/LLM output on the fallback page |
| D3 | **Token check is not constant-time and token rides the query string.** `params.get("token") == token`; query strings land in proxy logs/browser history. Default is open access; binding beyond localhost only *warns*. | verified (code): [call_server.py:88-91,800-804](../src/call_server.py) | credential leakage paths on LAN/phone deployments |
| D4 | **No version control.** Project is not a git repo (`.gitignore` exists, no history). No rollback, no change attribution. | verified on disk | any regression is unrecoverable except from manual copies |
| D5 | **Zero automated tests.** No `tests/`, no `test_*.py`. *(Resolved 2026-11-17: 45-test suite in `tests/`, all passing — see changelog.)* | verified on disk | every change is unguarded; brief requires unit/integration/WS layers |
| D6 | **Streaming accuracy hole (found & fixed this engagement).** Quiet speech resuming below the RMS gate (`peak*0.06`) left a stale speculative transcript authoritative: kn_02 CER 0.036→0.214 **measured**. Fix: finalize discards a speculative result when audio beyond expected trailing silence arrived after its snapshot; speculation suppressed after a mid-utterance invalidation. | measured + fix in [streaming_stt.py](../src/streaming_stt.py); re-validation passed 2026-11-17 (CER/WER parity all 12 languages) | violated "never compromise accuracy" until fixed |

### P2 — correctness / robustness, fix soon

| # | Defect | Evidence | Impact |
|---|---|---|---|
| D7 | **Hallucination filter eats a real word.** `_HALLUCINATIONS` contains `"एक"` (Hindi "one"); a caller answering "एक" is silently ignored. | verified (code): [sts_pipeline.py:370-380](../src/sts_pipeline.py) | dropped turns in numeric dialogs |
| D8 | **Idle watchdog counts inbound only.** Comment claims "every inbound frame / outbound audio" but `last_activity` is bumped only in `feed()`. A caller listening >180 s without speaking is disconnected mid-reply. | verified (code): [call_server.py:240-241,332,629-639](../src/call_server.py) | spurious 4408 on long replies/holds |
| D9 | **Barge-in can race the keep-alive LLM socket.** On cancel, the SSE generator's `finally` drains the remaining body (`response.read()`); `start_response` joins the old worker only 2 s. If the drain outlives the join, two worker threads share one `http.client` connection (not thread-safe) via `_conns`/`_active_conn`. | suspected (needs rapid-barge-in test): [sts_pipeline.py:634-645,893-907](../src/sts_pipeline.py) | corrupted request / hung turn under fast interruptions |
| D10 | **Tiny TTS ignores cancel_event mid-generation.** No callback path in the tiny branch; barge-in only takes effect between clauses/sentences. | verified (code): [tts_engine.py:366-375](../src/tts_engine.py) | up to one clause of extra speech after interrupt |
| D11 | **Backend-availability checks are MMS-only.** `TTSPool.langs` filter and `/health` `ready` test `tts-<lang>/model.onnx`, ignoring tiny/supertonic. Latent today (all 12 MMS dirs present) but a tiny-only install would report voices missing and exclude them from the pool. | verified (code): [tts_engine.py:559-561](../src/tts_engine.py), [call_server.py:577-579](../src/call_server.py) | wrong readiness on partial installs |
| D12 | **Latin loanwords silently dropped for 8 languages.** `localize_text` rewrites Latin only for en/hi/mr/gu although `_SCRIPT_SHIFT` covers bn/as/pa/or/ta/te/kn/ml; elsewhere the vocab filter deletes Latin chars with no warning (docstring promises one). Tiny backend passes `vocab=None` so unfiltered Latin reaches the model instead. | verified (code): [translit.py:209-228](../src/translit.py) | "WhatsApp"/"OTP" vanish or mispronounce in 8 languages |
| D13 | **Sender thread-pool pressure.** Each outbound item costs a `run_in_executor` slot blocked up to 0.2 s; ASR finalize uses the same default executor. Many concurrent calls can starve decode tasks. | suspected (needs load test): [call_server.py:276-302](../src/call_server.py) | latency collapse under concurrency |
| D14 | **No inbound message-size/rate limits.** WS binary frames and telephony JSON accepted up to uvicorn's 16 MB default; base64 decoded without cap; no per-IP connection limit. | verified (code): [call_server.py:657-698](../src/call_server.py) | memory exhaustion by a malicious client |

### P3 — hygiene / documentation

- D15 `config.py:44-48` comment describes 0.45 s while `ENDPOINT_SILENCE = 0.26` (stale).
- D16 `call_server.py` docstring claims barge-in "well under 200 ms"; actual threshold is 0.45 s sustained speech.
- D17 `requirements.txt` lists `num2words` (unused; normalization is hand-rolled) and `indic-nlp-library` (not installed in `.venv313` → optional normalization silently skipped).
- D18 `.gitignore` ignores `tools/` (smoke client would be untracked if git is initialised).
- D19 `agent.marks` is cleared per respond(); a latency event emitted after the next turn started reads the new turn's marks (minor race, cosmetic).
- D20 `AudioSink.is_speaking` is wall-clock estimated from emit time, not client playback; network jitter skews the echo gate/barge-in window slightly.
- D21 hi/mr and bn/as are indistinguishable by script; session default wins ties (documented behavior, but a Marathi caller in a hi-default session stays on the Hindi ASR).

## 3. Accuracy findings (measured, n=3/language — small sample, expand per Phase 6)

- Strong: mr/ta/te CER 0.000; kn 0.012; gu 0.025; ml 0.029; pa 0.042; bn 0.044; hi 0.047.
- **or CER 0.088 / WER 0.400** — usable but weakest Indic Conformer after as.
- **as CER 0.268 / WER 0.889** — Bengali-model alias; orthography mismatch dominates. Native Assamese export path exists (`colab/assamese_asr_export.ipynb`, `asr_ctc.py`) but no model is published/present. Highest-accuracy roadmap item.
- **en CER 0.141** — driven by en_01 (0.423) on Groq whisper-large-v3-turbo; en_02/03 perfect. Needs a larger corpus before any backend change (rule: no mapping changes without measurement).
- Streaming vs block: after the D6 fix, accuracy must be identical by construction (same authoritative decode); parity is the acceptance gate on every A/B run.

## 4. Latency engineering status (this engagement, measured)

Design: partials during speech (cost-gated), authoritative full decode started
speculatively 0.12 s into the endpoint silence window. Iterations:

1. **Merge-based streaming** (partials + tail merge): rejected — kn CER 0.012→0.318, bn/or/pa degraded (measured). Merging abandoned.
2. **Speculative decode, ungated partials**: accuracy parity restored, but slow models' partials held the engine lock at speech offset — mr 810→1641 ms, kn 975→2059 ms p50 (measured). Rejected.
3. **Cost-gated partials**: 8/12 languages faster, but kn_02 accuracy hole (D6) and mr/ml still regressed (partial cost measured on shorter buffers; mid-utterance pauses triggered wasted speculative decodes).
4. **Final: predicted-cost gating + staleness guard + post-miss suppression** — full A/B re-validation in progress; results and acceptance verdict recorded in `INDICVOICE_CHANGELOG.md` and `benchmarks/results/`.

Structural floor: endpoint silence (260/450 ms) + LLM TTFT (400–1300 ms) +
TTS TTFA (130–530 ms). The 300–500 ms EOU-to-first-audio aspiration is reachable
only for hi-class ASR with a warm LLM socket and head-clause TTS; per-language
realistic targets are set in the roadmap.

## 5. Security & privacy review

- Secrets: `.env` git-ignored, loaded without overriding real env; keys never logged (error strings carry HTTP status/body excerpts, not headers). `.env` itself was not read during this audit.
- TLS: self-signed RSA-2048/SHA-256, SANs for localhost+LAN IPs, 825 days; private key unencrypted in `certs/` (git-ignored). Adequate for LAN; not for internet exposure.
- Auth: opt-in shared token (D3). No per-user identity, no rate limiting (D14).
- Audio privacy: eval recordings git-ignored; no audio persisted server-side per call (streams only); `audio_out/` holds local CLI smoke outputs.
- Cloud calls: Groq LLM + en ASR send audio/text to a third party — must be disclosed to callers in any production use. No paid-tier usage was triggered by this audit (free-tier models only, per authorization).

## 6. Observability review

Present: per-turn `latency` events (asr/llm/tts/first_audio), `partial_transcript`,
`transcript` with `asr_mode`/`asr_strategy`, `/health` with per-voice readiness,
eval harness with p50/p95. Missing: structured logs (prints only), no request
IDs, no error counters, no metrics export, no call recordings for debugging
(privacy trade-off), client-side metrics not persisted. Roadmap items.

## 7. Test plan (Phase 7, to be implemented)

- Unit: codecs (PCM16/μ-law round-trip, resample), `_trim_silence`, normalizer
  (currency/dates/phones/OTP per language), SentenceSplitter, translit/vocab,
  SeamBlender, `_clean_transcript` (incl. D7 regression), StreamingSTT state
  machine with a fake engine (partials gating, speculation, staleness, resume).
- Integration: STTEngine on the 36-recording corpus (accuracy parity gate),
  TTSEngine smoke per backend, LLMClient against a local SSE stub (no paid calls).
- WebSocket: `/ws/voice` + `/ws/telephony` end-to-end with a stub LLM
  (`agent_factory` injection already supported), barge-in, idle timeout,
  token auth, streaming on/off, D1 error-survival regression.