# IndicVoice — CI Guide (Production Hardening V1, Phase H)

## Tier model

| Tier | Trigger | Models | Cloud keys | What runs |
|---|---|---|---|---|
| **fast** | every push / PR | none | none | codecs, text normalization, streaming state machine (fake engine), bind security, queue cap, static XSS checks, dataset schema validation |
| **model** | manual `workflow_dispatch` | downloaded in-job (hi, en, VAD) | none | the full 72-test suite including real-model WebSocket integration turns (StubLLM — still no cloud) |
| **cloud** | never in CI | — | — | live Groq/OpenAI turns stay a local, authorized activity (`tools/smoke_streaming.py`, `benchmarks/run_e2e_latency.py`) |
| **stress / benchmarks** | local only | yes | LLM key from `.env` | `benchmarks/run_e2e_latency.py`, `benchmarks/run_concurrency.py` — hardware-sensitive, must not run on shared CI runners |

CI never depends on paid cloud inference: the integration tests inject
`StubLLM`, and the fast tier has no keys at all.

## Files

- `.github/workflows/ci.yml` — both jobs.
- `requirements-ci.txt` — fast-tier dependency set (numpy, scipy, fastapi,
  uvicorn, websockets, aiohttp, sounddevice). `libportaudio2` is installed
  via apt because `sounddevice` needs the PortAudio shared library at import.
- `requirements.txt` — full stack for the model tier and local runs.

## Model-absent behavior (skip, never fake-pass)

`tests/test_ws_server.py::WSTests.setUpClass` raises `unittest.SkipTest`
when the VAD, hi TTS, hi ASR models or the starter WAV are missing (they are
git-ignored). Skips are reported as skips in the CI log — a green fast-tier
run does **not** claim the model-backed paths were exercised. Verified
locally by simulating a missing VAD path: the class reports
`OK (skipped=1)`, 0 errors.

The state-machine tests (`tests/test_streaming_stt.py`) use a fake engine
and always run, so the three accuracy-safety mechanisms (cost gating,
staleness guard, post-miss suppression) are covered even in the fast tier.

## Local equivalents

```bash
# fast tier (any machine with requirements-ci.txt)
python -m unittest discover -s tests -v
python benchmarks/validate_dataset.py

# full suite (models present)
.venv313/Scripts/python.exe -m unittest discover -s tests -v

# dataset completeness gate (manual milestone, not CI)
python benchmarks/validate_dataset.py --require-complete
```

## Current status

- Workflow authored and lint-checked by inspection: **PARTIAL**.
- Executed on GitHub Actions: **NOT TESTED** — this repository has no remote
  configured yet. To activate: create the remote, push `main`, and confirm
  the fast job runs green; then trigger the model tier once via
  *Actions → CI → Run workflow*.
- Fast-tier test selection verified locally (skip simulation above); the
  full 72-test suite passes locally on Windows/Python 3.13. Linux behavior
  of the model tier (sherpa-onnx/onnxruntime wheels) is **NOT TESTED**.

## Rules for future changes

1. Never weaken or delete a test to make CI green; fix the code or record a
   documented, reviewed skip.
2. New security controls must ship with a regression test in the fast tier
   wherever possible (no models, no network).
3. CI must never receive `GROQ_API_KEY`/`OPENAI_API_KEY` secrets; live-cloud
   verification stays local and authorized.
4. Benchmark scripts refuse occupied ports and only kill their own server
   subprocess — keep that property when extending them.