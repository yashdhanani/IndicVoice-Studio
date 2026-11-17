"""TTS synthesis benchmark (Production Hardening V1, Phase E).

For every configured language voice: full-utterance synthesis wall time,
real-time factor (RTF = wall seconds / audio seconds), and first-sentence
render latency (the offline part of "time to first audio"; playback and
network add on top in a live call).

Inputs are the reference sentences from eval_data/manifest.json (the same
sentences the synthetic ASR corpus speaks). No playback, no cloud, no
server. Run sequentially with no other CPU-heavy work for stable numbers.

Usage:
    python benchmarks/run_tts_bench.py
    python benchmarks/run_tts_bench.py --repeats 2 --out benchmarks/results/production_v1/tts_v1.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402
from src.tts_engine import TTSEngine  # noqa: E402


def percentile(values, pct):
    if not values:
        return None
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, int(round(pct / 100.0 * len(ordered) + 0.5)) - 1))
    return round(ordered[k], 3)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", default=str(ROOT / "eval_data" / "manifest.json"))
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--out", default=str(ROOT / "benchmarks" / "results" / "production_v1" / "tts_v1.json"))
    args = parser.parse_args(argv)

    entries = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    by_lang: dict[str, list[str]] = {}
    for e in entries:
        by_lang.setdefault(e["language"], []).append(e["reference_text"])

    results = {}
    for lang, texts in by_lang.items():
        backend = config.tts_backend(lang)
        try:
            engine = TTSEngine(lang)
        except Exception as exc:                          # noqa: BLE001
            print(f"[{lang}] SKIP: {exc}")
            results[lang] = {"backend": backend, "error": str(exc)[:200]}
            continue
        engine.synthesize(texts[0])  # warm caches, excluded from timing
        runs = []
        for text in texts:
            for _ in range(args.repeats):
                t0 = time.perf_counter()
                audio = engine.synthesize(text)
                wall = time.perf_counter() - t0
                audio_s = audio.size / float(engine.sample_rate)
                sentences = engine.normalizer.split_sentences(text) or [text]
                t1 = time.perf_counter()
                first = engine.render_sentence(sentences[0])
                first_ms = (time.perf_counter() - t1) * 1000.0
                runs.append({
                    "text": text,
                    "synth_ms": round(wall * 1000.0, 1),
                    "audio_s": round(audio_s, 2),
                    "rtf": round(wall / audio_s, 3) if audio_s > 0 else None,
                    "first_sentence_render_ms": round(first_ms, 1),
                    "first_sentence_audio_s": round(first.size / float(engine.sample_rate), 2),
                })
        rtfs = [r["rtf"] for r in runs if r["rtf"] is not None]
        results[lang] = {
            "backend": backend,
            "sample_rate": engine.sample_rate,
            "n": len(runs),
            "rtf_p50": percentile(rtfs, 50),
            "rtf_p90": percentile(rtfs, 90),
            "rtf_max": round(max(rtfs), 3) if rtfs else None,
            "synth_ms_p50": percentile([r["synth_ms"] for r in runs], 50),
            "first_sentence_render_ms_p50": percentile(
                [r["first_sentence_render_ms"] for r in runs], 50),
            "runs": runs,
        }
        print(f"[{lang}] backend={backend} rtf_p50={results[lang]['rtf_p50']} "
              f"first_sentence_p50={results[lang]['first_sentence_render_ms_p50']}ms "
              f"n={len(runs)}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "benchmark": "tts_v1",
        "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "note": "offline synthesis; first_sentence_render_ms excludes playback/network",
        "per_lang": results,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())