"""Prepare anonymized audio packages for human voice-quality evaluation (V2 Phase E).

Synthesizes the fixed representative utterance set with the production TTS
voices, writes WAV files under random opaque codes (no language or text in
the public package), adds repeated samples for rating-consistency checks,
and emits rating forms. The code→(lang, utterance) map is kept in private/
and must never be shown to listeners.

Synthesizing system output for listeners is legitimate; inventing listener
scores is not. This tool produces no scores.

Usage:
    .venv313/Scripts/python.exe evaluation/human_voice_quality/prepare_samples.py
    ... --seed 42 --repeats 2 --langs hi en

Exit codes: 0 = package built, 1 = a language failed (package still written
for the languages that succeeded, failures listed in the report).
"""
from __future__ import annotations

import argparse
import csv
import json
import secrets
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

LANGS = ("hi", "bn", "ta", "te", "kn", "ml", "mr", "gu", "pa", "or", "as", "en")


def write_wav(path: Path, audio: np.ndarray, rate: int) -> None:
    pcm = np.clip(audio, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def build_package(utterances: dict, synth, out_dir: Path,
                  seed: int | None = None, repeats: int = 2,
                  langs: tuple[str, ...] = LANGS) -> dict:
    """synth(lang, text) -> (float32 mono array, sample_rate).

    Returns the private report. Public package.json carries codes only.
    """
    rng = np.random.default_rng(seed)
    audio_dir = out_dir / "audio"
    private_dir = out_dir / "private"
    forms_dir = out_dir / "forms"
    for d in (audio_dir, private_dir, forms_dir):
        d.mkdir(parents=True, exist_ok=True)

    dims = utterances["dimensions"]
    texts_by_key = {u["key"]: u["texts"] for u in utterances["utterances"]}
    keys = list(texts_by_key)

    sample_map: dict[str, dict] = {}
    failures: dict[str, str] = {}
    codes: list[str] = []

    def new_code() -> str:
        while True:
            code = secrets.token_hex(3)
            if code not in sample_map:
                return code

    for lang in langs:
        for key in keys:
            text = texts_by_key[key][lang]
            try:
                audio, rate = synth(lang, text)
            except Exception as exc:  # noqa: BLE001
                failures[lang] = str(exc)[:200]
                break
            code = new_code()
            write_wav(audio_dir / f"{code}.wav", audio, rate)
            sample_map[code] = {"lang": lang, "utterance": key,
                                "sample_rate": rate,
                                "duration_s": round(len(audio) / float(rate), 2),
                                "repeat_of": None}
            codes.append(code)
        if lang in failures or repeats <= 0:
            continue
        # repeated presentations of existing samples, under fresh codes
        lang_codes = [c for c in codes if sample_map[c]["lang"] == lang]
        for orig in rng.choice(lang_codes, size=min(repeats, len(lang_codes)),
                               replace=False):
            code = new_code()
            orig_path = audio_dir / f"{orig}.wav"
            (audio_dir / f"{code}.wav").write_bytes(orig_path.read_bytes())
            sample_map[code] = {**sample_map[orig], "repeat_of": orig}
            codes.append(code)

    order = rng.permutation(len(codes))
    public = {
        "program": "indicvoice_human_voice_quality_v2",
        "instructions": (
            "Listen to each sample (headphones recommended, quiet room). Rate "
            "all ten dimensions 1-5 using the anchors. Samples are anonymized "
            "and shuffled; some samples repeat intentionally — rate each "
            "presentation independently. Do not guess the language or voice; "
            "just rate what you hear. You may replay a sample before rating."),
        "dimensions": dims,
        "scale": utterances["scale"],
        "samples": [codes[i] for i in order],
        "n_samples": len(codes),
    }
    (out_dir / "package.json").write_text(
        json.dumps(public, indent=2, ensure_ascii=False), encoding="utf-8")
    (private_dir / "sample_map.json").write_text(
        json.dumps(sample_map, indent=2, ensure_ascii=False), encoding="utf-8")

    with (forms_dir / "rating_form.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["sample_code", *dims, "qualitative_feedback"])
        for code in public["samples"]:
            writer.writerow([code, *([""] * len(dims)), ""])

    report = {
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "repeats_per_lang": repeats,
        "langs_requested": list(langs),
        "langs_ok": sorted({v["lang"] for v in sample_map.values()}),
        "failures": failures,
        "n_samples": len(codes),
        "n_unique": sum(1 for v in sample_map.values() if v["repeat_of"] is None),
        "n_repeats": sum(1 for v in sample_map.values() if v["repeat_of"] is not None),
        "utterance_set_status": utterances.get("status", ""),
    }
    (private_dir / "preparation_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--utterances", default=str(HERE / "utterances.json"))
    parser.add_argument("--out-dir", default=str(HERE))
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--langs", nargs="*", default=list(LANGS))
    args = parser.parse_args(argv)

    from src.tts_engine import TTSEngine

    engines: dict[str, TTSEngine] = {}

    def synth(lang: str, text: str):
        if lang not in engines:
            engines[lang] = TTSEngine(lang)
        engine = engines[lang]
        return engine.synthesize(text), engine.sample_rate

    utterances = json.loads(Path(args.utterances).read_text(encoding="utf-8"))
    report = build_package(utterances, synth, Path(args.out_dir),
                           seed=args.seed, repeats=args.repeats,
                           langs=tuple(args.langs))
    # committable evidence (no answer key): the private sample_map stays git-ignored
    evidence = ROOT / "benchmarks" / "results" / "realworld_v2" / "human_eval_package_v2.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())