# 12 — Regression Results

## Final test execution

- Command: `.venv313/Scripts/python.exe -m unittest discover -s tests -t .`
- Date: 2026-11-18
- Result: **186 tests OK**, 0 failures, 0 errors.
- Duration: 137.369 s.
- Exit code: 0.
- Record: `test_runs/run_20261118-113000.txt`.

## Test files (17)

test_capacity, test_codecs, test_dataset_tools, test_evaluate_ab, test_human_eval, test_lan_tls_check, test_latency_budget, test_metrics, test_pilot_monitor, test_security_revalidate, test_streaming_stt, test_text, test_turn_taking, test_v3_performance, test_ws_server, test_xss, (test_turn_taking new this engagement).

## New tests this engagement

- `tests/test_turn_taking.py` — 10 tests: BargeInSinkTests (3), LanguageSwitchEvidenceTests (4), EndpointRetuneTests (3). All pass.

## Compile check

- `py_compile` clean on `src/call_server.py src/tts_engine.py src/sts_pipeline.py tests/test_turn_taking.py`.

## Historical baseline

- Pre-engagement: 176 tests OK (144 s).
- Post: 186 tests OK (137.4 s). No tests weakened or disabled.

## Not run / not available

- CI on GitHub: workflow authored but never executed (no remote).
- Physical-device / phone tests: NOT TESTED.
- Human evaluation: NOT TESTED.