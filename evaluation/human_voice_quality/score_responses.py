"""Aggregate human listening responses for the V2 Phase E evaluation.

Reads listener response JSONs (from listening.html or the CSV form converted
to the same shape), joins them with the private sample map, and reports per
language and dimension: mean listener rating, sample standard deviation,
number of listeners, number of utterances, number of ratings, plus
repeated-sample consistency and qualitative feedback.

This is NOT an ITU-T MOS pipeline: no reference conditions, no controlled
listening lab, no listener screening per P.800. Outputs are labeled "mean
listener rating" and must never be reported as industry-standard MOS.

With zero responses the report says NOT TESTED and no numbers are invented.

Usage:
    .venv313/Scripts/python.exe evaluation/human_voice_quality/score_responses.py
    ... --responses evaluation/human_voice_quality/responses \
        --out benchmarks/results/realworld_v2/human_eval_v2.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

DIMENSIONS = (
    "pronunciation", "intelligibility", "naturalness", "prosody", "rhythm",
    "pauses", "sentence_endings", "question_intonation",
    "conversational_feel", "overall",
)


def load_responses(responses_dir: Path) -> list[dict]:
    out = []
    for path in sorted(responses_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["_file"] = path.name
        out.append(data)
    return out


def aggregate(sample_map: dict, responses: list[dict]) -> dict:
    """responses: [{listener_id, ratings: {code: {dim: 1..5}}, feedback: {code: str}}]"""
    per_lang: dict[str, dict] = {}
    consistency: dict[str, list] = {}
    feedback: dict[str, list] = {}
    problems: list[str] = []

    for resp in responses:
        listener = resp.get("listener_id") or resp.get("_file", "<unknown>")
        ratings = resp.get("ratings", {})
        for code, dims in ratings.items():
            info = sample_map.get(code)
            if info is None:
                problems.append(f"{listener}: unknown sample code {code}")
                continue
            lang = info["lang"]
            bucket = per_lang.setdefault(lang, {
                "listeners": set(), "utterances": set(),
                "dims": {d: [] for d in DIMENSIONS}})
            bucket["listeners"].add(listener)
            bucket["utterances"].add(info["utterance"])
            for dim, value in dims.items():
                if dim not in DIMENSIONS:
                    problems.append(f"{listener}/{code}: unknown dimension {dim}")
                    continue
                if not isinstance(value, (int, float)) or not 1 <= value <= 5:
                    problems.append(f"{listener}/{code}/{dim}: rating {value!r} outside 1-5")
                    continue
                bucket["dims"][dim].append(float(value))
            text = (resp.get("feedback") or {}).get(code)
            if text and text.strip():
                feedback.setdefault(lang, []).append(
                    {"listener": listener, "sample": code, "text": text.strip()})

    # repeated-sample consistency: |first - second| per dimension per listener
    for resp in responses:
        listener = resp.get("listener_id") or resp.get("_file", "<unknown>")
        ratings = resp.get("ratings", {})
        for code, info in sample_map.items():
            orig = info.get("repeat_of")
            if not orig or code not in ratings or orig not in ratings:
                continue
            deltas = {}
            for dim in DIMENSIONS:
                a, b = ratings[orig].get(dim), ratings[code].get(dim)
                if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                    deltas[dim] = abs(a - b)
            if deltas:
                consistency.setdefault(info["lang"], []).append(
                    {"listener": listener, "pair": [orig, code], "abs_delta": deltas})

    per_lang_out = {}
    for lang, bucket in sorted(per_lang.items()):
        dims_out = {}
        for dim, values in bucket["dims"].items():
            dims_out[dim] = {
                "mean": round(statistics.fmean(values), 3) if values else None,
                "sd": round(statistics.stdev(values), 3) if len(values) > 1 else None,
                "n_ratings": len(values),
            }
        cons = consistency.get(lang, [])
        all_deltas = [d for c in cons for d in c["abs_delta"].values()]
        per_lang_out[lang] = {
            "n_listeners": len(bucket["listeners"]),
            "n_utterances": len(bucket["utterances"]),
            "dimensions": dims_out,
            "repeat_consistency": {
                "n_pairs_rated": len(cons),
                "mean_abs_delta": round(statistics.fmean(all_deltas), 3) if all_deltas else None,
                "max_abs_delta": max(all_deltas) if all_deltas else None,
            },
        }

    return {
        "per_lang": per_lang_out,
        "qualitative_feedback": {k: v for k, v in sorted(feedback.items())},
        "problems": problems,
    }


def build_report(sample_map: dict, responses: list[dict]) -> dict:
    n_listeners = len({r.get("listener_id") or r.get("_file") for r in responses})
    report = {
        "program": "indicvoice_human_voice_quality_v2",
        "metric_label": "mean listener rating (5-point scale) — NOT ITU-T MOS",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "n_response_files": len(responses),
        "n_listeners": n_listeners,
        "status": "NOT TESTED" if not responses else "COLLECTED",
    }
    if not responses:
        report["note"] = ("No listener responses exist. No scores are reported. "
                          "Run listening sessions per docs/INDICVOICE_HUMAN_EVALUATION.md.")
        report["per_lang"] = {}
        return report
    report.update(aggregate(sample_map, responses))
    return report


def render_markdown(report: dict) -> str:
    lines = ["# Human voice-quality evaluation — V2", "",
             f"Status: **{report['status']}**  ",
             f"Metric: {report['metric_label']}  ",
             f"Listeners: {report['n_listeners']}  ",
             f"Recorded: {report['recorded_at']}", ""]
    if report["status"] == "NOT TESTED":
        lines.append(report["note"])
        return "\n".join(lines) + "\n"
    for lang, stats in report["per_lang"].items():
        lines.append(f"## {lang} — {stats['n_listeners']} listeners, "
                     f"{stats['n_utterances']} utterances")
        lines.append("")
        lines.append("| Dimension | Mean | SD | n ratings |")
        lines.append("|---|---|---|---|")
        for dim, d in stats["dimensions"].items():
            lines.append(f"| {dim} | {d['mean']} | {d['sd']} | {d['n_ratings']} |")
        rc = stats["repeat_consistency"]
        lines.append("")
        lines.append(f"Repeat consistency: {rc['n_pairs_rated']} pairs, "
                     f"mean |Δ| {rc['mean_abs_delta']}, max |Δ| {rc['max_abs_delta']}")
        lines.append("")
    if report.get("problems"):
        lines.append("## Data problems")
        lines.extend(f"- {p}" for p in report["problems"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--map", default=str(HERE / "private" / "sample_map.json"))
    parser.add_argument("--responses", default=str(HERE / "responses"))
    parser.add_argument("--out", default=str(
        ROOT / "benchmarks" / "results" / "realworld_v2" / "human_eval_v2.json"))
    args = parser.parse_args(argv)

    sample_map = json.loads(Path(args.map).read_text(encoding="utf-8"))
    responses_dir = Path(args.responses)
    responses = load_responses(responses_dir) if responses_dir.exists() else []
    report = build_report(sample_map, responses)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    out.with_suffix(".md").write_text(render_markdown(report), encoding="utf-8")
    print(f"status={report['status']} listeners={report['n_listeners']} → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())