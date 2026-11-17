"""Labeled noise robustness matrix (Production Hardening V1, Phase E).

Adds calibrated synthetic noise at fixed SNR levels to the synthetic starter
clips and measures block-ASR CER against the manifest references. This
checks the pipeline's noise wiring and gives a *relative* degradation curve;
it is NOT real-world acoustic validation (synthetic speech + synthetic
noise, no room impulse response, no real babble).

Usage:
    python benchmarks/run_noise_matrix.py --langs hi gu kn
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from scipy import signal  # noqa: E402

from src import config  # noqa: E402
from src.evaluate import cer, read_wav  # noqa: E402
from src.sts_pipeline import shared_stt  # noqa: E402

CONDITIONS = ("clean", "snr20", "snr10", "snr5")


def add_noise(audio: np.ndarray, snr_db: float | None, seed: int) -> np.ndarray:
    if snr_db is None:
        return audio
    rng = np.random.default_rng(seed)
    white = rng.standard_normal(audio.size).astype(np.float32)
    # low-pass shaped noise (closer to ambient rumble than pure white)
    b, a = signal.butter(2, 0.25)
    shaped = signal.lfilter(b, a, white).astype(np.float32)
    sig_power = float(np.mean(audio ** 2)) + 1e-12
    noise_power = float(np.mean(shaped ** 2)) + 1e-12
    target = sig_power / (10.0 ** (snr_db / 10.0))
    return audio + shaped * np.sqrt(target / noise_power)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--langs", nargs="+", default=["hi", "gu", "kn"])
    parser.add_argument("--manifest", default=str(ROOT / "eval_data" / "manifest.json"))
    parser.add_argument("--out", default=str(ROOT / "benchmarks" / "results" / "production_v1" / "noise_matrix_v1.json"))
    args = parser.parse_args(argv)

    entries = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    results = {}
    for lang in args.langs:
        clips = [e for e in entries if e["language"] == lang]
        if not clips:
            continue
        engine = shared_stt("auto", lang, config.DEFAULT_STT_MODEL)
        per_cond = {c: [] for c in CONDITIONS}
        rows = []
        for e in clips:
            audio = read_wav(ROOT / "eval_data" / e["audio_file"])
            for cond in CONDITIONS:
                snr = None if cond == "clean" else float(cond[3:])
                noisy = add_noise(audio, snr, seed=42)
                t0 = time.perf_counter()
                hyp = engine.transcribe(noisy)
                ms = (time.perf_counter() - t0) * 1000.0
                c = cer(e["reference_text"], hyp)
                per_cond[cond].append(c)
                rows.append({"clip": e["audio_file"], "condition": cond,
                             "cer": round(c, 3), "asr_ms": round(ms, 1),
                             "hyp": hyp})
                print(f"[{lang}] {e['audio_file']} {cond}: CER={c:.3f} ({ms:.0f}ms)")
        results[lang] = {
            "backend": getattr(engine, "backend", "?"),
            "mean_cer": {c: round(float(np.mean(v)), 3) if v else None
                         for c, v in per_cond.items()},
            "rows": rows,
        }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "benchmark": "noise_matrix_v1",
        "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "note": "synthetic low-pass noise on TTS-synthesized clips; relative "
                "degradation only, NOT real-world acoustic validation",
        "conditions": list(CONDITIONS),
        "per_lang": results,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())