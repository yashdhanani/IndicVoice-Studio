# 03 — Pipeline Validation

Each stage exercised by code + tests where noted. "PASS — Automated" = covered by automated test/benchmark; "NOT TESTED" = no real exercise.

| # | Stage | Source | Input→Output | Provider | Network | Timeout | Measured | Status |
|---|---|---|---|---|---|---|---|---|
| 1 | Microphone capture | `call_server.py` (client `web/app.js`) | PCM16 frames | browser | no | — | NOT TESTED (physical) | NOT TESTED |
| 2 | Preprocessing/resample | `call_server.resample` | float32/PCM16 | local | no | — | exercised by tests/test_codecs | PASS — Automated |
| 3 | VAD | Silero via sherpa | 512-sample frames | local | no | 0.25 s min speech | onset 672–1248 ms (stage bench) | PASS — Automated (synthetic) |
| 4 | Endpointing | `config.endpoint_for` | silence duration | local | no | 0.26 s (0.45 en) | measured per lang | PASS — Automated (synthetic) |
| 5 | Streaming ASR | `streaming_stt.StreamingSTT` | audio→text | IndicConformer/Groq | en only | engine lock | A/B parity 12/12 (docs) | PASS — Automated (synthetic) |
| 6 | Language ID | `maybe_switch_language` | transcript→lang code | script-based | no | — | Latin gate ≥3 words (new test) | PASS — Automated |
| 7 | Transcript finalize | `_clean_transcript` | text→text | local filter | no | — | tested | PASS — Automated |
| 8 | Conversation context | `VoiceAgent` | text→prompt | in-memory | no | — | tested via WS | PASS — Automated |
| 9 | LLM generation | `LLMClient.stream_chat` | prompt→SSE tokens | Groq gpt-oss-20b | yes | 30 s | TTFT 280–950 ms (E2E report) | PASS — Automated (live, free tier) |
| 10 | Text normalization | `text_normalizer/translit/humanizer` | text→spoken text | local | no | — | tested | PASS — Automated |
| 11 | Streaming TTS | `TTSPool.speak_sentences` | text→audio | tiny/supertonic/MMS | no | — | RTF 0.07–0.12 (stage bench) | PASS — Automated (synthetic) |
| 12 | Audio encoding | `call_server` | float32→PCM16/μ-law | local | no | — | tested | PASS — Automated |
| 13 | Audio playback | browser/phone | PCM→speaker | client | no | — | NOT TESTED (physical) | NOT TESTED |
| 14 | Interruption/next turn | barge-in + cancel | VAD speech→cancel | local | no | 0.45 s sustained | 10 tests (test_turn_taking) | PASS — Automated |

## Interruption handling (verified)

- Sink mute-after-cancel: `AudioSink._accepting` + `resume()`; cancel mutes before flush; `push()` drops while muted. Fixed this engagement (F1).
- TTS player: cancel checks before `_emit` in both speak paths; `resume()` on new turn. Fixed this engagement (F1).
- Barge-in threshold: 0.45 s sustained VAD speech while speaking. NOT measured under rapid stress (D9 suspected race remains open).

## Failure recovery (verified)

- ASR errors survive (D1 fixed + regression test).
- Watchdog: 180 s idle (inbound-only; D8 open).
- Abuse caps: utterance 60 s, session 1800 s, outbound queue 4096 (tested).
- Provider fallback: LLM fallback list empty by default; ASR backend by lang.

## Known unverified

- Physical microphone, phone network, real-device playback: NOT TESTED.
- Multi-hour soak, >5 concurrent sessions: NOT TESTED.
- D9 rapid-barge-in race: suspected, not reproduced.