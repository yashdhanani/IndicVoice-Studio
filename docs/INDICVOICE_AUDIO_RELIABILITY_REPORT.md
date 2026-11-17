# IndicVoice — Audio Reliability Report (Production Hardening V1, Phase C)

Date: 2026-11-17
Status vocabulary: PASS (automated) / PASS — manually verified / PARTIAL / FAIL / NOT TESTED / NOT APPLICABLE.

**Honesty statement:** no physical microphone, phone, or carrier call was
available in this environment. Every physical scenario below is
**NOT TESTED** and is written as an executable checklist for the person who
does have the devices. Nothing in this report claims real-world acoustic
validation. All automated audio evidence comes from file-based playback
over real WebSocket connections (synthetic starter clips), which exercises
the transport, VAD, endpointing, ASR, LLM and TTS wiring — not room
acoustics, mic hardware, or carrier networks.

## What IS verified (automated, file audio)

| Scenario | Evidence | Status |
|---|---|---|
| Browser-style turn: 16 kHz PCM16 frames at real-time pace → transcript → reply audio | `tests/test_ws_server.py::test_streaming_turn_end_to_end`, `test_block_turn_end_to_end` (71-test suite) | PASS |
| Telephony μ-law path: 20 ms/160-byte frames in, 20 ms frames out | `test_telephony_mulaw_turn` | PASS |
| ASR failure does not drop the call; next turn works | `test_asr_error_does_not_drop_call` | PASS |
| Endpoint silence handling incl. pause-heavy utterance (staleness guard) | `tests/test_streaming_stt.py` quiet-resume test; live smoke `benchmarks/results/smoke_live_hi.md` | PASS |
| Idle / max-duration / abuse closes | watchdog + cap tests | PASS |
| Codec round-trips (PCM16, μ-law, resample 8↔16 kHz) | `tests/test_codecs.py` (13 tests) | PASS |

## Manual checklists (all NOT TESTED)

Setup for all phone tests: server started with `start_voice_phone.bat`
(HTTPS 8443, self-signed cert, all 12 languages warmed),
`INDICVOICE_TOKEN` set in `.env`, phone on the same Wi-Fi, open
`https://<pc-ip>:8443/?token=<token>` and accept the certificate warning.

### C1 — Laptop microphone, quiet room
1. Open the call page on the PC itself (`https://127.0.0.1:8443`), grant mic.
2. Speak one Hindi sentence at normal volume; observe partial transcripts
   appearing while speaking, final transcript after ~0.3 s silence, reply audio.
3. Repeat in English and one Dravidian language (ta/te/kn — cloud ASR path).
4. Verify: no echoed TTS re-transcription (echo gate), barge-in works when
   interrupting the reply mid-sentence.
- Expected: intelligible transcripts, first audio < ~2.5 s after speech end
  on the reference laptop (see E2E report), interruption stops playback.
- Status: **NOT TESTED** (no mic capture performed in this environment).

### C2 — Phone on LAN (Android Chrome / iOS Safari)
1. Connect phone to same Wi-Fi; open the HTTPS URL with token; accept warning.
2. Grant mic permission (iOS requires HTTPS — verify the page loads and the
   mic prompt appears; on iOS also verify audio playback after a user tap).
3. Run 5 turns per language family; check transcript script correctness
   (native script, no mojibake), reply audibility, latency feel.
4. Lock the phone mid-call and unlock: verify whether the session survives
   or reconnects cleanly (browser suspend behavior differs by OS).
- Expected: mic granted only on secure origin; turns complete; no crash on
  lock/unlock (reconnect acceptable, document behavior).
- Status: **NOT TESTED**.

### C3 — Carrier telephony via WebSocket gateway
1. Point a Twilio/Plivo-style media-stream gateway at
   `wss://<host>:8443/ws/telephony?lang=hi&token=<token>` (μ-law 8 kHz).
2. Place a real PSTN call; verify `connected` event, media frames in/out,
   transcript + reply audible on the call.
3. Test DTMF-free hangup (`stop` event) and caller hangup (socket close):
   server must release the session and per-IP slot.
4. Verify 20 ms outbound pacing does not drift over a 2-minute call.
- Expected: intelligible two-way audio; clean teardown; no frame drift.
- Status: **NOT TESTED** (no gateway/carrier available; the μ-law wire
  format itself is automated-tested).

### C4 — Noise and distance
1. TV/office babble at ~55–65 dB: 5 utterances; note CER subjectively
   (transcript vs intended) and endpoint behavior (no premature cutoff).
2. Street/traffic noise: repeat; note failures honestly.
3. Far-field (2–3 m from laptop mic): repeat; the RMS silence gate may
   classify quiet speech as silence — the staleness guard protects the
   final transcript, but partials may lag. Record what actually happens.
- Expected: degraded but usable recognition in office noise; document
  street/far-field failure modes rather than assuming success.
- Status: **NOT TESTED**.

### C5 — Interruptions and long calls
1. Barge-in: interrupt the reply 10× at different points; verify playback
   stops within ~0.5 s and the new utterance is recognized.
2. 10-minute continuous conversation: verify no memory growth trend
   (server RSS), no watchdog false-close while audio flows, and that the
   30-minute cap (4410) fires when reached.
3. Rapid turn-taking (10 turns back-to-back): verify no transcript bleed
   between turns.
- Expected: clean barge-in; stable RSS; caps fire exactly once.
- Status: **NOT TESTED** (long-call RSS trend will be partially covered by
  the concurrency benchmark, but a real 10-minute conversation is not).

## Known acoustic limitations (carried from the audit)

- Quiet speech below the RMS gate (`peak*0.06`) is not detected as speech
  resume; the finalize staleness guard prevents wrong transcripts but
  partials can lag. Far-field validation (C4) should quantify this.
- The evaluation corpus is TTS-synthesized; absolute CER/WER numbers are
  optimistic until the 240-utterance real dataset (Phase D) is collected.
- `as` (Assamese) currently shares the Bengali ASR model — a documented
  workaround, not a validated language route.

## Completion gate

Phase C is complete only when C1–C5 are executed on real devices and each
row above is updated to PASS — manually verified / PARTIAL / FAIL with
dates, device models, and observed notes. Until then this report is a
checklist, not a validation.