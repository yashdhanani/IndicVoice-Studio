"""Report actual evaluation-dataset status (V2 Phase B).

Reads the manifest, re-validates every entry with validate_dataset, and
reports ACTUAL counts: collected per language, speaker diversity, noise and
domain coverage, duration statistics, transcript-verification progress.
Never estimates, never pads, never counts synthetic audio as real.

Usage:
    python benchmarks/dataset_report.py
    python benchmarks/dataset_report.py --out benchmarks/results/realworld_v2/dataset_report_v2.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "benchmarks"))
from validate_dataset import LANGS, TARGET_PER_LANG, validate_entry  # noqa: E402


def build_report(manifest: Path, root: Path) -> dict:
    entries = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()
               if line.strip()]
    per_lang = {}
    invalid = []
    for lang in LANGS:
        rows = [e for e in entries if e.get("lang") == lang]
        collected = [e for e in rows if e.get("status") == "COLLECTED"]
        durations = [e["duration_s"] for e in collected if e.get("duration_s")]
        noise: dict[str, int] = {}
        domains: dict[str, int] = {}
        for e in collected:
            noise[e.get("noise_condition", "?")] = noise.get(e.get("noise_condition", "?"), 0) + 1
            domains[e.get("domain", "?")] = domains.get(e.get("domain", "?"), 0) + 1
        per_lang[lang] = {
            "target": TARGET_PER_LANG,
            "collected": len(collected),
            "rejected": sum(1 for e in rows if e.get("status") == "REJECTED"),
            "not_collected": sum(1 for e in rows if e.get("status") == "NOT_COLLECTED"),
            "distinct_speakers": len({e.get("speaker_id") for e in collected}),
            "speaker_target": 5,
            "transcript_verified": sum(1 for e in collected if e.get("transcript_verified") is True),
            "noise_coverage": noise,
            "domain_coverage": domains,
            "duration_s": {
                "min": round(min(durations), 2) if durations else None,
                "p50": round(statistics.median(durations), 2) if durations else None,
                "max": round(max(durations), 2) if durations else None,
            },
        }
    for e in entries:
        problems = validate_entry(e, root)
        if problems:
            invalid.append({"id": e.get("id"), "problems": problems})
    collected_total = sum(v["collected"] for v in per_lang.values())
    return {
        "manifest": str(manifest),
        "target_total": TARGET_PER_LANG * len(LANGS),
        "collected_total": collected_total,
        "complete": collected_total == TARGET_PER_LANG * len(LANGS) and not invalid,
        "invalid_entries": invalid,
        "per_lang": per_lang,
        "note": "Actual counts only. NOT_COLLECTED slots are never filled with synthetic audio.",
    }


def render_markdown(report: dict) -> str:
    lines = ["# Evaluation dataset status (actual counts)", "",
             f"Collected: **{report['collected_total']} / {report['target_total']}**", "",
             "| lang | collected | speakers (target 5) | verified transcripts | noise coverage | duration p50 s |",
             "|---|---|---|---|---|---|"]
    for lang, v in report["per_lang"].items():
        noise = ", ".join(f"{k}:{n}" for k, n in sorted(v["noise_coverage"].items())) or "—"
        lines.append(f"| {lang} | {v['collected']}/{v['target']} | {v['distinct_speakers']} | "
                     f"{v['transcript_verified']} | {noise} | {v['duration_s']['p50'] or '—'} |")
    if report["invalid_entries"]:
        lines += ["", "## Invalid entries", ""]
        for item in report["invalid_entries"]:
            lines.append(f"- {item['id']}: {'; '.join(item['problems'])}")
    lines += ["", "No synthetic or placeholder audio is counted. Missing slots stay NOT_COLLECTED."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", default=str(ROOT / "evaluation" / "dataset_manifest.jsonl"))
    parser.add_argument("--out", default=None, help="JSON report path (.md written alongside)")
    args = parser.parse_args(argv)
    report = build_report(Path(args.manifest), ROOT)
    md = render_markdown(report)
    print(md)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        out.with_suffix(".md").write_text(md, encoding="utf-8")
        print(f"report -> {out}")
    return 1 if report["invalid_entries"] else 0


if __name__ == "__main__":
    sys.exit(main())