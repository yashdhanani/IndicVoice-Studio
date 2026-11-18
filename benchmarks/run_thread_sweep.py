"""Thread sweep for IndicVoice on the reference CPU.

Vary INDICVOICE_STT_THREADS and INDICVOICE_TTS_THREADS without code changes
(env vars are read by config at import time), measuring ASR decode and TTS
render latency on a fixed phrase. Fully local; no network, no paid calls.

    .venv313/Scripts/python.exe -m benchmarks.run_thread_sweep --langs hi en --repeats 5
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

PHRASES = {
    "hi": "मेरा ऑर्डर नंबर एक दो तीन है, कल तक पहुँच जाएगा।",
    "en": "My order number is one two three and it should arrive tomorrow.",
    "gu": "મારો ઓર્ડર નંબર એક બે ત્રણ છે, કાલ સુધીમાં પહોંચી જશે.",
    "ta": "என் ஆர்டர் எண் ஒன்று இரண்டு மூன்று, நாளைக்குள் வந்துவிடும்.",
    "mr": "माझा ऑर्डर नंबर एक दो तीन आहे, उद्या पर्यंत पोहोचेल.",
    "bn": "আমার অর্ডার নম্বর এক দুই তিন, কাল পৌঁছে যাবে।",
}

OUT = Path("benchmarks/results/cpu_sts_optimization/runs")


def rss_mb() -> float:
    try:
        import psutil
        return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
    except Exception:
        try:
            from src.call_server import _process_rss_mb
            return _process_rss_mb()
        except Exception:
            return -1.0


def run_one(lang, stt_threads, tts_threads, repeats):
    os.environ["INDICVOICE_STT_THREADS"] = str(stt_threads)
    os.environ["INDICVOICE_TTS_THREADS"] = str(tts_threads)
    # config reads env at import; force reimport
    for m in ("src.config", "src.sts_pipeline", "src.tts_engine"):
        sys.modules.pop(m, None)
    from src import config
    from src.sts_pipeline import shared_stt
    from src.tts_engine import TTSEngine

    engine = TTSEngine(lang)
    stt = shared_stt("auto", lang)
    phrase = PHRASES[lang]
    tts_times, asr_times = [], []
    audio = None
    for _ in range(repeats):
        t0 = time.perf_counter()
        audio = engine.render_sentence(phrase, cancel_event=None)
        tts_times.append((time.perf_counter() - t0) * 1000.0)
        t1 = time.perf_counter()
        _ = stt.transcribe(audio, engine.sample_rate)
        asr_times.append((time.perf_counter() - t1) * 1000.0)
    return {
        "stt_threads": stt_threads,
        "tts_threads": tts_threads,
        "tts_ms_median": round(statistics.median(tts_times), 1),
        "tts_ms_min": round(min(tts_times), 1),
        "asr_ms_median": round(statistics.median(asr_times), 1),
        "asr_ms_min": round(min(asr_times), 1),
        "audio_s": round(audio.size / engine.sample_rate, 2),
        "rss_mb": round(rss_mb(), 1),
    }


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    p = argparse.ArgumentParser()
    p.add_argument("--langs", nargs="+", default=["hi"])
    p.add_argument("--repeats", type=int, default=5)
    p.add_argument("--stt-threads", nargs="+", type=int, default=[1, 2, 3, 4])
    p.add_argument("--tts-threads", nargs="+", type=int, default=[1, 2, 4])
    args = p.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    results = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "host": "i7-8565U 4c/8t, 15.88GB RAM, Windows 11, Python 3.13",
        "repeats": args.repeats,
        "langs": {},
    }
    for lang in args.langs:
        rows = []
        for st in args.stt_threads:
            for tt in args.tts_threads:
                print(f"[{lang}] stt={st} tts={tt} ...", flush=True)
                try:
                    r = run_one(lang, st, tt, args.repeats)
                    rows.append(r)
                    print(f"   {r}", flush=True)
                except Exception as exc:
                    rows.append({"stt_threads": st, "tts_threads": tt, "error": str(exc)[:200]})
                    print(f"   ERROR: {exc}", flush=True)
        results["langs"][lang] = rows

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = OUT / f"thread_sweep_{stamp}.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
