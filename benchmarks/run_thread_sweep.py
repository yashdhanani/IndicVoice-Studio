"""V3 Phase B: controlled inference-thread sweep (microbenchmark).

Measures ASR decode and TTS synthesis latency, CPU and memory under explicit
thread counts on the reference 4-core/8-thread i7-8565U, plus a combined
ASR+TTS contention run that reproduces the live-call overlap (speculative
decode while the previous turn is still being synthesised).

No server, no cloud calls, no microphone. Models are loaded fresh per
configuration and released afterwards. Background machine load is sampled
before every block and recorded, because IDE/webview processes on this
machine are not under the benchmark's control.

Usage:
    python benchmarks/run_thread_sweep.py
    python benchmarks/run_thread_sweep.py --stt-threads 8 4 2 --tts-threads 0 2
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import threading
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402


def _cpu_times():
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class FT(ctypes.Structure):
            _fields_ = [("lo", wintypes.DWORD), ("hi", wintypes.DWORD)]

        idle, kernel, user = FT(), FT(), FT()
        ok = ctypes.windll.kernel32.GetSystemTimes(
            ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
        if not ok:
            return None
        conv = lambda f: (f.hi << 32) | f.lo  # noqa: E731
        return conv(idle), conv(kernel) + conv(user)
    try:
        parts = [int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
        return parts[3] + (parts[4] if len(parts) > 4 else 0), sum(parts)
    except OSError:
        return None


def cpu_pct(seconds: float) -> float | None:
    a = _cpu_times()
    time.sleep(seconds)
    b = _cpu_times()
    if not a or not b or b[1] <= a[1]:
        return None
    return round((1.0 - (b[0] - a[0]) / (b[1] - a[1])) * 100.0, 1)


class cpu_window:
    """Mean whole-machine CPU between enter and exit."""

    def __enter__(self):
        self.t0 = time.perf_counter()
        self.a = _cpu_times()
        return self

    def __exit__(self, *exc):
        self.b = _cpu_times()
        self.wall = time.perf_counter() - self.t0
        if self.a and self.b and self.b[1] > self.a[1]:
            self.pct = round((1.0 - (self.b[0] - self.a[0]) / (self.b[1] - self.a[1])) * 100.0, 1)
        else:
            self.pct = None


def rss_mb() -> float | None:
    from src.call_server import _process_rss_mb
    return _process_rss_mb()


def stats(values: list[float]) -> dict:
    if not values:
        return {}
    ordered = sorted(values)
    pick = lambda q: ordered[min(len(ordered) - 1, int(q * len(ordered)))]  # noqa: E731
    return {
        "n": len(values),
        "p50": round(pick(0.50), 1),
        "p90": round(pick(0.90), 1),
        "p95": round(pick(0.95), 1),
        "max": round(ordered[-1], 1),
        "mean": round(sum(values) / len(values), 1),
    }


def load_wav(path: Path) -> np.ndarray:
    from src.evaluate import read_wav
    return read_wav(path)


def sweep_asr(lang: str, thread_counts: list[int], clips: list[Path], repeats: int) -> list[dict]:
    from src.sts_pipeline import STTEngine

    results = []
    reference: dict[str, str] | None = None
    for threads in thread_counts:
        gc.collect()
        bg = cpu_pct(2.0)
        rss_before = rss_mb()
        t_load = time.perf_counter()
        engine = STTEngine(backend="indic", lang=lang, num_threads=threads)
        load_ms = (time.perf_counter() - t_load) * 1000.0
        rss_loaded = rss_mb()
        per_clip = {}
        transcripts = {}
        all_ms = []
        with cpu_window() as cw:
            for clip in clips:
                audio = load_wav(clip)
                times = []
                text = ""
                for _ in range(repeats):
                    t0 = time.perf_counter()
                    text = engine.transcribe(audio)
                    times.append((time.perf_counter() - t0) * 1000.0)
                per_clip[clip.stem] = stats(times)
                transcripts[clip.stem] = text
                all_ms.extend(times)
        identical = reference is None or transcripts == reference
        if reference is None:
            reference = transcripts
        results.append({
            "threads": threads,
            "background_cpu_pct_before": bg,
            "load_ms": round(load_ms, 1),
            "rss_delta_mb": round((rss_loaded or 0) - (rss_before or 0), 1),
            "decode_ms": stats(all_ms),
            "per_clip": per_clip,
            "cpu_pct_during": cw.pct,
            "transcripts_identical_to_first_config": identical,
            "transcripts": transcripts,
        })
        print(f"  asr threads={threads}: p50={results[-1]['decode_ms'].get('p50')}ms "
              f"cpu={cw.pct}% bg={bg}% identical={identical}")
        del engine
        gc.collect()
        time.sleep(2.0)
    return results


TTS_TEXT = {
    "hi": "नमस्ते, आपका ऑर्डर कल दोपहर तक डिलीवर हो जाएगा। क्या मैं आपकी कोई और मदद कर सकता हूँ?",
    "en": "Hello, your order will be delivered by tomorrow afternoon. Is there anything else I can help you with?",
}


def _tiny_cls(lang: str):
    directory = config.TINY_DIRS[lang]
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
    from indic_tiny_tts import TinyTTSOnnx
    return TinyTTSOnnx


def sweep_tts(lang: str, thread_counts: list[int], repeats: int) -> list[dict]:
    cls = _tiny_cls(lang)
    text = TTS_TEXT.get(lang, TTS_TEXT["hi"])
    results = []
    for threads in thread_counts:
        gc.collect()
        bg = cpu_pct(2.0)
        rss_before = rss_mb()
        t_load = time.perf_counter()
        tts = cls.from_pretrained(str(config.TINY_DIRS[lang]), threads=threads or None)
        load_ms = (time.perf_counter() - t_load) * 1000.0
        rss_loaded = rss_mb()
        times, durations = [], []
        with cpu_window() as cw:
            for _ in range(repeats):
                t0 = time.perf_counter()
                audio = tts.synthesize(text, voice="female", speed=config.TINY_SPEED)
                times.append((time.perf_counter() - t0) * 1000.0)
                durations.append(len(audio) / tts.sample_rate)
        results.append({
            "threads": threads if threads else "ort-default",
            "background_cpu_pct_before": bg,
            "load_ms": round(load_ms, 1),
            "rss_delta_mb": round((rss_loaded or 0) - (rss_before or 0), 1),
            "synth_ms": stats(times),
            "audio_s_mean": round(sum(durations) / len(durations), 2),
            "rtf_p50": round(sorted(times)[len(times) // 2] / 1000.0 / (sum(durations) / len(durations)), 3),
            "cpu_pct_during": cw.pct,
        })
        print(f"  tts threads={threads or 'default'}: p50={results[-1]['synth_ms'].get('p50')}ms "
              f"rtf={results[-1]['rtf_p50']} cpu={cw.pct}% bg={bg}%")
        del tts
        gc.collect()
        time.sleep(2.0)
    return results


def contention(lang: str, stt_threads: int, tts_threads: int, clips: list[Path],
               repeats: int) -> dict:
    """ASR decodes in a worker thread while TTS synthesises on this thread."""
    from src.sts_pipeline import STTEngine

    gc.collect()
    bg = cpu_pct(2.0)
    engine = STTEngine(backend="indic", lang=lang, num_threads=stt_threads)
    tts = _tiny_cls(lang).from_pretrained(str(config.TINY_DIRS[lang]), threads=tts_threads or None)
    text = TTS_TEXT.get(lang, TTS_TEXT["hi"])
    audio = load_wav(clips[0])
    asr_ms: list[float] = []
    tts_ms: list[float] = []
    stop = threading.Event()

    def asr_loop():
        while not stop.is_set():
            t0 = time.perf_counter()
            engine.transcribe(audio)
            asr_ms.append((time.perf_counter() - t0) * 1000.0)

    worker = threading.Thread(target=asr_loop, daemon=True)
    with cpu_window() as cw:
        worker.start()
        for _ in range(repeats):
            t0 = time.perf_counter()
            tts.synthesize(text, voice="female", speed=config.TINY_SPEED)
            tts_ms.append((time.perf_counter() - t0) * 1000.0)
        stop.set()
        worker.join(timeout=30)
    out = {
        "stt_threads": stt_threads,
        "tts_threads": tts_threads if tts_threads else "ort-default",
        "background_cpu_pct_before": bg,
        "asr_ms_under_contention": stats(asr_ms),
        "tts_ms_under_contention": stats(tts_ms),
        "cpu_pct_during": cw.pct,
    }
    print(f"  contention stt={stt_threads} tts={tts_threads or 'default'}: "
          f"asr p50={out['asr_ms_under_contention'].get('p50')}ms "
          f"tts p50={out['tts_ms_under_contention'].get('p50')}ms cpu={cw.pct}%")
    del engine, tts
    gc.collect()
    time.sleep(2.0)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lang", default="hi")
    parser.add_argument("--stt-threads", nargs="+", type=int, default=[8, 4, 2, 1])
    parser.add_argument("--tts-threads", nargs="+", type=int, default=[0, 4, 2, 1],
                        help="0 = onnxruntime default (current production behaviour)")
    parser.add_argument("--repeats", type=int, default=6)
    parser.add_argument("--contention", nargs="*", default=None,
                        help="pairs as stt:tts, e.g. 8:0 4:2 (default: first/last of each sweep)")
    parser.add_argument("--out", default=str(ROOT / "benchmarks" / "results" / "realworld_v3" / "thread_sweep_v3.json"))
    args = parser.parse_args(argv)

    clips = sorted((ROOT / "eval_data").glob(f"{args.lang}_*.wav"))
    if not clips:
        print(f"no starter clips for {args.lang}")
        return 1

    pairs = args.contention
    if pairs is None:
        pairs = [f"{args.stt_threads[0]}:{args.tts_threads[0]}",
                 f"{args.stt_threads[-2] if len(args.stt_threads) > 1 else args.stt_threads[0]}:"
                 f"{args.tts_threads[-2] if len(args.tts_threads) > 1 else args.tts_threads[0]}"]

    print(f"machine background CPU: {cpu_pct(3.0)}%")
    print("ASR sweep")
    asr = sweep_asr(args.lang, args.stt_threads, clips, args.repeats)
    print("TTS sweep")
    tts = sweep_tts(args.lang, args.tts_threads, args.repeats)
    print("contention runs")
    cont = []
    for pair in pairs:
        stt_t, tts_t = (int(x) for x in pair.split(":"))
        cont.append(contention(args.lang, stt_t, tts_t, clips, args.repeats))

    report = {
        "benchmark": "thread_sweep_v3",
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "machine": {"platform": sys.platform, "cpu_count_logical": os.cpu_count(),
                    "physical_cores": 4, "model": "i7-8565U (15W laptop)",
                    "note": "IDE/webview background load present; recorded per block"},
        "runtime": {"python": sys.version.split()[0]},
        "config": {"lang": args.lang, "repeats": args.repeats,
                   "stt_threads": args.stt_threads, "tts_threads": args.tts_threads},
        "corpus": "TTS-synthesized starter clips (eval_data/), NOT real recordings",
        "asr": asr,
        "tts": tts,
        "contention": cont,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())