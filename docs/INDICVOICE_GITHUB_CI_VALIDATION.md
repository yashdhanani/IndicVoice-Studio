# IndicVoice — GitHub / CI Validation (Real-World Validation V2, Phase H)

**Bottom line:** The CI workflow is correctly designed as a model-free, cloud-key-free
fast tier plus a manual model tier. The fast tier was **proven locally** (106 pass /
1 model-backed skip, 0 errors) by hiding the model directory. **GitHub-hosted execution
is NOT TESTED** — this repository has no git remote and no `gh` CLI, so an Actions run
cannot be triggered or observed here. Exact activation instructions are below.

Status vocabulary: PASS (automated) / PASS — manually verified / PARTIAL / FAIL /
NOT TESTED / NOT APPLICABLE.

---

## 1. What was inspected

| Artifact | Finding |
|---|---|
| `.github/workflows/ci.yml` | Two jobs: `fast` (push/PR/dispatch) and `model-tier` (dispatch only). |
| `requirements-ci.txt` | numpy, scipy, fastapi, uvicorn, websockets, aiohttp, sounddevice. No torch / sherpa-onnx / onnxruntime / groq / cryptography. |
| `requirements.txt` | Full deps for the manual model tier. |
| git remote | **None configured.** |
| `gh` CLI | **Not installed.** |
| Secrets in workflow | **None.** Only `PYTHONIOENCODING=utf-8` is set. No inference API keys anywhere. |

## 2. Fast tier is genuinely model-free and key-free

All heavy libraries are imported **inside functions**, never at module load:

- `src/asr_ctc.py:29`, `src/config.py:143` — `import onnxruntime`
- `src/sts_pipeline.py:73,804`, `src/tts_engine.py:201,297,377` — `import sherpa_onnx`
- `src/tls_cert.py:38-41` — `from cryptography …`

Module-level third-party imports are limited to `numpy`, `scipy`, `fastapi`,
`sounddevice` — all present in `requirements-ci.txt` (CI installs `libportaudio2`
for sounddevice). Model-backed tests guard on **file existence** and skip before
importing any engine, so the absence of models on a fresh checkout is sufficient.

### Local fast-tier simulation (PASS — automated)

Command (models hidden, no token):

```
INDICVOICE_MODELS_DIR=<nonexistent> INDICVOICE_TOKEN= \
  python -m unittest discover -s tests -v
```

Result: **Ran 107 tests — OK (skipped=1)**, 0 errors, 0 failures.
The single skip is `test_ws_server.WSTests` ("local hi models / starter WAVs not
present"). The second fast-tier step, `python benchmarks/validate_dataset.py`,
also exits 0 (reports the honest 0/240 corpus state).

Evidence: `benchmarks/results/realworld_v2/ci_validation_v2.json` and
`ci_fast_tier_sim.log`.

**Suite growth note:** the 107-test count above was the suite at Phase H time.
Phases I/J/K subsequently added security (20), pilot-monitor (12) and CPU-sampler
(2) tests; the final fast-tier simulation is **141 tests — OK (skipped=1)**,
recorded in `ci_fast_tier_final.log`. The model-free/key-free property is unchanged.

**Caveat (honest):** the simulation used the full development venv with the model
directory hidden, not a clean `requirements-ci` install. `cryptography` is present
in this venv, so `test_lan_tls_check.InspectCertTests` ran here; on the real fast
tier those tests skip via `skipUnless`. The simulation is therefore a faithful
*superset* of fast-tier behaviour — it cannot hide a fast-tier failure.

## 3. Model tier (manual, still no paid cloud)

`model-tier` runs only on `workflow_dispatch`. It installs `requirements.txt`,
downloads **free local** hi+en models and VAD via `src.download_models`, then runs
the full suite. No inference API key is referenced. This tier was **not executed on
GitHub** (NOT TESTED); the equivalent model-backed tests run locally during Phase K.

## 4. GitHub execution — NOT TESTED + activation instructions

No remote and no `gh` exist in this environment. To activate CI on GitHub:

1. Create an empty repository (private recommended) under your account/org.
2. Add the remote and push (run these yourself; they publish code):
   ```
   git remote add origin git@github.com:<owner>/<repo>.git
   git push -u origin main
   ```
3. The `fast` job triggers automatically on push. No secrets are required.
4. To run the model tier: Actions tab → CI → "Run workflow" (`workflow_dispatch`).
5. (Optional) Protect `main` and require the `fast` check to pass before merge.

**Do not** add inference API keys to CI. The fast tier needs none; the model tier
uses free local models. If a future cloud benchmark is ever wired into CI, it must
use a repository secret and remain manual — never on push.

## 5. Acceptance gate (CI)

**PARTIAL** — fast tier proven model-free/key-free locally (106 pass / 1 skip);
GitHub-hosted execution NOT TESTED (no remote). Gate becomes PASS once a GitHub
Actions run of the `fast` job is observed green.