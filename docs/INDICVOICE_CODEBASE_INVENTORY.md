# IndicVoice — Codebase Inventory (Phase 1)

Date: 2026-11-17 · Method: every `src/` module read in full; models, dependencies,
entry points and env references verified on disk by direct inspection.
No secrets are reproduced here (`.env` was deliberately not read; only
`.env.example` and variable *names* in code).

## 1. What the system is

A CPU-first, 12-language Indian voice agent: browser/phone microphone →
Silero VAD → ASR (local IndicConformer INT8 or Groq cloud Whisper) →
Groq LLM (`openai/gpt-oss-20b`, streamed) → local TTS (tiny Matcha+Vocos →
Supertonic 3 → MMS VITS fallback) → streamed audio back over WebSocket,
with barge-in, backchannels and per-turn language switching.

Languages (all preserved): hi, gu, mr, bn, ta, te, kn, ml, pa, or, as, en.
Assamese ASR is an explicit, documented alias of the Bengali Conformer
(`config.INDIC_ASR["as"] = dict(..., alias_of="bn")`); an optional native
wav2vec2 CTC export (`models/asr-as-ctc`, `src/asr_ctc.py`) overrides it when present.

## 2. Module map (`src/`, 5,021 lines Python)

| File | Lines | Role | Key facts verified |
|---|---|---|---|
| `config.py` | 398 | Paths, language tables, model specs, tunables | `.env` loader (no override of real env); endpoint silence 0.26 s (en 0.45 s); backend selection `tts_backend()` tiny→supertonic→mms; `STT_BACKEND_BY_LANG={"en":"groq"}`; `STT_FAST_LANGS` empty (local wins accuracy everywhere); token/idle/reasoning env knobs |
| `sts_pipeline.py` | 1140 | STTEngine (indic/whisper/groq/ctc/transducer), LLMClient (SSE, keep-alive, 429 fallback), VoiceAgent (VAD, language switch, sentence-streamed respond, backchannel, barge-in), CLI | Process-wide `shared_stt` cache; engine lock serialises decodes; silence trim + script-guard with local fallback; hallucination filter |
| `call_server.py` | 810 | FastAPI app: `/ws/voice` (PCM16 16 kHz), `/ws/telephony` (8 kHz μ-law), `/health`, static web UI | Per-call `CallSession`; ring buffer pre-onset; streaming STT integrated (`streaming=1` default, `--no-streaming` / `?streaming=0` to disable); idle timeout 180 s; optional `?token=`; TLS via `--tls` |
| `streaming_stt.py` | 259 | Pseudo-streaming wrapper (this engagement) | Partials during speech, cost-gated; authoritative full-buffer decode speculatively during endpoint silence; accuracy identical to block by construction |
| `tts_engine.py` | 680 | TTSEngine/TTSPool, AudioPlayer, shared model cache | Per-model generation lock; RMS loudness levelling for tiny voices; head-clause split for early playback; SeamBlender crossfades |
| `text_normalizer.py` | 546 | Numbers/currency/dates/phones/UPI/OTP → spoken words, 12 languages; SentenceSplitter | Full irregular 21–99 tables for hi/gu; IndicNLP normalizer optional (not installed in `.venv313`) |
| `humanizer.py` | 220 | Prosody jitter, clause pauses, −55 dB room tone, filler clips, SeamBlender | Deterministic seed; fillers synthesised once and cached |
| `translit.py` | 228 | Latin loanwords/digits → voice script; vocab filter | Curated tables hi/gu; rule-based roman→Devanagari + Unicode script shift for 9 more scripts; `localize_text` only applies Latin rewriting for en/hi/mr/gu |
| `evaluate.py` | 606 | WER/CER + latency harness, block/streaming/ab modes, `--asr-only` | Real-time-pace feeding; simulated endpoint semantics; NFC + punctuation-strip scoring |
| `download_models.py` | 252 | HF/GitHub model fetch + ONNX metadata patch | `vocab_size:auto` counted from tokens; atomic tmp-then-replace save |
| `asr_ctc.py` | 78 | Optional Assamese wav2vec2 CTC ONNX greedy decoder | Used only when `models/asr-as-ctc/model.onnx` exists (not present) |
| `tls_cert.py` | 83 | Self-signed cert for LAN HTTPS (phone mic needs secure origin) | RSA-2048, SANs for localhost + LAN IPs, 825 days, stored in `certs/` |

## 3. Frontend (`web/`)

- `index.html` (318 l), `app.js` (1187 l), `styles.css` (496 l).
- Browser client: mic capture → PCM16 16 kHz WebSocket, playback queue,
  partial/final transcript display, language picker, barge-in. Served by `call_server.py`.

## 4. Models on disk (`models/`, verified present)

| Group | Dirs | Size each | Notes |
|---|---|---|---|
| IndicConformer ASR INT8 | `asr-{hi,gu,mr,bn,ta,te,kn,ml,pa,or}` | hi 188 MB; others 132 MB | all have `model.int8.onnx` + `vocab.txt`; hi/gu also `tokens.txt`. No `asr-as` (alias of bn) |
| MMS TTS | `tts-{12 langs}` | 109 MB | `model.onnx` + `tokens.txt` complete for all 12 |
| Indic Tiny TTS | `tiny-{12 langs}` | 91–92 MB | `onnx/text_encoder.onnx` present → tiny is the active backend for all 12 in `.venv313` (onnxruntime 1.32.0) |
| Supertonic 3 INT8 | `sherpa-onnx-supertonic-3-tts-int8-2026-05-11` | 139 MB | all 7 required files present; 44.1 kHz; fallback for hi/en when tiny absent |
| Whisper | `whisper-base` 154 MB, `whisper-tiny` 99 MB | | INT8 encoder/decoder + tokens |
| VAD | `silero_vad.onnx` | 1.8 MB | |
| Samples | `samples/` | 309 KB | eng/guj/hin sample wavs |
| Absent | `asr-as-ctc`, `zipformer-streaming` | — | optional paths, correctly skipped |

## 5. Runtimes & dependencies

- **`.venv313` = Python 3.13.18 — the working runtime** (uv-created, no pip module).
  Installed (dist-info verified): sherpa-onnx 2.0.1, onnxruntime 1.32.0,
  numpy 2.5.5, scipy 1.18.1, fastapi 0.163.1, uvicorn 0.54.0, aiohttp 3.14.5,
  sounddevice 0.5.6. **jiwer, pandas, indic-nlp-library: not installed**
  (evaluate.py computes WER/CER itself; IndicNLP normalization silently skipped).
- `venv` = Python 3.15.0 — onnxruntime has no 3.15 wheel → tiny backend unavailable there; not the runtime to use.
- `requirements.txt` pins match the above (onnxruntime>=1.20, cryptography>=42).
- Console is cp1252: **`PYTHONIOENCODING=utf-8` required** for Indic output (bat files set it).

## 6. Environment variables (names only)

| Variable | Where | Default |
|---|---|---|
| `GROQ_API_KEY` | sts_pipeline | required for cloud LLM/ASR |
| `INDICVOICE_LLM_BACKEND` / `INDICVOICE_LLM_MODEL` | sts_pipeline / config | groq / `openai/gpt-oss-20b` |
| `GROQ_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OLLAMA_HOST` | sts_pipeline | optional alternate LLM backends |
| `INDICVOICE_GROQ_STT_MODEL` | config | `whisper-large-v3-turbo` |
| `INDICVOICE_STT_MODE` | config | `fast` |
| `INDICVOICE_REASONING_EFFORT` | config | `low` |
| `INDICVOICE_TOKEN` | config | empty = **open access** |
| `INDICVOICE_IDLE_TIMEOUT` | config | 180 s |
| `INDICVOICE_MODELS_DIR`, `INDICVOICE_AUDIO_DIR` | config | project-relative |

`.env` exists (git-ignored), auto-loaded by `config._load_dotenv` without overriding real env vars.

## 7. Entry points

- `start_voice.bat` → `.venv313\Scripts\python.exe -m src.call_server --port 8000 --warm <all 12>`; polls `/health`, opens browser.
- `start_voice_phone.bat` → `--host 0.0.0.0 --port 8443 --tls --warm <all 12>`; comments instruct setting `INDICVOICE_TOKEN`.
- `python -m src.sts_pipeline` — local mic/speaker CLI agent.
- `python -m src.evaluate --manifest eval_data/manifest.json [--mode block|streaming|ab] [--asr-only]`.
- `python -m src.download_models --langs … | --all | --tiny | --supertonic | --vad --stt`.
- `tools/smoke_streaming.py` — WS smoke client (streams a wav at real-time pace, prints events/latencies).
- Notebooks: `colab/assamese_asr_export.ipynb`, `training_colab/train_indic_tts.ipynb`.

## 8. Evaluation assets & prior baselines

- `eval_data/`: 36 real-pace recordings (3 per language × 12) + `manifest.json` (reference texts) + 9-case subset. **3 utterances/lang — below the brief's ≥20 target; expansion is roadmap item.**
- `eval/manifest_report.md` — prior full-pipeline baseline (n=3/lang, ms):

| lang | CER | WER | ASR p50 | LLM TTFT p50 | TTS TTFA p50 | E2E p50 | E2E p95 |
|---|---|---|---|---|---|---|---|
| hi | 0.047 | 0.170 | 160 | 447 | 174 | 769 | 826 |
| gu | 0.025 | 0.111 | 831 | 472 | 179 | 1539 | 2656 |
| mr | 0.000 | 0.000 | 1415 | 448 | 134 | 1990 | 2308 |
| bn | 0.044 | 0.233 | 765 | 562 | 202 | 1303 | 1625 |
| ta | 0.000 | 0.000 | 749 | 503 | 530 | 1770 | 1863 |
| te | 0.000 | 0.000 | 755 | 592 | 150 | 1807 | 2643 |
| kn | 0.012 | 0.083 | 989 | 404 | 179 | 1589 | 3023 |
| ml | 0.029 | 0.111 | 1485 | 1277 | 152 | 2074 | 3524 |
| pa | 0.042 | 0.170 | 821 | 472 | 147 | 1478 | 2280 |
| or | 0.088 | 0.400 | 806 | 992 | 171 | 1998 | 2880 |
| as | 0.268 | 0.889 | 767 | 668 | 231 | 1626 | 1942 |
| en | 0.141 | 0.143 | 464 | 770 | 144 | 1432 | 1504 |

- `eval/ab_full.{json,md}` — block-vs-streaming A/B (this engagement; being regenerated with the final cost-gated design).
- Other reports: accuracy/groq/indic/whisper/latency comparisons from backend selection.

## 9. Tests

**None.** No `tests/` directory, no `test_*.py` anywhere in the project.
Closest artifact: `tools/smoke_streaming.py` (manual WS smoke client).
Automated tests at unit/integration/WS layers are a Phase 7 deliverable.

## 10. Structural observations (feed into Phase 2 audit)

1. **Not a git repository.** `.gitignore` exists but there is no history → no rollback mechanism, no change attribution. (P1)
2. `TTSPool.langs` availability check tests only the **MMS** `model.onnx` path (`tts_engine.py:560`), ignoring tiny/supertonic backends — a language with only tiny downloaded would be excluded from the pool. All 12 MMS dirs happen to exist here, so no live impact. (P2, latent)
3. `translit.localize_text` restricts Latin rewriting to en/hi/mr/gu even though `_SCRIPT_SHIFT` covers 9 more scripts; for other languages Latin words fall through to the vocab filter and are **silently dropped** (module docstring promises a warning that does not exist). Tiny backend passes `vocab=None`, so no filtering there. (P2)
4. `config.py:44-48` comment says 0.45 s while `ENDPOINT_SILENCE = 0.26` — stale comment. (P3)
5. Tiny-backend `synthesize` ignores `cancel_event` mid-generation (no callback path); barge-in only takes effect between clauses. (P2)
6. `jiwer`/`pandas` absent → any pasted harness code assuming them would fail; `evaluate.py` is self-contained (verified).
7. `.gitignore` ignores `tools/` — the smoke client and uv binaries would not be committed if git is initialised. (P3)
8. Token auth is opt-in (`INDICVOICE_TOKEN` empty = open). LAN/phone deployment must set it; bat file warns but does not enforce. (P1 security)
9. `requirements.txt` lists `num2words` but normalization is hand-rolled in `text_normalizer.py` (num2words not installed/used). (P3 cleanup)