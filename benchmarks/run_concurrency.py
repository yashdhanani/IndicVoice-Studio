"""Concurrent-session stress matrix (Production Hardening V1, Phase G).

Drives N simultaneous call sessions (default levels 1, 2, 3, 5) against a
real server started by this script, each session running several sequential
real-time turns from the synthetic starter corpus. Reports per-level success
rate, latency percentiles and server working-set peak.

Level 10 is intentionally NOT in the default matrix on the reference machine
(i7-8565U, 4 cores / 8 threads, ~4 GB free RAM): five concurrent local ASR
decodes already saturate it. Pass --levels 1 2 3 5 10 on stronger hardware.

Usage:
    python benchmarks/run_concurrency.py
    python benchmarks/run_concurrency.py --levels 1 2 3 --turns 3 --port 8010

Only terminates the server process it started itself; refuses occupied ports.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_e2e_latency import (  # noqa: E402
    RSSSampler, port_free, run_turn, stats, wait_health,
)


async def one_session(base: str, lang: str, clips: list[Path],
                      session_id: int, turns: int) -> list[dict]:
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


async def drive_level(base: str, lang: str, clips: list[Path],
                      level: int, turns: int) -> dict:
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


async def drive(args, base: str) -> list[dict]:
    clips = sorted((ROOT / "eval_data").glob(f"{args.lang}_*.wav"))
    if not clips:
        raise RuntimeError(f"no starter clips for {args.lang}")
    levels = []
    for level in args.levels:
        print(f"--- level {level}: {level} concurrent sessions x {args.turns} turns ---")
        result = await drive_level(base, args.lang, clips, level, args.turns)
        levels.append(result)
        e2e = result["e2e_client_ms"]
        print(f"    ok={result['turns_ok']}/{result['turns_total']} "
              f"e2e p50={e2e['p50']} p95={e2e['p95']} ms "
              f"wall={result['wall_s']}s")
        await asyncio.sleep(3)  # let the server settle between levels
    return levels


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lang", default="hi")
    parser.add_argument("--levels", nargs="+", type=int, default=[1, 2, 3, 5])
    parser.add_argument("--turns", type=int, default=3, help="turns per session")
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--out", default=str(ROOT / "benchmarks" / "results" / "production_v1" / "concurrency_v1.json"))
    args = parser.parse_args(argv)

    if not port_free(args.port):
        print(f"port {args.port} is occupied; identify the owner first or use --port")
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    log_path = out_path.with_name(out_path.stem + "_server.log")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
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
                levels = asyncio.run(drive(args, f"ws://127.0.0.1:{args.port}"))
                rss_summary = rss.summary()
                rss_series = rss.samples
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

    report = {
        "benchmark": "concurrency_v1",
        "started": started,
        "machine": {"platform": sys.platform, "cpu_count": os.cpu_count()},
        "config": {"lang": args.lang, "levels": args.levels,
                   "turns_per_session": args.turns,
                   "note": "level 10 excluded by default on the 4-core/15W reference laptop"},
        "corpus": "TTS-synthesized starter clips (eval_data/), NOT real recordings",
        "llm": health.get("llm"),
        "server_rss": rss_summary,
        "levels": levels,
        "rss_series_mb": rss_series,
    }
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())