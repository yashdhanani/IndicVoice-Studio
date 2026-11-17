# IndicVoice — Microphone Validation Program (Real-World V2, Phase C)

Date: 2026-11-17
Status vocabulary: PASS (automated) / PASS — manually verified / PARTIAL / FAIL / NOT TESTED / NOT APPLICABLE.

**Honesty contract:** no physical microphone capture was performed in this
environment. The automated probes below are *capability checks* — they prove
the browser APIs, the shipped AudioWorklet code, the resampler math and the
WebSocket transport work. They do **not** prove that a real microphone, in a
real room, produces correct transcripts. All 17 physical scenarios (M01–M17)
are **NOT TESTED**. An AudioWorklet compilation test is not microphone
validation, and this document never treats it as one.

## 1. The tool

`web/mic_validation.html` — served by the call server at
`/static/mic_validation.html`. It contains:

1. **Environment auto-detection**: browser + version (from UA), OS, secure
   context flag, page origin, hardware concurrency, timestamp.
2. **Probes P1–P8** (automated capability checks, run on button click or via
   `window.__runProbes()`).
3. **Scenarios M01–M17**: each with written instructions and a 9-field record
   form — microphone type/model, input sample rate (Hz), actual audio
   duration (s), ASR transcript, recognition correctness
   (correct / minor errors / wrong / no transcript / n/a), first-audio latency
   (ms), playback behavior, errors observed, result
   (NOT TESTED / PASS / PARTIAL / FAIL). Every form defaults to NOT TESTED.
4. **Optional mic measurement** (`measureMic`): only after the operator
   explicitly clicks and grants permission; reads `track.getSettings()`
   (device label, native sample rate, channel count, echoCancellation /
   noiseSuppression / autoGainControl flags) and stops the track immediately.
   Nothing is recorded or uploaded.
5. **Export**: download / clipboard JSON of environment + probes + all
   scenario records (`window.__resultsJSON()`), for filing under
   `benchmarks/results/realworld_v2/`.

### How to run it (operator with a real microphone)

```bat
start_voice.bat            rem or: .venv313\Scripts\python.exe -m src.call_server --port 8010
```

Open `http://127.0.0.1:8010/static/mic_validation.html` in the browser under
test. Click **Run probes**, then work through M01–M17 on the actual call page
(`/`), filling each form as you go. Export the JSON and save it as
`benchmarks/results/realworld_v2/mic_validation_<browser>_<date>.json`.
Repeat per browser/device. Do not mark a scenario PASS without having
performed it on that device.

## 2. Automated probe results (executed 2026-11-17)

Evidence: `benchmarks/results/realworld_v2/mic_probes_embedded_chromium.json`.

**Environment caveat:** the probes ran in Qoder's embedded Chromium
150.0.7871.250 (Electron 43.8.4) on Windows — **not standalone Chrome
desktop**. Results transfer as engine-level evidence (same Blink/V8 audio
stack) but standalone Chrome and every other browser remain untested.
Microphone permission was **denied** in this automated environment;
`getUserMedia` was never granted and no speech was captured.

| Probe | What it checks | Result | Detail |
|---|---|---|---|
| P1 | `getUserMedia` API present | PASS | available |
| P2 | `AudioContext({sampleRate:16000})` honored | PASS | ctx.sampleRate=16000 → native resampling path active |
| P3 | **Shipped** MicProcessor worklet compiles | PASS | extracted live from `/static/app.js` (not a copy) and registered in a real AudioContext; compilation ≠ mic validation |
| P4 | Linear resampler math, 48k→16k 440 Hz sine | PASS | max sample error 0.0000 vs ideal (algorithmic check, not mic audio) |
| P5 | Microphone permission state | INFO | denied (expected in automation; no capture attempted) |
| P6 | Audio input device enumeration | INFO | 1 input visible; labels hidden until permission granted |
| P7 | WebSocket transport reachable | PASS | real WS to `/ws/voice?lang=hi&streaming=1` opened; no audio sent; closed immediately |
| P8 | Playback graph initializes | PASS | ctx.state=running, clock advanced 0.264 s with a silent buffer |

**P8 incident (recorded, not hidden):** the first full probe run reported
P8 FAIL — the audio clock advanced 0.000 s within the probe's 250 ms window.
Isolated trials showed the identical zero-gain graph advancing 0.176–0.592 s
once the audio service was warm, i.e. cold-start latency in this environment,
not a product defect. The probe wait was extended to 700 ms plus one retry;
the check itself (`currentTime` must advance) was not weakened. The second
full run passed at 0.264 s. On real hardware, re-run P8 cold and note the
first-render delay — it is part of perceived playback-init latency (Phase F).

Server: task-owned `src.call_server` on port 8010, torn down after the probes
(process tree killed; the pre-existing port-8000 process was never touched).

## 3. Physical scenarios — all NOT TESTED

Each row is an executable instruction for the person with the hardware.
Record all 9 fields per scenario in the page form; export the JSON.

| ID | Scenario | Procedure (summary) | Expected | Status |
|---|---|---|---|---|
| M01 | Permission accepted | Start a call, accept the mic prompt | state chip → connected; mic meter moves on speech | NOT TESTED |
| M02 | Permission denied | Deny the mic prompt | clear error; no crash, no silent continue | NOT TESTED |
| M03 | Mic removed mid-call | Unplug/disable input during an active call | observable error/stall; note recovery after re-plug | NOT TESTED |
| M04 | 44.1 kHz input device | Use a 44.1 kHz-native device/interface | record reported input rate; recognition works | NOT TESTED |
| M05 | 48 kHz input device | Same with 48 kHz-native (most laptop/phone mics) | same | NOT TESTED |
| M06 | 16 kHz resampling correctness | Speak a known sentence | transcript matches; native AudioContext resampling or linear fallback (P4 checks fallback math only) | NOT TESTED |
| M07 | Low-volume speech | Speak quietly at ~30 cm | note whether VAD triggers; RMS gate may classify quiet speech as silence — record honestly | NOT TESTED |
| M08 | Normal-volume speech | Conversational baseline turn | correct transcript, reply audio | NOT TESTED |
| M09 | Loud speech | Speak loudly, no clipping distortion | transcript correct; note AGC pumping | NOT TESTED |
| M10 | Background noise | Fan/TV/office babble at realistic level | note degradation, not assumed success | NOT TESTED |
| M11 | Natural pauses | 0.3–0.8 s hesitations mid-sentence | turn not cut early; full sentence recognized (endpoint 0.26 s hi-family / 0.45 s en + staleness guard) | NOT TESTED |
| M12 | Long utterance | Speak continuously 20–40 s | no truncation below the 60 s cap; coherent reply | NOT TESTED |
| M13 | Rapid speech | Speak fast | note transcript correctness | NOT TESTED |
| M14 | Different speaker | Second person speaks | note recognition quality change | NOT TESTED |
| M15 | Barge-in | Interrupt the assistant mid-reply | playback stops promptly (~0.5 s); new turn recognized | NOT TESTED |
| M16 | Tab backgrounding | Background tab 30 s mid-call, return | note whether audio/WS survived browser throttling | NOT TESTED |
| M17 | Disconnect + reconnect | Drop Wi-Fi briefly mid-call, restore | clean close; fresh call connects | NOT TESTED |

Known risk areas to watch (from the V1 audit, carried forward): quiet speech
below the RMS gate (`peak*0.06`) is not detected as speech resume — the
finalize staleness guard protects the final transcript but partials can lag
(M07); browser timer throttling can affect M16; the linear fallback resampler
is lower quality than native resampling (M04/M06 on devices that refuse a
16 kHz context).

## 4. Browser compatibility checklist

| Browser / platform | Priority | Probes | Physical M01–M17 | Status |
|---|---|---|---|---|
| Chrome desktop (Windows) | **primary** | not run standalone | not run | NOT TESTED |
| Embedded Chromium 150 (Electron, Windows) | reference only | P1–P8 executed (§2) | not run | capability checks PASS; physical NOT TESTED |
| Edge desktop | secondary | — | — | NOT TESTED |
| Firefox desktop | secondary | — | — | NOT TESTED (AudioWorklet + `sampleRate` constructor support must be verified, not assumed) |
| Safari macOS | secondary | — | — | NOT TESTED |
| Android Chrome (phone) | phone path | — | — | NOT TESTED (see INDICVOICE_PHONE_LAN_TEST.md) |
| iOS Safari (phone) | phone path | — | — | NOT TESTED (HTTPS mandatory for mic; playback needs user gesture) |

## 5. Completion gate

Phase C is complete only when M01–M17 have been executed on at least Chrome
desktop with a real microphone, each row updated to PASS — manually verified /
PARTIAL / FAIL with date, device model, browser version and the exported
JSON filed under `benchmarks/results/realworld_v2/`. Until then this document
is a program plus capability evidence, not a microphone validation.