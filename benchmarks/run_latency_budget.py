"""End-to-end latency-budget investigation (Real-World V2, Phase F).

Extends the V1 E2E harness with the measurements the V2 brief requires:

  * Controlled CPU load (idle / moderate / high) via bounded spinner threads.
  * One session vs multiple concurrent sessions (contention).
  * Streaming (speculative ASR) vs block (?streaming=0) on the SAME clips,
    so the actual overlap saving can be computed two ways:
      - ASR-time hidden during endpoint silence  = block.asr_ms - stream.asr_ms
      - Perceived E2E saving                     = block.e2e_ms - stream.e2e_ms
    The gap between these two is the brief's "important distinction": a lower
    ASR time does NOT automatically become an equal E2E improvement, because
    LLM TTFT + TTS first-clause dominate the post-transcript budget.
  * Warm model (server --warm) vs cold first turn (reported separately).
  * Per-language P50/P90/P95 for every stage; stages are reported separately
    and NEVER summed into a synthetic "E2E".

Structural decomposition reported per turn:
  e2e_client_ms ~= endpoint_silence + first_audio_ms + transport_residual
  transport_residual = e2e_client_ms - first_audio_ms - endpoint_silence
  (endpoint_silence is the configured VAD wait; on localhost transport is small)

Safety: this is a 15 W laptop. High load is bounded (4 spinners), each
condition is short, and there is a cooldown between conditions. The script
refuses an occupied port and only kills the server it started. Corpus is the
TTS-synthesized starter set (NOT real recordings) — latency on this machine,
not real-world acoustic robustness. No paid provider is introduced; the LLM
is whatever .env already configures (Groq free tier).

Usage:
    .venv313/Scripts/python.exe benchmarks/run_latency_budget.py
    ... --langs hi en --turns 8 --conditions idle1s idle1b mod1s high1s idle3s idle3b
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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))

from run_e2e_latency import (  # noqa: E402
    RSSSampler, port_free, stats, wait_health,
)
from src import config  # noqa: E402
from src.evaluate import read_wav  # noqa: E402


class CPULoad:
    """Bounded busy-spin load. n=0 idle, 2 moderate, 4 high (8 logical cores)."""

    def __init__(self, n: int):
        self.n = n
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def _spin(self):
        x = 0.0
        while not self._stop.is_set():
            for _ in range(200000):
                x = (x + 1.0) * 1.000001 % 1e6
            self._stop.wait(0.001)

    def __enter__(self):
        for _ in range(self.n):
            t = threading.Thread(target=self._spin, daemon=True)
            t.start()
            self._threads.append(t)
        return self

    def __exit__(self, *exc):
        self._stop.set()
        for t in self._threads:
            t.join(timeout=2)


#: condition key -> (cpu_spinners, n_sessions, streaming)
CONDITIONS = {
    "idle1s": (0, 1, True),
    "idle1b": (0, 1, False),
    "mod1s": (2, 1, True),
    "high1s": (4, 1, True),
    "idle3s": (0, 3, True),
    "idle3b": (0, 3, False),
}


def overlap_savings(stream_turns: list[dict], block_turns: list[dict]) -> dict:
    """Match streaming vs block turns by (lang, clip) and compute savings.

    Returns aggregate ASR-time hidden vs perceived E2E saving, plus the gap.
    Only ok turns with both metrics present are paired.
    """
    def key(t):
        return (t["lang"], t["clip"])

    block_by = {key(t): t for t in block_turns if t.get("ok")}
    asr_saved, e2e_saved, pairs = [], [], []
    for s in stream_turns:
        if not s.get("ok"):
            continue
        b = block_by.get(key(s))
        if not b:
            continue
        if "asr_ms" in s and "asr_ms" in b:
            asr_saved.append(b["asr_ms"] - s["asr_ms"])
        if "e2e_client_ms" in s and "e2e_client_ms" in b:
            e2e_saved.append(b["e2e_client_ms"] - s["e2e_client_ms"])
        pairs.append(key(s))
    return {
        "n_pairs": len(pairs),
        "asr_time_hidden_ms": stats(asr_saved),
        "perceived_e2e_saved_ms": stats(e2e_saved),
        "note": ("asr_time_hidden is decode work overlapped with endpoint silence; "
                 "perceived_e2e_saved is what the caller actually gains. The gap is "
                 "LLM TTFT + TTS first-clause, which speculative ASR cannot reduce."),
    }


async def drive_condition(base: str, langs: list[str], turns: int,
                          n_sessions: int, streaming: bool) -> list[dict]:
    mode = "streaming" if streaming else "block"
    suffix = "" if streaming else "&streaming=0"
    results: list[dict] = []
    for lang in langs:
        clips = sorted((ROOT / "eval_data").glob(f"{lang}_*.wav"))
        if not clips:
            continue
        # build a pool of (clip, turn_idx) jobs
        jobs = [(clips[i % len(clips)], i + 1) for i in range(turns)]

        async def one(wav: Path, idx: int) -> dict:
            # run_turn hardcodes the query string; replicate with mode suffix
            audio = read_wav(wav)
            pcm = (audio * 32767).astype("<i2")
            import aiohttp
            res: dict = {"lang": lang, "clip": wav.name, "turn": idx,
                         "mode": mode, "audio_s": round(len(audio) / 16000.0, 2)}
            events: list[dict] = []
            t_first = t_last = None
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(
                    f"{base}/ws/voice?lang={lang}&backchannel=0{suffix}",
                    max_msg_size=0,
                ) as ws:
                    async def send():
                        nonlocal t_last
                        for i in range(0, len(pcm), 320):
                            await ws.send_bytes(pcm[i:i + 320].tobytes())
                            await asyncio.sleep(0.02)
                        t_last = time.perf_counter()
                        for _ in range(50):
                            await ws.send_bytes(b"\x00" * 640)
                            await asyncio.sleep(0.02)
                    sender = asyncio.create_task(send())
                    deadline = time.perf_counter() + 45
                    quiet = None
                    while time.perf_counter() < deadline:
                        try:
                            msg = await asyncio.wait_for(ws.receive(), timeout=0.5)
                        except asyncio.TimeoutError:
                            if t_first and quiet and time.perf_counter() - quiet > 1.0:
                                break
                            continue
                        quiet = time.perf_counter()
                        if msg.type == aiohttp.WSMsgType.BINARY:
                            if t_first is None:
                                t_first = time.perf_counter()
                        elif msg.type == aiohttp.WSMsgType.TEXT:
                            events.append(json.loads(msg.data))
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            res["closed_early"] = True
                            break
                    sender.cancel()
            lat = next((e for e in events if e.get("type") == "latency"), None)
            tr = next((e for e in events if e.get("type") == "transcript"), None)
            errs = [e for e in events if e.get("type") == "error"]
            if t_first and t_last:
                res["e2e_client_ms"] = round((t_first - t_last) * 1000.0, 1)
            if lat:
                for k in ("asr_ms", "llm_ms", "tts_ms", "first_audio_ms"):
                    if lat.get(k) is not None:
                        res[k] = lat[k]
            if tr:
                res["transcript"] = tr.get("text", "")
                res["asr_strategy"] = tr.get("asr_strategy", "block")
            if errs:
                res["errors"] = [e.get("message", "")[:120] for e in errs]
            endpoint = config.endpoint_for(lang) * 1000.0
            res["endpoint_silence_ms"] = round(endpoint, 1)
            if "e2e_client_ms" in res and "first_audio_ms" in res:
                res["transport_residual_ms"] = round(
                    res["e2e_client_ms"] - res["first_audio_ms"] - endpoint, 1)
            res["ok"] = bool(res.get("e2e_client_ms") and tr and not errs)
            return res

        # drive n_sessions concurrent turns at a time
        for start in range(0, len(jobs), n_sessions):
            batch = jobs[start:start + n_sessions]
            done = await asyncio.gather(*(one(w, i) for w, i in batch))
            results.extend(done)
    return results


def per_lang_stats(turns: list[dict], langs: list[str]) -> dict:
    ok = [t for t in turns if t.get("ok")]
    out = {}
    for lang in langs:
        lt = [t for t in ok if t["lang"] == lang]
        out[lang] = {
            m: stats([t[m] for t in lt if m in t])
            for m in ("e2e_client_ms", "first_audio_ms", "asr_ms", "llm_ms",
                      "tts_ms", "transport_residual_ms")
        }
        out[lang]["failed_turns"] = sum(
            1 for t in turns if t["lang"] == lang and not t.get("ok"))
        strat: dict[str, int] = {}
        for t in lt:
            strat[t.get("asr_strategy", "?")] = strat.get(t.get("asr_strategy", "?"), 0) + 1
        out[lang]["asr_strategy_counts"] = strat
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--langs", nargs="+", default=["hi", "en"])
    parser.add_argument("--turns", type=int, default=8)
    parser.add_argument("--port", type=int, default=8011)
    parser.add_argument("--conditions", nargs="+", default=list(CONDITIONS))
    parser.add_argument("--cooldown", type=float, default=8.0,
                        help="seconds idle between conditions (thermal safety)")
    parser.add_argument("--out", default=str(
        ROOT / "benchmarks" / "results" / "realworld_v2" / "latency_budget_v2.json"))
    args = parser.parse_args(argv)

    for c in args.conditions:
        if c not in CONDITIONS:
            print(f"unknown condition {c}; choose from {list(CONDITIONS)}")
            return 1
    if not port_free(args.port):
        print(f"port {args.port} occupied; investigate (netstat -ano) or use --port")
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    log_path = out_path.with_name(out_path.stem + "_server.log")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    print(f"starting server on 127.0.0.1:{args.port} (warm {args.langs})")
    conditions_out: dict[str, dict] = {}
    with open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "src.call_server", "--host", "127.0.0.1",
             "--port", str(args.port), "--warm", *args.langs],
            cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            health = wait_health(args.port)
            base = f"ws://127.0.0.1:{args.port}"
            with RSSSampler(proc.pid) as rss:
                for idx, cond in enumerate(args.conditions):
                    spin, sess, streaming = CONDITIONS[cond]
                    if idx:
                        print(f"cooldown {args.cooldown}s (thermal safety)…")
                        time.sleep(args.cooldown)
                    print(f"\n=== condition {cond}: cpu_spinners={spin} "
                          f"sessions={sess} streaming={streaming} ===")
                    with CPULoad(spin):
                        t0 = time.perf_counter()
                        turns = asyncio.run(drive_condition(
                            base, args.langs, args.turns, sess, streaming))
                        wall = time.perf_counter() - t0
                    conditions_out[cond] = {
                        "cpu_spinners": spin, "n_sessions": sess,
                        "streaming": streaming, "wall_s": round(wall, 1),
                        "per_lang": per_lang_stats(turns, args.langs),
                        "turns": turns,
                    }
                    for lang, m in conditions_out[cond]["per_lang"].items():
                        e = m["e2e_client_ms"]
                        print(f"  [{cond}/{lang}] n={e['n']} e2e p50={e['p50']} "
                              f"p90={e['p90']} p95={e['p95']} "
                              f"strat={m['asr_strategy_counts']}")
                rss_summary = rss.summary()
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

    # overlap savings: pair streaming vs block within the same session count
    savings = {}
    for sess_tag, s_cond, b_cond in (("1session", "idle1s", "idle1b"),
                                     ("3session", "idle3s", "idle3b")):
        if s_cond in conditions_out and b_cond in conditions_out:
            savings[sess_tag] = overlap_savings(
                conditions_out[s_cond]["turns"], conditions_out[b_cond]["turns"])

    report = {
        "benchmark": "latency_budget_v2",
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "machine": {"platform": sys.platform, "cpu_count": os.cpu_count(),
                    "note": "15 W i7-8565U 4C/8T laptop; load bounded for thermal safety"},
        "corpus": "TTS-synthesized starter clips (eval_data/), NOT real recordings",
        "llm": health.get("llm"),
        "config": {"langs": args.langs, "turns_per_lang": args.turns,
                   "conditions": args.conditions, "cooldown_s": args.cooldown,
                   "endpoint_ms": {l: round(config.endpoint_for(l) * 1000, 1) for l in args.langs}},
        "server_rss": rss_summary,
        "conditions": conditions_out,
        "overlap_savings": savings,
        "stage_note": ("stages overlap and are reported separately, never summed; "
                       "e2e_client_ms includes the endpoint-silence wait + localhost transport"),
    }
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out_path}")
    for tag, s in savings.items():
        ah = s["asr_time_hidden_ms"]["p50"]
        es = s["perceived_e2e_saved_ms"]["p50"]
        print(f"overlap[{tag}]: ASR hidden p50={ah}ms vs perceived E2E saved p50={es}ms "
              f"(n={s['n_pairs']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())