# IndicVoice — Real-World Validation V2 Baseline (Phase A)

Date: 2026-11-17 · Scope: independent inspection of git state, code, tests and
benchmark artifacts before accepting any reported V1 number. Status vocabulary:
PASS (automated) / PASS — manually verified / PARTIAL / FAIL / NOT TESTED /
NOT APPLICABLE.

## 1. Git state (inspected, not assumed)

| Item | Observed value |
|---|---|
| Branch | `main` |
| HEAD at phase start | `d0ff9e7` ("Ignore generated review bundles") |
| Commit history | 9 commits, `5768a6d` (stable baseline) → `d0ff9e7`; every V1 phase checkpoint present |
| Remote | **none configured** (`git remote -v` empty) |
| Stash | empty |
| Working tree at start | one unstaged deletion: `eval/shoot.mjs`; nothing else modified or untracked |
| Identity | repo-local `IndicVoice Dev <dev@indicvoice.local>` (user-approved placeholder) |

## 2. Special issue: `eval/shoot.mjs` — investigated and restored

Followed the required investigation sequence:

1. **Tracked?** Yes — committed in `4a84be9` ("Preserve visual-QA work"), the
   only commit touching it.
2. **Committed contents inspected**: 127-line Node script driving headless
   Chrome over CDP (port 9223) to capture full-page + live-state screenshots
   into `eval/shots/` (git-ignored). Benign local QA tooling; no secrets, no
   network calls beyond localhost CDP.
3. **Deletion staged or unstaged?** Unstaged (` D` in `git status`); nothing
   in the index (`git diff --cached` empty).
4. **Legitimate local modifications?** None possible — the file was absent
   from disk, so there was no uncommitted content to preserve. No stash, no
   other branch contains a variant.
5. **Safe to restore?** Yes: restoring a deleted tracked file with no local
   modifications loses nothing and is reversible (re-delete if intended).
6. **Action**: `git checkout -- eval/shoot.mjs` (single-file restore, not a
   tree-wide destructive checkout). Diff inspected before acting.
7. **Verified**: file present (6,776 bytes), `node --check` passes, working
   tree clean afterwards. Visual-QA capability preserved.

Cause of the disappearance remains unknown (not deleted by the engineering
session; possibly OneDrive sync or manual action). Recorded, not guessed.

## 3. Documentation consistency review (CI guide)

The brief reported a duplicated model-tier row and contradictory 71/72
test-count lines. **Inspection did not reproduce a duplicated row**: the tier
table has four distinct rows (fast / model / cloud / stress). Test-count
findings and actions:

| Location | Finding | Action |
|---|---|---|
| `INDICVOICE_CI_GUIDE.md` | both count references already say 72; fast/model tiers unambiguous; Windows-local vs Linux-CI distinction present; GitHub status explicitly NOT TESTED | none needed |
| `INDICVOICE_AUDIO_RELIABILITY_REPORT.md:19` | present-tense "(71-test suite)" | corrected to 72 |
| `INDICVOICE_SECURITY_HARDENING.md` B7 | "71/71 PASS" — accurate *Phase B checkpoint* record | kept as history; added note that the current suite is 72 |
| `INDICVOICE_CHANGELOG.md` B7 row, `PRODUCTION_V1_BASELINE.md` commit row | historical 71 references tied to commit `8b9efc1` | kept — they describe that checkpoint, not the current state |

No undocumented CI execution is claimed anywhere: GitHub execution remains
**NOT TESTED** (no remote; `gh` CLI not installed on this machine).

## 4. Reported V1 baseline — independently re-verified from artifacts

| Reported claim | Artifact inspected | Verified value | Status |
|---|---|---|---|
| 72/72 tests passing | full suite executed this session | `Ran 72 tests in 136.359 s — OK` (Windows, `.venv313`) | PASS (automated) |
| E2E p50 hi 1130 ms / en 1264 ms | `benchmarks/results/production_v1/e2e_v1.json` | hi p50 1130.1, p90 1937.2, p95 2766.2; en p50 1264.2, p90 1589.8, p95 2886.6; 0 failed turns, n=20/lang | confirmed |
| 33/33 concurrency turns, levels 1/2/3/5 | `production_v1/concurrency_v1.json` | 3+6+9+15 = 33 OK, success 1.0 every level; RSS peak 732.5 MB | confirmed |
| TTS RTF 0.11–0.20 | `production_v1/tts_v1.json` | rtf_p50 0.110 (hi) – 0.200 (kn); all 12 backends `tiny` | confirmed |
| A/B parity reproduced twice | `production_v1/ab_v1.json`, `ab_v1_run2.json` | CER/WER identical block=streaming, 12/12 langs, both runs; values match original `eval/ab_full.json` | confirmed |
| Readiness 63/100 | `INDICVOICE_PRODUCTION_READINESS.md` | weighted rows recompute to 63.0 | confirmed |
| Review bundle from HEAD `d0ff9e7` | bundle cover + git log | **correction**: bundle was archived at `4fb184d` (one commit earlier; `d0ff9e7` only changed `.gitignore`, which does not affect bundle contents). Bundle exists, 293,712 bytes, 111 entries | confirmed with correction |

Historical results (`eval/`, `benchmarks/results/` root and `production_v1/`)
are all present and were not modified. V2 outputs go to
`benchmarks/results/realworld_v2/` only.

## 5. Environment (unchanged from V1)

- Intel i7-8565U 4C/8T 15 W, 16 GB RAM, Windows 11, Git Bash.
- Runtime `.venv313/Scripts/python.exe` (Python 3.13, sherpa-onnx 2.0.1,
  CPU-only). `PYTHONIOENCODING=utf-8` required.
- **Port 8000**: pre-existing python.exe PID 23004 (~888 MB RSS) — the user's
  running server. Identified, never touched. V2 harnesses use port-free
  checks and their own ports (8010+), killing only their own process trees.
- Port 8010: free at phase start.
- No `gh` CLI, no git remote → GitHub CI activation cannot be executed here
  (Phase H will prepare exact instructions and mark execution NOT TESTED).
- No physical microphone/phone participant available to this session; no
  human listeners. Phases C/D/E build tooling + protocols and mark physical
  validation NOT TESTED. No simulated result will be substituted.
- Groq free-tier key in `.env` (never read/committed); live benchmark usage
  follows the previously authorized pattern (small, controlled runs).

## 6. V2 execution contract

- Preserve the V1 implementation, all 12 language routes, conservative
  fallback, rollback switches, security controls and all 72 tests.
- Every significant change ships with regression tests.
- Real recordings: 0/240 today; increments reported as actual counts, never
  padded with synthetic audio. ASR output is never used as its own reference.
- All new results under `benchmarks/results/realworld_v2/`; no historical
  file overwritten.