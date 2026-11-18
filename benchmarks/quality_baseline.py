"""Phase 0 baseline audit for the human voice-quality project.

Read-only inventory of the repository, providers, language configuration,
historical benchmarks and the current automated test result, written to a NEW
timestamped directory under benchmarks/results/human_voice_quality/baseline/.
Historical V1/V2 results are read, never modified. The live server on port 8000
is probed as a client only; it is never restarted or reconfigured.

Usage:
    .venv313/Scripts/python.exe benchmarks/quality_baseline.py
    .venv313/Scripts/python.exe benchmarks/quality_baseline.py --tests-log eval/_regression_now.log
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402

LANGS = ["hi", "gu", "mr", "bn", "ta", "te", "kn", "ml", "pa", "or", "as", "en"]
HVQ = ROOT / "benchmarks" / "results" / "human_voice_quality"


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                              text=True, timeout=20).stdout.strip()
    except Exception as exc:
        return f"unavailable: {exc}"


def probe(path: str) -> dict:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000" + path, timeout=4) as r:
            body = r.read(4000).decode("utf-8", "replace")
            return {"status": r.status, "body": json.loads(body) if body.startswith("{") else body[:400]}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "body": exc.read(200).decode("utf-8", "replace")}
    except Exception as exc:
        return {"status": None, "error": str(exc)}


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def model_matrix() -> dict:
    rows = {}
    for lang in LANGS:
        tiny = config.MODELS_DIR / f"tiny-{lang}"
        mms = config.MODELS_DIR / f"tts-{lang}" / "model.onnx"
        asr = config.indic_asr_dir(lang) if config.has_indic_asr(lang) else None
        rows[lang] = {
            "tts_backend_selected": config.tts_backend(lang),
            "tiny_model_present": tiny.is_dir(),
            "mms_model_present": mms.exists(),
            "supertonic_eligible": lang in config.SUPERTONIC_LANGS,
            "asr_local_dir": asr.name if asr else None,
            "asr_present": bool(asr and asr.is_dir()),
            "asr_alias_of": config.INDIC_ASR.get(lang, {}).get("alias_of"),
            "stt_default_backend": config.STT_BACKEND_BY_LANG.get(lang, "auto"),
            "endpoint_silence_s": config.endpoint_for(lang),
        }
    return rows


def inventory() -> dict:
    def listing(rel: str, pattern: str = "*") -> list[str]:
        folder = ROOT / rel
        return sorted(p.name for p in folder.glob(pattern)) if folder.is_dir() else []

    manifest = [json.loads(line) for line in
                (ROOT / "evaluation" / "dataset_manifest.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    statuses: dict[str, int] = {}
    for entry in manifest:
        statuses[entry["status"]] = statuses.get(entry["status"], 0) + 1
    pkg = load_json(ROOT / "evaluation" / "human_voice_quality" / "package.json") or {}
    responses = ROOT / "evaluation" / "human_voice_quality" / "responses"
    return {
        "src_modules": listing("src", "*.py"),
        "tests": listing("tests", "test_*.py"),
        "benchmark_harnesses": listing("benchmarks", "*.py"),
        "docs": listing("docs", "*.md"),
        "web_assets": listing("web"),
        "models_dirs": listing("models"),
        "dataset_slots": len(manifest),
        "dataset_status_counts": statuses,
        "listening_package_samples": pkg.get("n_samples", 0),
        "listening_dimensions": pkg.get("dimensions", []),
        "listener_responses_on_disk": len(list(responses.glob("*.json"))) if responses.is_dir() else 0,
        "historical_result_trees": listing("benchmarks/results"),
    }


def historical() -> dict:
    out = {}
    v1 = ROOT / "benchmarks" / "results" / "production_v1"
    v2 = ROOT / "benchmarks" / "results" / "realworld_v2"
    for name, folder in (("v1", v1), ("v2", v2)):
        files = {}
        for path in sorted(folder.glob("*.json")):
            data = load_json(path)
            if data is None:
                continue
            if isinstance(data, dict):
                files[path.name] = {k: data[k] for k in list(data)[:8]}
            else:
                files[path.name] = {"entries": len(data)}
        out[name] = files
    score = load_json(v2 / "final_scorecard_v2.json") or {}
    out["v2_scorecard"] = score.get("scorecard", [])
    out["v2_verdict"] = score.get("verdict")
    out["v2_not_tested"] = score.get("not_tested")
    return out


def speak_evidence() -> dict:
    runs = sorted(p for p in (ROOT / "eval").glob("speak_check_*") if p.is_dir())
    out = []
    for run in runs:
        data = load_json(run / "results.json")
        if not data:
            continue
        out.append({
            "run": run.name,
            "generated": data.get("generated"),
            "repeats": data.get("repeats_per_sentence", 1),
            "languages": [{k: r.get(k) for k in
                           ("lang", "n", "status", "cer_clean_mean", "cer_clean_max",
                            "clean_renders", "word_miss_renders", "audible_all",
                            "tts_backend", "asr_backend", "render_rtf_mean")}
                          for r in data.get("languages", [])],
        })
    return {"runs": out}


def tests_result(log: Path | None) -> dict:
    if log is None or not log.exists():
        return {"status": "NOT TESTED", "note": "no regression log supplied yet"}
    text = log.read_text(encoding="utf-8", errors="replace")
    ran = re.search(r"Ran (\d+) tests?", text)
    ok = re.search(r"^OK", text, re.M)
    failed = re.search(r"FAILED \(([^)]*)\)", text)
    skips = len(re.findall(r"\.\.\. skipped", text))
    return {
        "status": "PASS (automated)" if ok and not failed else "FAIL" if failed else "PARTIAL",
        "tests_run": int(ran.group(1)) if ran else None,
        "skipped": skips,
        "failure_summary": failed.group(1) if failed else None,
        "log": str(log.relative_to(ROOT)) if log.is_relative_to(ROOT) else str(log),
        "tail": text.strip().splitlines()[-6:],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 0 baseline audit (read-only)")
    parser.add_argument("--tests-log", default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = Path(args.out) if args.out else HVQ / "baseline" / stamp
    if out.exists() and any(out.iterdir()):
        print(f"refusing to write into non-empty {out}", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)

    health = probe("/health")
    metrics = probe("/metrics")
    payload = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "phase": "0 — baseline audit",
        "git": {"head": git("rev-parse", "HEAD"), "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
                "status_short": git("status", "--short").splitlines(),
                "recent": git("log", "--oneline", "-6").splitlines()},
        "inventory": inventory(),
        "language_model_matrix": model_matrix(),
        "providers": {
            "tts": {"preferred": "Indic Tiny (Matcha+Vocos)", "fallbacks": ["supertonic-3-int8", "mms-vits"],
                    "tiny_speed": config.TINY_SPEED, "tiny_target_rms": config.TINY_TARGET_RMS,
                    "supertonic_available": config.supertonic_available(),
                    "supertonic_langs": sorted(config.SUPERTONIC_LANGS)},
            "asr": {"local_indic_conformer_langs": sorted(config.INDIC_ASR),
                    "local_whisper_models": sorted(config.STT_MODELS),
                    "cloud_groq_langs": sorted(config.GROQ_STT_LANGS),
                    "cloud_routing_by_lang": dict(config.STT_BACKEND_BY_LANG),
                    "stt_mode": config.STT_MODE},
            "llm": {"primary_model": config.LLM_PRIMARY_MODEL,
                    "reasoning_effort": config.LLM_REASONING_EFFORT,
                    "note": "cloud Groq by default; Ollama/OpenAI-compatible supported; not exercised by this audit"},
        },
        "live_server_probe": {
            "port": 8000, "health": health, "metrics": metrics,
            "note": ("running process predates HEAD: /metrics exists in source but returns 404 live"
                     if metrics.get("status") == 404 and health.get("status") == 200 else
                     "live process matches source routes probed"),
            "ownership": "user-owned pre-existing process; never restarted or rebound by this audit",
        },
        "historical_benchmarks": historical(),
        "speak_check_evidence": speak_evidence(),
        "automated_tests": tests_result(Path(args.tests_log) if args.tests_log else None),
        "safety": {
            "historical_results_modified": False,
            "port_8000_process_touched": False,
            "cloud_inference_used": False,
            "env_file_read": False,
        },
    }
    (out / "baseline.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    inv = payload["inventory"]
    lines = [
        "# Phase 0 baseline audit — IndicVoice human voice-quality project",
        "",
        f"Generated {payload['generated']} · HEAD `{payload['git']['head'][:9]}` "
        f"({payload['git']['branch']}) · read-only audit, new directory `{out.relative_to(ROOT)}`",
        "",
        "## Repository inventory",
        "",
        f"* src modules: {len(inv['src_modules'])} · tests: {len(inv['tests'])} · "
        f"benchmark harnesses: {len(inv['benchmark_harnesses'])} · docs: {len(inv['docs'])}",
        f"* dataset slots: {inv['dataset_slots']} ({inv['dataset_status_counts']})",
        f"* blind listening package: {inv['listening_package_samples']} samples, "
        f"{len(inv['listening_dimensions'])} dimensions; listener responses on disk: "
        f"{inv['listener_responses_on_disk']}",
        f"* historical result trees: {', '.join(inv['historical_result_trees'])}",
        "",
        "## Working tree at audit time",
        "",
        "```", *payload["git"]["status_short"][:20], "```",
        "",
        "## Providers and language configuration",
        "",
        "| lang | TTS selected | tiny | mms | supertonic eligible | local ASR | endpoint s |",
        "|---|---|---|---|---|---|---|",
    ]
    for lang, row in payload["language_model_matrix"].items():
        lines.append(f"| {lang} | {row['tts_backend_selected']} | {'yes' if row['tiny_model_present'] else 'NO'} | "
                     f"{'yes' if row['mms_model_present'] else 'no'} | {'yes' if row['supertonic_eligible'] else 'no'} | "
                     f"{row['asr_local_dir'] or 'whisper'}{' (bn alias)' if row['asr_alias_of'] else ''} | "
                     f"{row['endpoint_silence_s']} |")
    lines += [
        "",
        f"LLM primary: `{payload['providers']['llm']['primary_model']}` "
        f"(reasoning {payload['providers']['llm']['reasoning_effort']}); not exercised here.",
        "",
        "## Live server (client-side probe only)",
        "",
        f"* /health → {health.get('status')} · /metrics → {metrics.get('status')}",
        f"* {payload['live_server_probe']['note']}",
        "",
        "## Automated tests (current run)",
        "",
        f"* status: {payload['automated_tests']['status']} · "
        f"tests run: {payload['automated_tests'].get('tests_run')} · "
        f"skipped: {payload['automated_tests'].get('skipped')}",
        "",
        "## Latest speak-check evidence (synthetic round-trip, not human)",
        "",
    ]
    runs = payload["speak_check_evidence"]["runs"]
    if runs:
        latest = runs[-1]
        lines.append(f"Run `{latest['run']}` ({latest['repeats']} takes/sentence):")
        lines.append("")
        lines.append("| lang | renders | clean | CER clean mean | worst | status |")
        lines.append("|---|---|---|---|---|---|")
        for r in latest["languages"]:
            lines.append(f"| {r['lang']} | {r['n']} | {r['clean_renders']} | "
                         f"{r['cer_clean_mean']} | {r['cer_clean_max']} | {r['status']} |")
    lines += [
        "",
        "## Known defects carried into this project",
        "",
        "* Malayalam `എന്റെ` heard as `എറെ` in 3/3 takes (repeatable pronunciation candidate).",
        "* Hindi: 1/9 renders decoded to a single character by the production Conformer while a "
        "second recogniser heard the full sentence (decode instability, audio healthy).",
        "* Assamese round-trip confounded: decoded by the Bengali Conformer (no Assamese export).",
        "* English local whisper writes digits ('1-2-3'); digit-expanded CER 0.000 (formatting, not speech).",
        "* Synthesis is non-deterministic: identical text renders different audio each take.",
        "* Human dataset: 0/240 collected. MOS / mean listener ratings: NOT TESTED.",
        "",
        "## Safety attestation",
        "",
        "* Historical V1/V2 results read only; nothing overwritten.",
        "* Port 8000 process untouched; probed as a client.",
        "* No cloud inference, no paid API, `.env` never read.",
        "",
    ]
    (out / "baseline.md").write_text("\n".join(lines), encoding="utf-8")
    if args.tests_log and Path(args.tests_log).exists():
        (out / "regression.log").write_text(Path(args.tests_log).read_text(encoding="utf-8", errors="replace"),
                                            encoding="utf-8")
    print(f"baseline -> {out}")
    print("\n".join(lines[:14]))
    return 0


if __name__ == "__main__":
    sys.exit(main())