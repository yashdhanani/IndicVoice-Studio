"""IndicVoice quality-audit console — task server on 127.0.0.1:8010.

Wraps the existing, proven tooling (speak_check harness, dataset ingest /
verify / validate, blind listening package builder and scorer) behind a small
JSON API and serves the audit console in web/quality. It never touches the
user-owned server on port 8000, never overwrites historical V1/V2 results,
never reads .env, and never calls cloud or paid inference.

Every mutation writes NEW files: manifest edits are backed up first, listener
responses and generated reports land in timestamped paths. Synthetic TTS
audio is never counted as human recordings; absent human evidence is reported
as NOT TESTED.

Run:  .venv313/Scripts/python.exe src/quality_console.py [--port 8010]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402

LANGS = ("hi", "gu", "mr", "bn", "ta", "te", "kn", "ml", "pa", "or", "as", "en")
LANG_NAMES = {
    "hi": "Hindi", "gu": "Gujarati", "mr": "Marathi", "bn": "Bengali",
    "ta": "Tamil", "te": "Telugu", "kn": "Kannada", "ml": "Malayalam",
    "pa": "Punjabi", "or": "Odia", "as": "Assamese", "en": "English",
}

MANIFEST = ROOT / "evaluation" / "dataset_manifest.jsonl"
BACKUP_DIR = ROOT / "evaluation" / "dataset_backups"
CONSENT_DIR = ROOT / "evaluation" / "dataset" / "consent"
QUARANTINE = ROOT / "evaluation" / "dataset" / "quarantine"
HVQ = ROOT / "evaluation" / "human_voice_quality"
RESPONSES = HVQ / "responses"
HQ_RESULTS = ROOT / "benchmarks" / "results" / "human_voice_quality"
WEB = ROOT / "web" / "quality"
PY = str(ROOT / ".venv313" / "Scripts" / "python.exe")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ingest_mod = _load("iv_ingest", ROOT / "benchmarks" / "ingest_dataset.py")
validate_mod = _load("iv_validate", ROOT / "benchmarks" / "validate_dataset.py")
score_mod = _load("iv_score", HVQ / "score_responses.py")
prepare_mod = _load("iv_prepare", HVQ / "prepare_samples.py")

app = FastAPI(title="IndicVoice quality console", docs_url=None, redoc_url=None)

_lock = threading.Lock()
_jobs: dict[str, dict] = {}
_undo_stack: list[Path] = []


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# evidence readers (read-only)
# --------------------------------------------------------------------------

def speak_runs() -> list[dict]:
    runs = []
    for p in sorted((ROOT / "eval").glob("speak_check_*")):
        if not p.is_dir() or not (p / "results.json").exists():
            continue
        d = read_json(p / "results.json")
        langs = d.get("languages", [])
        runs.append({
            "run": p.name,
            "generated": d.get("generated"),
            "repeats": d.get("repeats_per_sentence"),
            "n_renders": sum(l.get("n", 0) for l in langs),
            "clean": sum(l.get("clean_renders", 0) for l in langs),
            "statuses": {l["lang"]: l.get("status") for l in langs},
            "has_player": (p / "listen.html").exists(),
        })
    return runs


def latest_run() -> dict | None:
    runs = speak_runs()
    return runs[-1] if runs else None


def default_run() -> dict | None:
    """Most recent run covering all 12 languages; subset runs stay selectable."""
    runs = speak_runs()
    full = [r for r in runs if len(r.get("statuses") or {}) == len(LANGS)]
    pool = full or runs
    return pool[-1] if pool else None


def run_results(name: str) -> dict:
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(400, "bad run name")
    p = ROOT / "eval" / name / "results.json"
    if not p.exists():
        raise HTTPException(404, "run not found")
    return read_json(p)


def baselines() -> list[dict]:
    out = []
    bdir = HQ_RESULTS / "baseline"
    if bdir.exists():
        for p in sorted(bdir.iterdir()):
            if p.is_dir() and (p / "baseline.json").exists():
                d = read_json(p / "baseline.json")
                out.append({"run": p.name, "generated": d.get("generated"),
                            "head": (d.get("git") or {}).get("head"),
                            "tests": (d.get("automated_tests") or {}).get("status")})
    return out


def dataset_entries() -> list[dict]:
    return ingest_mod.load_manifest(MANIFEST)


def dataset_summary() -> dict:
    entries = dataset_entries()
    per_lang = {}
    for lang in LANGS:
        slots = [e for e in entries if e["lang"] == lang]
        collected = [e for e in slots if e.get("status") == "COLLECTED"]
        verified = [e for e in collected if e.get("transcript_verified")]
        problems = []
        for e in collected:
            problems.extend(validate_mod.validate_entry(e, ROOT))
        per_lang[lang] = {
            "slots": len(slots), "collected": len(collected),
            "verified": len(verified),
            "speakers": len({e.get("speaker_id") for e in collected}),
            "validation_problems": problems,
            "status": ("NOT TESTED" if not collected else
                       "PARTIAL" if problems or len(verified) < len(collected)
                       else "PASS (automated)"),
        }
    return {
        "total_slots": len(entries),
        "collected": sum(v["collected"] for v in per_lang.values()),
        "verified": sum(v["verified"] for v in per_lang.values()),
        "per_lang": per_lang,
        "human_dataset_status": ("NOT TESTED" if not any(
            v["collected"] for v in per_lang.values()) else "PARTIAL"),
    }


def listening_packages() -> list[dict]:
    out = []
    v2 = HVQ / "package.json"
    if v2.exists():
        d = read_json(v2)
        out.append({"id": "v2", "label": "V2 blind set (6 types × 12 langs)",
                    "n_samples": d.get("n_samples"), "dimensions": d.get("dimensions"),
                    "dir": str(HVQ.relative_to(ROOT))})
    for p in sorted(HVQ.glob("extended_*")):
        pkg = p / "package.json"
        if p.is_dir() and pkg.exists():
            d = read_json(pkg)
            out.append({"id": p.name, "label": "Extended blind set (10 types)",
                        "n_samples": d.get("n_samples"),
                        "dimensions": d.get("dimensions"),
                        "dir": str(p.relative_to(ROOT))})
    return out


def package_dir(pkg_id: str) -> Path:
    if pkg_id == "v2":
        return HVQ
    if pkg_id.startswith("extended_") and "/" not in pkg_id and ".." not in pkg_id:
        p = HVQ / pkg_id
        if (p / "package.json").exists():
            return p
    raise HTTPException(404, "unknown package")


def listening_status() -> dict:
    pkgs = listening_packages()
    responses = sorted(RESPONSES.glob("*.json")) if RESPONSES.exists() else []
    listeners = set()
    for r in responses:
        try:
            listeners.add(read_json(r).get("listener_id") or r.stem)
        except (json.JSONDecodeError, OSError):
            continue
    return {
        "packages": pkgs,
        "n_response_files": len(responses),
        "n_listeners": len(listeners),
        "status": "NOT TESTED" if not responses else "PARTIAL",
        "metric_label": "mean listener rating (5-point) — NOT ITU-T MOS",
    }


# --------------------------------------------------------------------------
# overview / languages
# --------------------------------------------------------------------------

PHONETIC_CHECKS = {
    "hi": ["Aspirated vs unaspirated consonants (क/ख, ग/घ, च/छ, त/थ, प/फ)",
           "Retroflex vs dental distinction (ट/त, ड/द, ण/न)",
           "Natural schwa deletion (e.g. समझ, not सम-झ-अ)",
           "Sentence-final falling intonation on statements",
           "Question intonation on क्या-questions"],
    "gu": ["Vowel length (ઇ/ઈ, ઉ/ઊ)", "Nasalization (અં, અઁ)",
           "Retroflex consonants (ટ, ડ, ણ)", "Native conversational rhythm",
           "Gujarati–English code-mixing (ઈમેલ, બુકિંગ)"],
    "mr": ["Retroflex vs dental (ट/त, ड/द, ण/न)", "Syllable stress and rhythm",
           "Natural Marathi sentence patterns", "Schwa handling distinct from Hindi"],
    "bn": ["Vowel realization (অ/আ, ই/ঈ)", "Consonant clusters (ক্ষ, জ্ঞ)",
           "Bengali intonation contours", "Regional pronunciation variation"],
    "ta": ["Retroflex / dental / alveolar distinction (ட/த/ற)",
           "Vowel length (அ/ஆ, இ/ஈ)", "Natural conversational intonation",
           "No voiced-stop aspiration contrasts (unlike Hindi)"],
    "te": ["Long vs short vowels (అ/ఆ, ఇ/ఈ)", "Consonant articulation clarity",
           "Native Telugu rhythm", "Common conversational word pronunciation"],
    "kn": ["Retroflex consonants (ಟ, ಡ, ಣ)", "Phoneme realization accuracy",
           "Word boundaries and intonation", "Native conversational flow"],
    "ml": ["Vowel length and consonant distinctions", "Complex clusters (ന്ത, ഞ്ച, ക്ത)",
           "Native pronunciation of എന്റെ / എന്നെ", "Conversational rhythm"],
    "pa": ["Tonal distinctions where relevant (ਘਰ/ਕਰ)", "Natural sentence rhythm",
           "Conversational vocabulary", "Geminate consonants (ਕੱਲ੍ਹ)"],
    "or": ["Vowel and consonant realization", "Native Odia sentence patterns",
           "Retroflex series", "Natural intonation"],
    "as": ["Assamese-specific phonetics (ৱ, ক্ষ)", "Distinct vowel realization vs Bengali",
           "Natural intonation", "Assamese vocabulary and sentence patterns"],
    "en": ["Indian English pronunciation where appropriate", "Clear articulation",
           "Stress, reductions, pauses, intonation",
           "Code-switching with Indian languages", "Digit/date verbalisation"],
}


@app.get("/api/overview")
def overview():
    run = default_run()
    matrix = []
    if run:
        d = run_results(run["run"])
        for l in d["languages"]:
            matrix.append({
                "lang": l["lang"], "name": LANG_NAMES[l["lang"]],
                "status": l["status"], "n": l["n"],
                "clean": l["clean_renders"],
                "cer_clean_mean": l["cer_clean_mean"],
                "cer_clean_max": l["cer_clean_max"],
                "rtf": l["render_rtf_mean"],
                "duration_mean_s": l["duration_mean_s"],
                "tts_backend": l["tts_backend"], "asr_backend": l["asr_backend"],
                "word_miss": l["word_miss_renders"],
                "script_miss": l["script_miss_renders"],
            })
    ds = dataset_summary()
    ls = listening_status()
    bl = baselines()
    return {
        "generated": now_iso(),
        "latest_run": run,
        "matrix": matrix,
        "gates": (run_results(run["run"]).get("gates") if run else None),
        "dataset": ds,
        "listening": ls,
        "baselines": bl,
        "tests": (read_json(HQ_RESULTS / "baseline" / bl[-1]["run"] / "baseline.json").get("automated_tests")
                  if bl else None),
        "human_evaluation": "NOT TESTED" if ls["n_response_files"] == 0 else "PARTIAL",
        "mos": "NOT TESTED",
        "notes": [
            "Round-trip evidence is synthetic TTS→ASR, not human speech evaluation.",
            "WER/CER measure intelligibility of renders, never TTS naturalness.",
            "Human dataset 0/240 collected means every human metric is NOT TESTED.",
        ],
    }


@app.get("/api/languages")
def languages():
    run = default_run()
    measured = {}
    if run:
        for l in run_results(run["run"])["languages"]:
            measured[l["lang"]] = l
    ds = dataset_summary()["per_lang"]
    out = []
    for lang in LANGS:
        m = measured.get(lang, {})
        defects = []
        for row in m.get("rows", []):
            if row.get("status") != "PASS (automated)":
                defects.append({
                    "sentence": row["sentence"], "take": row["take"],
                    "wav": row["wav"], "status": row["status"],
                    "reference": row["reference"], "hypothesis": row["hypothesis"],
                    "cer_clean": row["cer_clean"], "notes": row.get("notes", []),
                })
        out.append({
            "lang": lang, "name": LANG_NAMES[lang],
            "script": ingest_mod.SCRIPTS.get(lang),
            "tts_backend": m.get("tts_backend"),
            "asr_backend": m.get("asr_backend"),
            "asr_note": ("Bengali Conformer alias — no Assamese export"
                         if lang == "as" else None),
            "status": m.get("status", "NOT TESTED"),
            "phonetic_checks": PHONETIC_CHECKS[lang],
            "phonetic_status": "NOT TESTED — requires native-speaker evidence",
            "defects": defects,
            "dataset": ds[lang],
            "metrics": {k: m.get(k) for k in
                        ("n", "clean_renders", "cer_clean_mean", "cer_clean_max",
                         "wer_clean_mean", "render_rtf_mean", "duration_mean_s",
                         "hf_share_max", "audible_all")},
        })
    return {"languages": out, "run": run["run"] if run else None}


@app.get("/api/baseline")
def baseline():
    bl = baselines()
    if not bl:
        raise HTTPException(404, "no baseline audit yet")
    p = HQ_RESULTS / "baseline" / bl[-1]["run"]
    return {"run": bl[-1]["run"], "data": read_json(p / "baseline.json"),
            "markdown": (p / "baseline.md").read_text(encoding="utf-8"),
            "all": bl}


@app.get("/api/runs")
def runs():
    return {"runs": speak_runs()}


@app.get("/api/runs/{name}")
def run_detail(name: str):
    return run_results(name)


@app.get("/api/runs/{name}/audio/{file}")
def run_audio(name: str, file: str):
    if "/" in name or ".." in name or "/" in file or ".." in file:
        raise HTTPException(400, "bad path")
    p = ROOT / "eval" / name / "audio" / file
    if not p.exists() or p.suffix != ".wav":
        raise HTTPException(404, "audio not found")
    return FileResponse(p, media_type="audio/wav")


# --------------------------------------------------------------------------
# dataset CRUD (wraps proven ingest/verify/validate; backup + undo)
# --------------------------------------------------------------------------

def backup_manifest(tag: str) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dst = BACKUP_DIR / f"manifest_{stamp()}_{tag}.jsonl"
    shutil.copy2(MANIFEST, dst)
    return dst


def push_undo(tag: str) -> Path:
    b = backup_manifest(tag)
    remember(b)
    return b


def remember(b: Path) -> None:
    with _lock:
        _undo_stack.append(b)
        del _undo_stack[:-20]


@app.get("/api/dataset")
def dataset():
    entries = dataset_entries()
    for e in entries:
        if e.get("status") == "COLLECTED":
            e["_problems"] = validate_mod.validate_entry(e, ROOT)
        else:
            e["_problems"] = []
    return {"entries": entries, "summary": dataset_summary(),
            "noise_conditions": list(ingest_mod.NOISE),
            "devices": list(ingest_mod.DEVICES),
            "undo_available": bool(_undo_stack)}


@app.get("/api/dataset/{slot_id}/audio")
def dataset_audio(slot_id: str):
    e = next((x for x in dataset_entries() if x["id"] == slot_id), None)
    if not e or e.get("status") != "COLLECTED":
        raise HTTPException(404, "slot not collected")
    p = ROOT / e["audio_path"]
    if not p.exists():
        raise HTTPException(404, "audio missing")
    return FileResponse(p, media_type="audio/wav")


@app.post("/api/dataset/ingest")
async def dataset_ingest(
    request: Request, lang: str, reference: str, speaker: str, consent: str,
    noise: str = "clean", device: str = "laptop", slot_id: str = "",
    environment: str = "", convert: str = "1", dry_run: str = "0",
):
    if consent != "yes":
        raise HTTPException(400, "explicit recording consent is required")
    if not reference.strip():
        raise HTTPException(400, "reference must be human-written text, never ASR output")
    tmp_dir = ROOT / "evaluation" / "dataset" / "uploads"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir / f"upload_{stamp()}_{uuid.uuid4().hex[:6]}.wav"
    tmp.write_bytes(await request.body())
    b = backup_manifest("ingest")
    problems, entry = ingest_mod.ingest(
        ROOT, MANIFEST, tmp, lang, reference, speaker, True, noise, device,
        slot_id=slot_id or None, convert=convert == "1",
        environment=environment or None, dry_run=dry_run == "1")
    if problems:
        tmp.unlink(missing_ok=True)
        raise HTTPException(400, "; ".join(problems))
    if dry_run == "1":
        tmp.unlink(missing_ok=True)
        return {"entry": entry, "dry_run": True, "summary": dataset_summary()}
    remember(b)
    CONSENT_DIR.mkdir(parents=True, exist_ok=True)
    (CONSENT_DIR / f"{entry['id']}.json").write_text(json.dumps({
        "slot": entry["id"], "speaker_id": speaker, "consent": True,
        "consent_asserted_by": "recorder via console", "recorded_at": now_iso(),
        "reference_human_written": True, "device": device, "noise": noise,
    }, indent=2), encoding="utf-8")
    tmp.unlink(missing_ok=True)
    return {"entry": entry, "summary": dataset_summary()}


@app.post("/api/dataset/{slot_id}/verify")
def dataset_verify(slot_id: str, payload: dict):
    verifier = ((payload or {}).get("verifier") or "").strip()
    e = next((x for x in dataset_entries() if x["id"] == slot_id), None)
    if e is None:
        raise HTTPException(404, "unknown slot")
    if e.get("status") != "COLLECTED":
        raise HTTPException(400, f"slot {slot_id} is not COLLECTED")
    if not verifier:
        raise HTTPException(400, "missing pseudonymous verifier id")
    if verifier == e.get("speaker_id"):
        raise HTTPException(400, "verifier must be a second speaker, not the recorder")
    push_undo("verify")
    problems = ingest_mod.verify_transcript(MANIFEST, slot_id, verifier)
    if problems:
        raise HTTPException(400, "; ".join(problems))
    e = next(x for x in dataset_entries() if x["id"] == slot_id)
    return {"entry": e, "summary": dataset_summary()}


@app.post("/api/dataset/{slot_id}/clear")
def dataset_clear(slot_id: str):
    entries = dataset_entries()
    e = next((x for x in entries if x["id"] == slot_id), None)
    if not e:
        raise HTTPException(404, "unknown slot")
    if e.get("status") != "COLLECTED":
        raise HTTPException(400, "slot is not COLLECTED")
    push_undo("clear")
    src = ROOT / e["audio_path"]
    if src.exists():
        q = QUARANTINE / stamp()
        q.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(q / src.name))
    keep = {k: e[k] for k in ("id", "lang", "audio_path", "domain",
                              "prompt_hint", "target_speaker_group")}
    fresh = {**keep, "status": "NOT_COLLECTED", "reference_text": None,
             "speaker_id": None, "consent": None, "noise_condition": "clean",
             "device": None, "duration_s": None, "collected_at": None, "notes": None}
    entries = [fresh if x["id"] == slot_id else x for x in entries]
    ingest_mod.save_manifest(MANIFEST, entries)
    return {"entry": fresh, "summary": dataset_summary(),
            "note": "audio preserved in quarantine, never deleted"}


@app.post("/api/dataset/undo")
def dataset_undo():
    with _lock:
        if not _undo_stack:
            raise HTTPException(400, "nothing to undo")
        b = _undo_stack.pop()
    backup_manifest("pre-undo")
    shutil.copy2(b, MANIFEST)
    return {"restored_from": b.name, "summary": dataset_summary(),
            "undo_available": bool(_undo_stack)}


@app.post("/api/dataset/validate")
def dataset_validate():
    entries = dataset_entries()
    problems = {}
    for e in entries:
        if e.get("status") == "COLLECTED":
            p = validate_mod.validate_entry(e, ROOT)
            if p:
                problems[e["id"]] = p
    out = HQ_RESULTS / "reports" / f"dataset_validation_{stamp()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"generated": now_iso(), "problems": problems,
                               "summary": dataset_summary()}, indent=2,
                              ensure_ascii=False), encoding="utf-8")
    return {"problems": problems, "report": str(out.relative_to(ROOT)),
            "status": "PASS (automated)" if not problems else "PARTIAL"}


# --------------------------------------------------------------------------
# listening evaluation (blind packages; private map never leaves the server)
# --------------------------------------------------------------------------

@app.get("/api/listening")
def listening():
    return listening_status()


@app.get("/api/listening/{pkg_id}/package")
def listening_package(pkg_id: str):
    p = package_dir(pkg_id)
    return read_json(p / "package.json")


@app.get("/api/listening/{pkg_id}/audio/{code}")
def listening_audio(pkg_id: str, code: str):
    if "/" in code or ".." in code:
        raise HTTPException(400, "bad code")
    p = package_dir(pkg_id) / "audio" / f"{code}.wav"
    if not p.exists():
        raise HTTPException(404, "sample not found")
    return FileResponse(p, media_type="audio/wav")


@app.post("/api/listening/{pkg_id}/responses")
def listening_response(pkg_id: str, payload: dict):
    package_dir(pkg_id)  # validates id
    listener = (payload or {}).get("listener_id", "").strip()
    ratings = (payload or {}).get("ratings") or {}
    if not listener:
        raise HTTPException(400, "pseudonymous listener_id required")
    if not ratings:
        raise HTTPException(400, "no ratings submitted")
    sample_map = read_json(package_dir(pkg_id) / "private" / "sample_map.json")
    for code, dims in ratings.items():
        if code not in sample_map:
            raise HTTPException(400, f"unknown sample code {code}")
        for dim, v in dims.items():
            if dim not in score_mod.DIMENSIONS:
                raise HTTPException(400, f"unknown dimension {dim}")
            if not isinstance(v, (int, float)) or not 1 <= v <= 5:
                raise HTTPException(400, f"rating for {code}/{dim} outside 1-5")
    RESPONSES.mkdir(parents=True, exist_ok=True)
    safe = "".join(c for c in listener if c.isalnum() or c in "-_")[:40]
    out = RESPONSES / f"{pkg_id}_{safe}_{stamp()}.json"
    out.write_text(json.dumps({
        "listener_id": listener, "package": pkg_id,
        "submitted_at": now_iso(), "ratings": ratings,
        "feedback": (payload or {}).get("feedback") or {},
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"saved": out.name, "n_response_files": len(list(RESPONSES.glob('*.json')))}


@app.get("/api/listening/{pkg_id}/results")
def listening_results(pkg_id: str):
    p = package_dir(pkg_id)
    sample_map = read_json(p / "private" / "sample_map.json")
    responses = []
    if RESPONSES.exists():
        for f in sorted(RESPONSES.glob(f"{pkg_id}_*.json")):
            responses.append(read_json(f))
    report = score_mod.build_report(sample_map, responses)
    return report


@app.post("/api/listening/prepare")
def listening_prepare(payload: dict):
    langs = tuple((payload or {}).get("langs") or LANGS)
    repeats = int((payload or {}).get("repeats", 1))
    seed = (payload or {}).get("seed")
    with _lock:
        if any(j["kind"] == "prepare" and j["state"] == "running" for j in _jobs.values()):
            raise HTTPException(409, "a preparation job is already running")
    out_dir = HVQ / f"extended_{stamp()}"
    utter = HVQ / "utterances_v3.json"
    if not utter.exists():
        raise HTTPException(500, "utterances_v3.json missing")
    job = {"id": uuid.uuid4().hex[:8], "kind": "prepare", "state": "running",
           "started": now_iso(), "out": str(out_dir.relative_to(ROOT)),
           "langs": list(langs), "log": ""}
    with _lock:
        _jobs[job["id"]] = job

    def work():
        try:
            from src.tts_engine import TTSEngine
            engines: dict[str, TTSEngine] = {}

            def synth(lang, text):
                if lang not in engines:
                    engines[lang] = TTSEngine(lang)
                e = engines[lang]
                return e.synthesize(text), e.sample_rate

            utterances = read_json(utter)
            report = prepare_mod.build_package(utterances, synth, out_dir,
                                               seed=seed, repeats=repeats, langs=langs)
            job["state"] = "done" if not report["failures"] else "partial"
            job["report"] = report
        except Exception as exc:  # noqa: BLE001
            job["state"] = "error"
            job["error"] = str(exc)[:400]
        job["finished"] = now_iso()

    threading.Thread(target=work, daemon=True).start()
    return {"job": job["id"], "out": job["out"]}


# --------------------------------------------------------------------------
# benchmark jobs (bounded, local-only, new timestamped run dirs)
# --------------------------------------------------------------------------

@app.post("/api/benchmarks/run")
def benchmark_run(payload: dict):
    langs = (payload or {}).get("langs") or list(LANGS)
    langs = [l for l in langs if l in LANGS]
    if not langs:
        raise HTTPException(400, "no valid languages")
    repeats = max(1, min(5, int((payload or {}).get("repeats", 2))))
    sentences = max(1, min(5, int((payload or {}).get("sentences", 3))))
    with _lock:
        if any(j["kind"] == "benchmark" and j["state"] == "running" for j in _jobs.values()):
            raise HTTPException(409, "a benchmark job is already running")
    job = {"id": uuid.uuid4().hex[:8], "kind": "benchmark", "state": "running",
           "started": now_iso(), "langs": langs, "repeats": repeats,
           "sentences": sentences, "log": ""}
    with _lock:
        _jobs[job["id"]] = job

    def work():
        cmd = [PY, str(ROOT / "eval" / "speak_check.py"),
               "--langs", ",".join(langs), "--repeats", str(repeats),
               "--sentences", str(sentences), "--no-zip"]
        try:
            proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True,
                                  text=True, encoding="utf-8", errors="replace",
                                  timeout=1800,
                                  env={**__import__("os").environ,
                                       "PYTHONIOENCODING": "utf-8"})
            job["log"] = (proc.stdout or "")[-4000:] + (proc.stderr or "")[-2000:]
            job["state"] = "done" if proc.returncode == 0 else "error"
            job["returncode"] = proc.returncode
        except subprocess.TimeoutExpired:
            job["state"] = "error"
            job["error"] = "timeout after 30 min"
        except Exception as exc:  # noqa: BLE001
            job["state"] = "error"
            job["error"] = str(exc)[:400]
        job["finished"] = now_iso()

    threading.Thread(target=work, daemon=True).start()
    return {"job": job["id"]}


@app.get("/api/jobs")
def jobs():
    with _lock:
        return {"jobs": sorted(_jobs.values(), key=lambda j: j["started"],
                               reverse=True)}


# --------------------------------------------------------------------------
# resources
# --------------------------------------------------------------------------

def process_rss_mb() -> float | None:
    try:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]

        h = ctypes.windll.kernel32.GetCurrentProcess()
        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        if ctypes.windll.kernel32.K32GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb):
            return round(pmc.WorkingSetSize / 1048576.0, 1)
    except Exception:  # noqa: BLE001
        return None
    return None


@app.get("/api/resources")
def resources():
    import os
    hist = {}
    cap = ROOT / "benchmarks" / "results" / "realworld_v2"
    for name in ("capacity_v2.json", "concurrency_v2.json"):
        p = cap / name
        if p.exists():
            d = read_json(p)
            hist[name] = {k: d[k] for k in list(d)[:8]}
    return {
        "console_rss_mb": process_rss_mb(),
        "cpu_logical": os.cpu_count(),
        "stt_threads": config.STT_NUM_THREADS,
        "tts_threads": getattr(config, "TTS_NUM_THREADS", 0),
        "historical": hist,
        "note": "Live pipeline RSS/CPU belong to the port-8000 process, which this console never touches.",
    }


# --------------------------------------------------------------------------
# final report generator (14 sections, strict status vocabulary)
# --------------------------------------------------------------------------

@app.post("/api/reports/generate")
def report_generate():
    ov = overview()
    langs = languages()["languages"]
    ds = dataset_summary()
    ls = listening_status()
    run = ov["latest_run"]
    rows = run_results(run["run"])["languages"] if run else []
    bl = baselines()
    base = read_json(HQ_RESULTS / "baseline" / bl[-1]["run"] / "baseline.json") if bl else {}
    ts = stamp()
    out = HQ_RESULTS / "reports" / ts
    out.mkdir(parents=True, exist_ok=True)

    listening_reports = {}
    for pkg in ls["packages"]:
        p = package_dir(pkg["id"])
        smap = read_json(p / "private" / "sample_map.json")
        resps = [read_json(f) for f in sorted(RESPONSES.glob(f"{pkg['id']}_*.json"))] \
            if RESPONSES.exists() else []
        listening_reports[pkg["id"]] = score_mod.build_report(smap, resps)

    L = []
    A = L.append
    A(f"# IndicVoice human voice-quality — final report ({ts})")
    A("")
    A("Status vocabulary: PASS (automated) / PASS — manually verified / PARTIAL / FAIL / NOT TESTED / NOT APPLICABLE.")
    A("")
    A("## 1. Overall language quality matrix")
    A("")
    A("| lang | round-trip | clean/n | CER clean mean | human naturalness | production readiness |")
    A("|---|---|---|---|---|---|")
    for l in langs:
        m = l["metrics"]
        A(f"| {l['lang']} | {l['status']} | {m.get('clean_renders')}/{m.get('n')} | "
          f"{m.get('cer_clean_mean')} | NOT TESTED | NOT TESTED — no human evidence |")
    A("")
    A("## 2. ASR results (synthetic round-trip, local only)")
    A("")
    for r in rows:
        A(f"- {r['lang']}: backend {r['asr_backend']}, CER clean mean {r['cer_clean_mean']}, "
          f"worst {r['cer_clean_max']}, word-miss renders {r['word_miss_renders']}.")
    if not rows:
        A("- NOT TESTED — no speak-check run available.")
    A("")
    A("## 3. TTS results")
    A("")
    for r in rows:
        A(f"- {r['lang']}: backend {r['tts_backend']}, {r['n']} renders, "
          f"audible_all={r['audible_all']}, mean duration {r['duration_mean_s']} s, "
          f"render RTF {r['render_rtf_mean']}.")
    A("")
    A("## 4. Pronunciation defects (measured candidates, not native-speaker verdicts)")
    A("")
    any_def = False
    for l in langs:
        for d in l["defects"]:
            any_def = True
            A(f"- {l['lang']} s{d['sentence']} take {d['take']}: "
              f"«{d['reference']}» → «{d['hypothesis']}» (CER clean {d['cer_clean']}). "
              + "; ".join(d["notes"]))
    if not any_def:
        A("- None measured in the latest run.")
    A("")
    A("## 5. Prosody and naturalness defects")
    A("")
    A("- NOT TESTED — no human prosody ratings exist. Automated signal gates "
      "(audibility, clipping, voice-band coverage) are not naturalness measurements.")
    A("")
    A("## 6. Human evaluation results")
    A("")
    A(f"- HUMAN DATASET: {ds['human_dataset_status']} ({ds['collected']}/{ds['total_slots']} slots collected, "
      f"{ds['verified']} transcripts independently verified).")
    A(f"- Listening responses: {ls['n_response_files']} files, {ls['n_listeners']} listeners → {ls['status']}.")
    A("")
    A("## 7. MOS")
    A("")
    A("- NOT TESTED. No ITU-T MOS protocol has been run. Listener means, when collected, "
      "are labelled 'mean listener rating', never MOS.")
    A("")
    A("## 8. Provider and voice comparison")
    A("")
    A("| lang | selected TTS | tiny | MMS fallback | supertonic eligible | local ASR |")
    A("|---|---|---|---|---|---|")
    mm = base.get("language_model_matrix") or {}
    for lang, m in mm.items():
        A(f"| {lang} | {m.get('tts_backend_selected')} | {m.get('tiny_model_present')} | "
          f"{m.get('mms_model_present')} | {m.get('supertonic_eligible')} | "
          f"{m.get('asr_local_dir')}{' (' + str(m.get('asr_alias_of')) + ' alias)' if m.get('asr_alias_of') else ''} |")
    A("")
    A("Selection is unchanged from the frozen V2 configuration; no provider was swapped "
      "without measured evidence.")
    A("")
    A("## 9. Latency comparison")
    A("")
    for r in rows:
        A(f"- {r['lang']}: render RTF mean {r['render_rtf_mean']} (render time / audio duration).")
    A("- End-to-end conversational latency: see historical realworld_v2 artifacts; "
      "not re-measured against the live port-8000 process by this console.")
    A("")
    A("## 10. CPU and RAM")
    A("")
    A(f"- Console process RSS: {process_rss_mb()} MB · logical CPUs: {__import__('os').cpu_count()}.")
    A(f"- Configured STT threads: {config.STT_NUM_THREADS}; TTS threads knob: "
      f"{getattr(config, 'TTS_NUM_THREADS', 0)} (0 = ORT default).")
    A("- Historical capacity evidence: benchmarks/results/realworld_v2 (read-only).")
    A("")
    A("## 11. Regression tests")
    A("")
    t = base.get("automated_tests") or {}
    A(f"- {t.get('status', 'NOT TESTED')} — {t.get('tests_run', '?')} tests, "
      f"{t.get('skipped', '?')} skipped (log: {t.get('log', 'n/a')}).")
    A("")
    A("## 12. Known limitations")
    A("")
    for n in (base.get("known_defects") or [
        "Malayalam എന്റെ heard as എറെ in 3/3 takes (repeatable pronunciation candidate).",
        "Hindi: 1/9 renders decoded to a single character by the Conformer (decode instability).",
        "Assamese round-trip confounded by the Bengali Conformer alias.",
        "English local whisper digit formatting inflates raw CER (digit-expanded CER 0.000).",
        "Synthesis is non-deterministic across takes.",
    ]):
        A(f"- {n}")
    A("- Assamese ASR uses the Bengali Conformer alias; round-trip CER is confounded.")
    A("- Synthesis is non-deterministic; single-render claims are invalid.")
    A("")
    A("## 13. Recommended next improvements")
    A("")
    A("1. Collect the 240-slot human dataset with consented native speakers (≥5/language).")
    A("2. Run blind listening sessions with the prepared packages; score with score_responses.")
    A("3. Native-speaker review of the Malayalam എന്റെ pronunciation candidate.")
    A("4. Investigate the Hindi Conformer single-character decode collapse.")
    A("5. Export a dedicated Assamese ASR model to remove the Bengali alias confound.")
    A("")
    A("## 14. Production readiness by language")
    A("")
    for l in langs:
        A(f"- {l['lang']} ({l['name']}): automated speech generation "
          f"{'verified' if l['status'].startswith('PASS') else 'partially verified'}; "
          "pronunciation partially validated; human naturalness NOT TESTED; "
          "production-ready NOT TESTED.")
    A("")
    A("No language is marked production-ready: that claim requires human evidence "
      "which does not yet exist.")

    md = "\n".join(L) + "\n"
    (out / "final_report.md").write_text(md, encoding="utf-8")
    payload = {"generated": now_iso(), "run": ts, "overview": ov,
               "languages": langs, "dataset": ds, "listening": listening_reports,
               "resources": resources()}
    (out / "final_report.json").write_text(json.dumps(payload, indent=2,
                                                      ensure_ascii=False), encoding="utf-8")
    return {"run": ts, "dir": str(out.relative_to(ROOT)),
            "markdown": md}


@app.get("/api/reports")
def reports():
    rdir = HQ_RESULTS / "reports"
    out = []
    if rdir.exists():
        for p in sorted(rdir.iterdir()):
            if p.is_dir() and (p / "final_report.md").exists():
                out.append({"run": p.name})
    return {"reports": out}


@app.get("/api/reports/{name}")
def report_detail(name: str):
    if "/" in name or ".." in name:
        raise HTTPException(400, "bad name")
    p = HQ_RESULTS / "reports" / name
    if not (p / "final_report.md").exists():
        raise HTTPException(404, "report not found")
    return {"run": name,
            "markdown": (p / "final_report.md").read_text(encoding="utf-8"),
            "data": read_json(p / "final_report.json")}


# --------------------------------------------------------------------------
# static console
# --------------------------------------------------------------------------

@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/assets", StaticFiles(directory=WEB), name="assets")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8010)
    args = ap.parse_args()
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", args.port))
        except OSError:
            print(f"port {args.port} is occupied by another process; refusing to bind.",
                  file=sys.stderr)
            return 1
    print(f"quality console → http://127.0.0.1:{args.port}/  (port 8000 untouched)")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())