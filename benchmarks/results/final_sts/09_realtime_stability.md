# 09 — Real-Time Stability

## Tested

- Conversation turn-taking: 10 regression tests (tests/test_turn_taking.py) — barge-in sink mute, Latin-switch evidence gate, endpoint retune. All pass.
- WebSocket session lifecycle: tests/test_ws_server.py (isolated server, ephemeral port).
- Streaming STT state machine: tests/test_streaming_stt.py (partials, speculation, staleness, suppression, resume).
- Abuse caps: utterance 60 s, session 1800 s, outbound queue 4096 — tested.
- Idle watchdog 180 s — implemented; inbound-only counting (D8 open).
- Barge-in: 0.45 s sustained VAD speech while speaking → cancel + flush + mute.

## Not tested

- Rapid-barge-in stress / D9 race (suspected): NOT TESTED.
- Multi-hour soak at 2–3 concurrent calls: NOT TESTED.
- >5 concurrent sessions: NOT TESTED (by design; level 10 not attempted).
- Physical device (mic/phone) interruption: NOT TESTED.
- Network drop / reconnect recovery: NOT TESTED.
- Long utterance truncation >60 s: NOT TESTED live.

## Conclusion

Core turn-taking and interruption logic is unit/WS-tested and stable on synthetic paths. Real-world stability (device, network, soak, high concurrency) is NOT validated. No claim of production stability.