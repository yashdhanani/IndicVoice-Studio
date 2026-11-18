"""Consolidate every measurement into one per-language defect matrix.

Reads the LATEST artifact of each existing harness and writes a new timestamped
directory under ``benchmarks/results/human_voice_quality/language_audits/``.
Nothing is overwritten, nothing is re-measured, no audio is generated here.

Sources (latest of each, all optional — a missing source is reported as such):
  eval/speak_check_*/results.json                          TTS render + ASR round trip
  eval/accuracy.json                                       ASR CER/WER, 12 languages
  benchmarks/results/human_voice_quality/conversational*/*  gender / code-switch / script
  eval/latency.json, benchmarks/results/realworld_v3/*.json latency, RSS
  evaluation/dataset_manifest.jsonl                        human dataset slots

The four claims the master brief asks for are kept separate and never merged:
``automated_speech_generation`` / ``pronunciation`` / ``human_naturalness`` /
``production_ready``. Human naturalness is NOT TESTED unless listener responses
exist on disk.
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LANGS = ["hi", "gu", "mr", "bn", "ta", "te", "kn", "ml", "pa", "or", "as", "en"]
LANG_NAMES = {
    "hi": "Hindi", "gu": "Gujarati", "mr": "Marathi", "bn": "Bengali",
    "ta": "Tamil", "te": "Telugu", "kn": "Kannada", "ml": "Malayalam",
    "pa": "Punjabi", "or": "Odia", "as": "Assamese", "en": "Indian English",
}
HVQ = ROOT / "benchmarks" / "results" / "human_voice_quality"


def load(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def newest(pattern: str):
    hits = sorted(glob.glob(str(ROOT / pattern)))
    return Path(hits[-1]) if hits else None


def speak_check() -> dict:
    """Round-trip evidence per language: newest run that covered that language.

    Runs are partial (``--langs hi,ta`` is common), so taking only the newest
    file hides eleven languages. Oldest-to-newest, later runs overwrite earlier
    ones per language.
    """
    out: dict = {}
    for path_str in sorted(glob.glob(str(ROOT / "eval/speak_check_*/results.json"))):
        path = Path(path_str)
        data = load(path)
        if not data:
            continue
        rows = data.get("languages")
        if isinstance(rows, list):
            rows = {row.get("lang"): row for row in rows if row.get("lang")}
        for lang, row in (rows or {}).items():
            if not row:
                continue
            out[lang] = {
                "source": str(path.relative_to(ROOT)),
                "tts_backend": row.get("tts_backend"),
                "asr_backend": row.get("asr_backend"),
                "cer_clean_mean": row.get("cer_clean_mean"),
                "clean_render_rate": row.get("clean_render_rate"),
                "clean_renders": row.get("clean_renders"),
                "renders": row.get("n"),
                "word_miss_renders": row.get("word_miss_renders"),
                "script_miss_renders": row.get("script_miss_renders"),
            }
    return out


def asr_accuracy() -> dict:
    """Corpus CER per language: newest file that measured that language.

    Runs are per-language as often as full-suite, so a single ``accuracy.json``
    goes stale for the language that was just re-measured.
    """
    paths = sorted(glob.glob(str(ROOT / "eval" / "accuracy*.json")),
                   key=lambda p: Path(p).stat().st_mtime)
    out: dict = {}
    for raw in paths:
        path = Path(raw)
        data = load(path)
        if not data:
            continue
        for lang, block in (data.get("languages") or {}).items():
            acc = (block or {}).get("accuracy") or {}
            if acc.get("n"):
                out[lang] = {"cer": acc.get("cer"), "wer": acc.get("wer"),
                             "backend": acc.get("backend"), "n": acc.get("n"),
                             "source": str(path.relative_to(ROOT))}
    return out


def conversational() -> dict:
    path = newest("benchmarks/results/human_voice_quality/conversational_postfix/*/report.json")
    data = load(path) if path else None
    if not data:
        return {}
    out = {}
    for item in data.get("languages") or []:
        if "error" in item:
            out[item["lang"]] = {"error": item["error"]}
            continue
        gender = item.get("gender") or {}
        # Re-score code-switching from the stored replies: the matcher was fixed
        # after this run was written (Assamese অর্ডাৰৰ was scored as a lost term).
        code_switch_pass = (item.get("code_switch") or {}).get("pass")
        replies = item.get("replies") or {}
        if replies.get("mix") and replies.get("ask"):
            terms = _kept_terms().get(item["lang"])
            if terms:
                code_switch_pass = (
                    _term_kept(replies["mix"]["reply"], terms[0])
                    and _term_kept(replies["ask"]["reply"], terms[1])
                )
        repetition_ok = not (item.get("repetition") or {}).get("duplicate_opening")
        length_ok = (item.get("length") or {}).get("pass")
        script_ok = item.get("script_ok")
        # Recompute the verdict from the corrected parts; the stored `pass` was
        # written before the code-switch matcher was fixed.
        parts = (gender.get("pass"), code_switch_pass, script_ok, repetition_ok, length_ok)
        out[item["lang"]] = {
            "gender_status": gender.get("status") or gender.get("found"),
            "gender_pass": gender.get("pass"),
            "code_switch_pass": code_switch_pass,
            "script_ok": script_ok,
            "repetition_ok": repetition_ok,
            "length_ok": length_ok,
            "pass": all(part is not False for part in parts),
            "source": str(path.relative_to(ROOT)),
        }
    return out


def latency() -> dict:
    """Per-language perceived latency, preferring the 12-language run."""
    out = {}
    path = newest("eval/latency.json")
    data = load(path) if path else None
    if data:
        for lang, block in (data.get("languages") or {}).items():
            perceived = (block or {}).get("latency", {}).get("perceived_ms") or {}
            asr = (block or {}).get("latency", {}).get("asr_ms") or {}
            if perceived.get("n"):
                out[lang] = {"perceived_p50": perceived.get("p50"),
                             "perceived_p95": perceived.get("p95"),
                             "asr_p50": asr.get("p50"),
                             "n": perceived["n"],
                             "source": str(path.relative_to(ROOT))}
    return out


def resources() -> dict:
    """Phase 9 measurements already recorded by the latency/concurrency harnesses."""
    facts = {}
    for pattern, label in (("benchmarks/results/realworld_v3/latency_v3.json", "latency_run"),
                           ("benchmarks/results/production_v1/concurrency_v1.json", "concurrency_run")):
        path = newest(pattern)
        data = load(path) if path else None
        if not data:
            continue
        rss = data.get("server_rss") or {}
        facts[label] = {
            "source": str(path.relative_to(ROOT)),
            "peak_mb": rss.get("peak_mb"),
            "final_mb": rss.get("final_mb"),
            "cpu_count": (data.get("machine") or {}).get("cpu_count"),
        }
    return facts


def dataset() -> dict:
    manifest = ROOT / "evaluation" / "dataset_manifest.jsonl"
    if not manifest.exists():
        return {"slots": 0, "collected": 0, "verified": 0, "status": "NOT TESTED"}
    per_lang = {lang: {"slots": 0, "collected": 0, "verified": 0} for lang in LANGS}
    total = {"slots": 0, "collected": 0, "verified": 0}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        lang = entry.get("lang") or entry.get("language")
        if lang not in per_lang:
            continue
        total["slots"] += 1
        per_lang[lang]["slots"] += 1
        if (entry.get("status") or "").upper() not in {"NOT_COLLECTED", ""}:
            total["collected"] += 1
            per_lang[lang]["collected"] += 1
            if entry.get("transcript_verified") or entry.get("verified_by"):
                total["verified"] += 1
                per_lang[lang]["verified"] += 1
    listeners = len(glob.glob(str(ROOT / "evaluation/human_voice_quality/responses/*.json")))
    return {"total": total, "per_language": per_lang, "listener_responses": listeners,
            "status": "NOT TESTED" if total["collected"] == 0 else "PARTIAL"}


def _audit_module():
    """Load benchmarks/audit_conversational.py for its term matcher."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "audit_conversational", ROOT / "benchmarks" / "audit_conversational.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _kept_terms() -> dict:
    try:
        return _audit_module().KEPT_TERMS
    except Exception:
        return {}


def _term_kept(reply: str, forms: list[str]) -> bool:
    try:
        return _audit_module().term_kept(reply, forms)
    except Exception:
        return any(form in reply for form in forms)


def classify(row: dict) -> list[dict]:
    """Severity-ranked defects for one language, each with its evidence."""
    defects = []
    sp = row.get("round_trip") or {}
    acc = row.get("asr") or {}
    conv = row.get("conversational") or {}

    cer = sp.get("cer_clean_mean")
    if isinstance(cer, float) and cer > 0.15:
        defects.append({"severity": 1, "kind": "asr_accuracy",
                        "detail": f"round-trip CER {cer:.3f} > 0.15",
                        "evidence": sp.get("source")})
    elif isinstance(cer, float) and cer > 0.05:
        defects.append({"severity": 3, "kind": "asr_accuracy",
                        "detail": f"round-trip CER {cer:.3f} > 0.05",
                        "evidence": sp.get("source")})

    rate = sp.get("clean_render_rate")
    if isinstance(rate, float) and rate < 0.9:
        defects.append({"severity": 2 if rate >= 0.5 else 1, "kind": "tts_render",
                        "detail": f"{sp.get('clean_renders')}/{sp.get('renders')} clean renders",
                        "evidence": sp.get("source")})

    if acc.get("cer") is not None and acc["cer"] > 0.15:
        defects.append({"severity": 1, "kind": "asr_accuracy_corpus",
                        "detail": f"corpus CER {acc['cer']:.3f} > 0.15",
                        "evidence": acc.get("source")})

    if conv.get("gender_pass") is False:
        defects.append({"severity": 2, "kind": "gender_agreement",
                        "detail": f"gender status {conv.get('gender_status')} vs female voice",
                        "evidence": conv.get("source")})
    if conv.get("code_switch_pass") is False:
        defects.append({"severity": 2, "kind": "code_switch",
                        "detail": "caller's English term not preserved", "evidence": conv.get("source")})
    if conv.get("script_ok") is False:
        defects.append({"severity": 2, "kind": "script",
                        "detail": "reply in the wrong script",
                        "evidence": conv.get("source")})

    lat = row.get("latency") or {}
    if isinstance(lat.get("perceived_p50"), (int, float)) and lat["perceived_p50"] > 2500:
        defects.append({"severity": 3, "kind": "latency",
                        "detail": f"perceived p50 {lat['perceived_p50']:.0f} ms",
                        "evidence": lat.get("source")})
    return defects


def build() -> dict:
    sp, acc, conv, lat, res, ds = speak_check(), asr_accuracy(), conversational(), latency(), resources(), dataset()

    rows = {}
    for lang in LANGS:
        round_trip = sp.get(lang)
        row = {"lang": lang, "name": LANG_NAMES[lang],
               "round_trip": round_trip, "asr": acc.get(lang),
               "conversational": conv.get(lang), "latency": lat.get(lang)}
        defects = classify(row)
        row["defects"] = defects

        # Claim 1 — does the voice produce intelligible, correct-script audio?
        if round_trip and isinstance(round_trip.get("clean_render_rate"), float):
            claim = "PASS (automated)" if round_trip["clean_render_rate"] >= 0.9 else "PARTIAL"
        else:
            claim = "NOT TESTED"

        # Claim 2 — pronunciation judged by natives? Only "candidates" exist.
        pronunciation = ("PARTIAL — automated candidates only, no native verdict"
                         if round_trip else "NOT TESTED")

        # Claim 3 — human naturalness. Never inferred from audio metrics.
        naturalness = "NOT TESTED — no listener ratings"

        row["claims"] = {
            "automated_speech_generation": claim,
            "pronunciation": pronunciation,
            "human_naturalness": naturalness,
            "production_ready": "NOT TESTED — no human evidence",
        }
        rows[lang] = row

    worst = max((d.get("severity", 9) for r in rows.values() for d in r["defects"]), default=0)
    return {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "language_count": len(LANGS),
        "worst_severity": worst or None,
        "resources": res,
        "dataset": ds,
        "languages": rows,
    }


def render(report: dict) -> str:
    ds = report["dataset"]
    total = ds.get("total") or {}
    lines = [
        "# IndicVoice — language defect matrix",
        "",
        f"Generated {report['generated']} from stored measurements (nothing re-measured here).",
        "",
        "## Claims are separate on purpose",
        "",
        "| claim | meaning |",
        "|---|---|",
        "| automated speech generation | voice produced non-empty, correct-script, "
        "round-trip-intelligible audio |",
        "| pronunciation | NOT native-verified unless stated |",
        "| human naturalness | needs listener ratings (MOS) |",
        "| production ready | needs both of the above |",
        "",
        f"Human dataset: **{total.get('collected', 0)}/{total.get('slots', 0)} collected** "
        f"({total.get('verified', 0)} transcript-verified), "
        f"listener responses: **{ds.get('listener_responses', 0)}** → "
        f"`HUMAN DATASET: {ds.get('status')}`",
        "",
        "## Matrix",
        "",
        "| lang | TTS | ASR backend | round-trip CER | clean renders | corpus CER | latency p50 | conversational | worst defect |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for lang in LANGS:
        row = report["languages"][lang]
        sp = row["round_trip"] or {}
        lats = row["latency"] or {}
        conv = row["conversational"] or {}
        cer = sp.get("cer_clean_mean")
        acc_cer = (row["asr"] or {}).get("cer")
        defects = row["defects"]
        worst = (f"S{min(d['severity'] for d in defects)} {min(defects, key=lambda d: d['severity'])['kind']}"
                 if defects else "none")
        cer_cell = "-" if cer is None else f"{cer:.3f}"
        acc_cell = "-" if acc_cer is None else f"{acc_cer:.3f}"
        p50 = lats.get("perceived_p50")
        lat_cell = "-" if p50 is None else f"{p50:.0f} ms"
        conv_cell = "PASS" if conv.get("pass") else ("FAIL" if conv else "NOT TESTED")
        renders = f"{sp.get('clean_renders', '-')}/{sp.get('renders', '-')}"
        lines.append(
            f"| {lang} | {sp.get('tts_backend') or '-'} | {sp.get('asr_backend') or '-'} | "
            f"{cer_cell} | {renders} | {acc_cell} | {lat_cell} | {conv_cell} | {worst} |"
        )

    lines += ["", "## Defects by severity", ""]
    ranked = []
    for lang in LANGS:
        for defect in report["languages"][lang]["defects"]:
            ranked.append((defect["severity"], lang, defect))
    if not ranked:
        lines.append("No automated defect at the current thresholds.")
    for severity, lang, defect in sorted(ranked, key=lambda item: (item[0], item[1])):
        lines.append(f"- **S{severity} {lang} · {defect['kind']}** — {defect['detail']} "
                     f"(`{defect['evidence']}`)")

    res = report.get("resources") or {}
    lines += ["", "## Phase 9 — CPU and memory (measured, from existing runs)", ""]
    for label, facts in res.items():
        lines.append(f"- {label}: peak RSS {facts.get('peak_mb')} MB, final "
                     f"{facts.get('final_mb')} MB, {facts.get('cpu_count')} logical CPUs "
                     f"(`{facts.get('source')}`)")
    lines += [
        "",
        "## What is still unmeasured",
        "",
        "- MOS, naturalness, prosody and pronunciation by native listeners: **NOT TESTED**.",
        "- Real-caller recognition accuracy: every audio measurement here is synthesised.",
        "- Physical microphone, phone and telephony acoustics: **NOT TESTED**.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the per-language defect matrix")
    parser.add_argument("--out-root", default="benchmarks/results/human_voice_quality/language_audits")
    args = parser.parse_args(argv)

    report = build()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = ROOT / args.out_root / stamp
    out.mkdir(parents=True, exist_ok=True)
    (out / "matrix.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    text = render(report)
    (out / "matrix.md").write_text(text, encoding="utf-8")
    print(text)
    print(f"matrix -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
