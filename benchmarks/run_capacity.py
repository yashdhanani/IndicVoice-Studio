"""Capacity validation under concurrent load (Real-World Validation V2, Phase G).

Drives a conservative concurrency matrix (default levels 1, 2, 3, 5) against a
real server this script starts, while sampling three resource axes:

  * system CPU utilisation   (GetSystemTimes / /proc/stat, whole machine)
  * server working-set RSS   (RSSSampler, follows the venv launcher child)
  * live operational gauges  (GET /metrics: active sessions, outbound queue
                              depth, ASR executor queue, event-loop delay)

After the load it verifies session cleanup (active_sessions returns to 0) and
recovery (a fresh turn still succeeds), then emits a conservative capacity
recommendation. Level 10 is intentionally excluded on the 4-core/15 W reference
laptop; pass --levels 1 2 3 5 10 only on stronger hardware.

This is a load test, not a torture test: it never targets an occupied port and
only terminates the server process it started itself.

Usage:
    python benchmarks/run_capacity.py
    python benchmarks/run_capacity.py --levels 1 2 3 --turns 3 --port 8013
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_e2e_latency import (  # noqa: E402
    RSSSampler, port_free, run_turn, stats, wait_health,
)


class CPUSampler:
    """Whole-machine CPU utilisation sampler (no psutil dependency).

    Windows: GetSystemTimes returns cumulative idle/kernel/user FILETIMEs;
    utilisation = 1 - idle_delta / total_delta over each interval. Linux:
    /proc/stat aggregate jiffies. Samples are (elapsed_s, percent).
    """

    def __init__(self, interval: float = 1.0):
        self.interval = interval
        self.samples: list[tuple[float, float]] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._prev = None
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class FT(ctypes.Structure):
                _fields_ = [("lo", wintypes.DWORD), ("hi", wintypes.DWORD)]

            self._ft = FT
            self._ctypes = ctypes
            self._get = ctypes.windll.kernel32.GetSystemTimes

    def _read(self):
        if sys.platform == "win32":
            idle, kernel, user = self._ft(), self._ft(), self._ft()
            byref = self._ctypes.byref
            if not self._get(byref(idle), byref(kernel), byref(user)):
                return None
            conv = lambda f: (f.hi << 32) | f.lo  # noqa: E731
            # kernel time includes idle time on Windows
            return conv(idle), conv(kernel) + conv(user)
        try:
            line = Path("/proc/stat").read_text().splitlines()[0]
            parts = [int(x) for x in line.split()[1:]]
            idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
            return idle, sum(parts)
        except OSError:
            return None

    def _run(self):
        t0 = time.perf_counter()
        self._prev = self._read()
        while not self._stop.wait(self.interval):
            cur = self._read()
            if cur and self._prev:
                d_idle = cur[0] - self._prev[0]
                d_total = cur[1] - self._prev[1]
                if d_total > 0:
                    pct = max(0.0, min(100.0, (1.0 - d_idle / d_total) * 100.0))
                    self.samples.append((round(time.perf_counter() - t0, 1), round(pct, 1)))
            self._prev = cur

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=3)

    def summary(self) -> dict:
        if not self.samples:
            return {"available": False}
        values = [p for _, p in self.samples]
        return {
            "available": True,
            "peak_pct": round(max(values), 1),
            "mean_pct": round(sum(values) / len(values), 1),
            "samples": len(values),
        }


class MetricsPoller:
    """Polls GET /metrics during load; keeps the peak of each gauge."""

    def __init__(self, port: int, token: str = "", interval: float = 1.0):
        self.url = f"http://127.0.0.1:{port}/metrics"
        if token:
            self.url += f"?token={token}"
        self.interval = interval
        self.series: list[dict] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        t0 = time.perf_counter()
        while not self._stop.wait(self.interval):
            try:
                with urllib.request.urlopen(self.url, timeout=3) as r:
                    data = json.loads(r.read().decode("utf-8"))
                data["t"] = round(time.perf_counter() - t0, 1)
                self.series.append(data)
            except Exception:
                continue

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=3)

    def peaks(self) -> dict:
        if not self.series:
            return {"available": False}
        keys = ("active_sessions", "outbound_queue_total", "outbound_queue_max",
                "asr_executor_queue", "event_loop_delay_ms")
        out = {"available": True, "samples": len(self.series)}
        for k in keys:
            vals = [s[k] for s in self.series if isinstance(s.get(k), (int, float))]
            out["peak_" + k] = round(max(vals), 2) if vals else None
        return out


def cleanup_ok(metrics: dict | None) -> bool:
    """True when the server reports zero live sessions after load."""
    return bool(metrics) and metrics.get("active_sessions") == 0


def capacity_recommendation(levels: list[dict]) -> dict:
    """Conservative safe concurrency from the measured matrix.

    A level is 'safe' only if every turn succeeded AND the event-loop delay
    stayed below 250 ms (audio delivery would stutter above that) AND CPU peak
    stayed below 95 %. The recommendation is the highest contiguous safe level
    starting from 1; we never extrapolate beyond what was measured.
    """
    safe = []
    for lv in sorted(levels, key=lambda x: x["level"]):
        ok = (
            lv["success_rate"] >= 1.0
            and (lv.get("peak_event_loop_delay_ms") or 0) < 250.0
            and (lv.get("cpu", {}).get("peak_pct") or 0) < 95.0
        )
        lv["safe"] = ok
        if ok:
            safe.append(lv["level"])
        else:
            break
    recommended = max(safe) if safe else 0
    return {
        "recommended_max_concurrency": recommended,
        "measured_levels": [lv["level"] for lv in levels],
        "safe_levels": safe,
        "basis": "highest contiguous level with 100% turn success, "
                 "event-loop delay <250 ms and CPU peak <95%",
        "note": "conservative; not extrapolated beyond measured levels. "
                "Reference machine is a 4-core/15 W laptop.",
    }


async def one_session(base, lang, clips, session_id, turns):
    results = []
    for i in range(turns):
        wav = clips[(session_id + i) % len(clips)]
        try:
            result = await run_turn(base, lang, wav, i + 1)
        except Exception as exc:                          # noqa: BLE001
            result = {"ok": False, "exception": str(exc)[:200]}
        result["session"] = session_id
        results.append(result)
    return results


async def drive_level(base, lang, clips, level, turns):
    t0 = time.perf_counter()
    sessions = await asyncio.gather(*(
        one_session(base, lang, clips, s, turns) for s in range(level)
    ))
    flat = [t for sess in sessions for t in sess]
    ok = [t for t in flat if t.get("ok")]
    return {
        "level": level,
        "turns_total": len(flat),
        "turns_ok": len(ok),
        "success_rate": round(len(ok) / len(flat), 3) if flat else 0.0,
        "wall_s": round(time.perf_counter() - t0, 1),
        "e2e_client_ms": stats([t["e2e_client_ms"] for t in ok if "e2e_client_ms" in t]),
        "first_audio_ms": stats([t["first_audio_ms"] for t in ok if "first_audio_ms" in t]),
        "asr_ms": stats([t["asr_ms"] for t in ok if "asr_ms" in t]),
        "errors": [t.get("errors") or t.get("exception") for t in flat
                   if not t.get("ok")][:10],
        "turns": flat,
    }


def fetch_metrics(port, token=""):
    url = f"http://127.0.0.1:{port}/metrics"
    if token:
        url += f"?token={token}"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


async def drive(args, base, port):
    clips = sorted((ROOT / "eval_data").glob(f"{args.lang}_*.wav"))
    if not clips:
        raise RuntimeError(f"no starter clips for {args.lang}")
    levels = []
    for level in args.levels:
        print(f"--- level {level}: {level} concurrent sessions x {args.turns} turns ---")
        with CPUSampler() as cpu, MetricsPoller(port, args.token) as mp:
            result = await drive_level(base, args.lang, clips, level, args.turns)
            result["cpu"] = cpu.summary()
            result["cpu_series"] = cpu.samples
            result["metrics_peaks"] = mp.peaks()
            result["peak_event_loop_delay_ms"] = mp.peaks().get("peak_event_loop_delay_ms")
        levels.append(result)
        e2e = result["e2e_client_ms"]
        print(f"    ok={result['turns_ok']}/{result['turns_total']} "
              f"e2e p50={e2e['p50']} p95={e2e['p95']} ms "
              f"cpu_peak={result['cpu'].get('peak_pct')}% "
              f"loop_delay_peak={result['peak_event_loop_delay_ms']}ms "
              f"wall={result['wall_s']}s")
        await asyncio.sleep(args.cooldown)  # thermal safety on the 15 W laptop
    return levels


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lang", default="hi")
    parser.add_argument("--levels", nargs="+", type=int, default=[1, 2, 3, 5])
    parser.add_argument("--turns", type=int, default=3, help="turns per session")
    parser.add_argument("--port", type=int, default=8013)
    parser.add_argument("--token", default="", help="access token if the server requires one")
    parser.add_argument("--cooldown", type=float, default=8.0, help="seconds between levels")
    parser.add_argument("--out", default=str(ROOT / "benchmarks" / "results" / "realworld_v2" / "capacity_v2.json"))
    args = parser.parse_args(argv)

    if not port_free(args.port):
        print(f"port {args.port} is occupied; identify the owner first or use --port")
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    log_path = out_path.with_name(out_path.stem + "_server.log")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    if args.token:
        env["INDICVOICE_TOKEN"] = args.token
    print(f"starting server on 127.0.0.1:{args.port}")
    with open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "src.call_server",
             "--host", "127.0.0.1", "--port", str(args.port), "--warm", args.lang],
            cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            health = wait_health(args.port)
            with RSSSampler(proc.pid) as rss:
                started = time.strftime("%Y-%m-%dT%H:%M:%S")
                levels = asyncio.run(drive(args, f"ws://127.0.0.1:{args.port}", args.port))
                rss_summary = rss.summary()
                rss_series = rss.samples
            # let in-flight sessions drain, then verify cleanup + recovery
            time.sleep(3)
            after = fetch_metrics(args.port, args.token)
            cleanup = cleanup_ok(after)
            clips = sorted((ROOT / "eval_data").glob(f"{args.lang}_*.wav"))
            recovery = {"ok": False}
            if clips:
                try:
                    recovery = asyncio.run(
                        run_turn(f"ws://127.0.0.1:{args.port}", args.lang, clips[0], 1))
                except Exception as exc:                  # noqa: BLE001
                    recovery = {"ok": False, "exception": str(exc)[:200]}
        finally:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                               capture_output=True)
            else:
                proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    recommendation = capacity_recommendation(levels)
    report = {
        "benchmark": "capacity_v2",
        "started": started,
        "machine": {"platform": sys.platform, "cpu_count": os.cpu_count()},
        "config": {"lang": args.lang, "levels": args.levels,
                   "turns_per_session": args.turns, "cooldown_s": args.cooldown,
                   "note": "level 10 excluded by default on the 4-core/15W reference laptop"},
        "corpus": "TTS-synthesized starter clips (eval_data/), NOT real recordings",
        "llm": health.get("llm"),
        "server_rss": rss_summary,
        "rss_series_mb": rss_series,
        "levels": levels,
        "post_load": {
            "active_sessions": (after or {}).get("active_sessions"),
            "cleanup_ok": cleanup,
            "recovery_turn_ok": bool(recovery.get("ok")),
            "recovery_e2e_ms": recovery.get("e2e_client_ms"),
        },
        "capacity_recommendation": recommendation,
    }
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out_path}")
    print(f"cleanup_ok={cleanup} recovery_ok={recovery.get('ok')} "
          f"recommended_max_concurrency={recommendation['recommended_max_concurrency']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())