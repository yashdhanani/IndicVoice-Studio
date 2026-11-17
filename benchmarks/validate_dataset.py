"""Validate the Production Hardening V1 evaluation dataset (Phase D).

Checks every manifest entry against the schema, verifies that COLLECTED
entries point at real 16 kHz mono PCM16 WAV files with a reference text and
recorded consent, and reports per-language completeness. NOT_COLLECTED slots
are reported as missing -- this tool never creates audio or reference text.

Usage:
    python benchmarks/validate_dataset.py
    python benchmarks/validate_dataset.py --manifest evaluation/dataset_manifest.jsonl
    python benchmarks/validate_dataset.py --require-complete   # gate: all 240 collected
    python benchmarks/validate_dataset.py --out benchmarks/results/production_v1/dataset_validation.json

Exit codes: 0 = all present entries valid; 1 = invalid entries; 2 = incomplete
with --require-complete.
"""
from __future__ import annotations

import argparse
import json
import sys
import wave
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LANGS = ("hi", "bn", "ta", "te", "kn", "ml", "mr", "gu", "pa", "or", "as", "en")
STATUSES = ("NOT_COLLECTED", "COLLECTED", "REJECTED")
NOISE = ("clean", "office", "street")
DEVICES = ("phone", "laptop", "headset", "other")
REQUIRED_KEYS = (
    "id", "lang", "audio_path", "status", "reference_text", "speaker_id",
    "consent", "noise_condition", "device", "duration_s", "domain",
    "collected_at",
)
TARGET_PER_LANG = 20


def validate_entry(entry: dict, root: Path) -> list[str]:
    problems = []
    for key in REQUIRED_KEYS:
        if key not in entry:
            problems.append(f"missing key '{key}'")
    if problems:
        return problems

    if entry["lang"] not in LANGS:
        problems.append(f"unknown lang '{entry['lang']}'")
    if entry["status"] not in STATUSES:
        problems.append(f"unknown status '{entry['status']}'")
    if entry["noise_condition"] not in NOISE:
        problems.append(f"unknown noise_condition '{entry['noise_condition']}'")

    status = entry["status"]
    if status == "NOT_COLLECTED":
        if entry["reference_text"] is not None:
            problems.append("NOT_COLLECTED entry must not carry a reference_text")
        if (root / entry["audio_path"]).exists():
            problems.append("audio file exists but status is NOT_COLLECTED")
        return problems

    if status == "REJECTED":
        if not entry.get("notes"):
            problems.append("REJECTED entry needs notes explaining why")
        return problems

    # COLLECTED: everything below must be real, verified data
    if not isinstance(entry["reference_text"], str) or not entry["reference_text"].strip():
        problems.append("COLLECTED entry needs a non-empty reference_text")
    if entry["consent"] is not True:
        problems.append("COLLECTED entry needs consent=true (recorded speaker permission)")
    if not entry["speaker_id"]:
        problems.append("COLLECTED entry needs a pseudonymous speaker_id")
    if entry["device"] not in DEVICES:
        problems.append(f"COLLECTED entry needs device in {DEVICES}")
    try:
        date.fromisoformat(str(entry["collected_at"]))
    except (ValueError, TypeError):
        problems.append("collected_at must be an ISO date (YYYY-MM-DD)")
    # V2 metadata fields (optional for pre-V2 entries, checked when present)
    if entry.get("sample_rate") is not None and entry["sample_rate"] != 16000:
        problems.append("sample_rate metadata must be 16000 for canonical audio")
    if entry.get("transcript_verified") is not None and not isinstance(entry["transcript_verified"], bool):
        problems.append("transcript_verified must be a boolean")
    if entry.get("transcript_verified") is True and not entry.get("transcript_verified_by"):
        problems.append("transcript_verified=true needs a pseudonymous transcript_verified_by")

    path = root / entry["audio_path"]
    if not path.exists():
        problems.append(f"audio file missing: {entry['audio_path']}")
        return problems
    try:
        with wave.open(str(path), "rb") as wav:
            channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
            frames = wav.getnframes()
        if channels != 1:
            problems.append(f"audio must be mono (got {channels} channels)")
        if width != 2:
            problems.append(f"audio must be PCM16 (got sample width {width})")
        if rate != 16000:
            problems.append(f"audio must be 16 kHz (got {rate})")
        duration = frames / float(rate)
        if not 0.5 <= duration <= 60.0:
            problems.append(f"duration {duration:.2f}s outside 0.5-60 s")
        if entry["duration_s"] is not None and abs(entry["duration_s"] - duration) > 0.1:
            problems.append("duration_s disagrees with the WAV header")
    except (wave.Error, EOFError) as exc:
        problems.append(f"unreadable WAV: {exc}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest",
                        default=str(ROOT / "evaluation" / "dataset_manifest.jsonl"))
    parser.add_argument("--require-complete", action="store_true",
                        help="exit 2 unless every slot is COLLECTED and valid")
    parser.add_argument("--out", default=None, help="write the JSON report here")
    args = parser.parse_args(argv)

    entries = []
    for lineno, line in enumerate(Path(args.manifest).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except ValueError as exc:
            print(f"line {lineno}: invalid JSON: {exc}")
            return 1

    seen, invalid = set(), []
    per_lang = {lang: {"target": TARGET_PER_LANG, "collected": 0,
                       "not_collected": 0, "rejected": 0, "speakers": set()}
                for lang in LANGS}
    for entry in entries:
        eid = entry.get("id", "<no id>")
        if eid in seen:
            invalid.append({"id": eid, "problems": ["duplicate id"]})
        seen.add(eid)
        problems = validate_entry(entry, ROOT)
        if problems:
            invalid.append({"id": eid, "problems": problems})
        lang = entry.get("lang")
        if lang in per_lang:
            status = entry.get("status")
            if status == "COLLECTED" and not problems:
                per_lang[lang]["collected"] += 1
                per_lang[lang]["speakers"].add(entry.get("speaker_id"))
            elif status == "REJECTED":
                per_lang[lang]["rejected"] += 1
            else:
                per_lang[lang]["not_collected"] += 1

    collected = sum(v["collected"] for v in per_lang.values())
    report = {
        "manifest": str(Path(args.manifest)),
        "total_slots": len(entries),
        "target_total": TARGET_PER_LANG * len(LANGS),
        "collected": collected,
        "invalid_entries": invalid,
        "per_lang": {
            lang: {**{k: v for k, v in stats.items() if k != "speakers"},
                   "distinct_speakers": len(stats["speakers"])}
            for lang, stats in per_lang.items()
        },
        "complete": collected == TARGET_PER_LANG * len(LANGS) and not invalid,
    }
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"dataset: {collected}/{report['target_total']} collected, "
          f"{len(invalid)} invalid entries")
    for lang, stats in report["per_lang"].items():
        print(f"  {lang}: {stats['collected']}/{stats['target']} collected, "
              f"{stats['distinct_speakers']} speakers, {stats['rejected']} rejected")
    for item in invalid:
        print(f"  INVALID {item['id']}: {'; '.join(item['problems'])}")
    if invalid:
        return 1
    if args.require_complete and not report["complete"]:
        print("NOT COMPLETE: remaining slots are NOT_COLLECTED (no audio fabricated)")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())