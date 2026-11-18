"""V3 Phase C end-to-end latency benchmark with full stage attribution.

Same methodology as benchmarks/run_e2e_latency.py (real server, real-time
synthetic-corpus turns, last-speech-frame -> first-audio-byte client timing)
plus:

  llm_ttft_ms   LLM request start -> first token (true TTFT, excludes the
                ASR->LLM handoff that llm_ms includes)
  asr_strategy  speculative / full / cloud / block counts per language
  --endpoint X  optional per-call end-of-turn silence override, for the
                controlled endpoint experiment (defaults unchanged)

Stage timings overlap in the streaming pipeline and are never summed.
Corpus caveat: eval_data/*.wav are TTS-synthesized starter clips, NOT real
human recordings.

Usage:
    python benchmarks/run_latency_v3.py --langs hi en --turns 20
    python benchmarks/run_latency_v3.py --langs hi --turns 12 --endpoint 0.20 \
        --out benchmarks/results/realworld_v3/latency_v3_hi_ep200.json
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

import aiohttp  # noqa: E402

from run_e2e_latency import (  # noqa: E402
    RSSSampler, port_free, stats, wait_health,
)
from src import config  # noqa: E402
from src.evaluate import read_wav  # noqa: E402


async def run_turn(base: str, lang: str, wav: Path, turn_idx: int,
                   endpoint: float | None) -> dict:
    audio = read_wav(wav)
    pcm = (audio * 32767).astype("<i2")
    result: dict = {
        "lang": lang, "clip": wav.name, "turn": turn_idx,
        "audio_s": round(len(audio) / 16000.0, 2),
    }
    query = f"lang={lang}&backchannel=0"
    if endpoint is not None:
        query += f"&endpoint={endpoint}"
    events: list[dict] = []
    t_first_audio = None
    t_last_speech = None
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(
            f"{base}/ws/voice?{query}", max_msg_size=0,
        ) as ws:
            async def send():
                nonlocal t_last_speech
                for i in range(0, len(pcm), 320):
                    await ws.send_bytes(pcm[i:i + 320].tobytes())
                    await asyncio.sleep(0.02)
                t_last_speech = time.perf_counter()
                for _ in range(50):  # 1 s trailing silence -> endpoint
                    await ws.send_bytes(b"\x00" * 640)
                    await asyncio.sleep(0.02)

            sender = asyncio.create_task(send())
            deadline = time.perf_counter() + 40
            quiet_since = None
            while time.perf_counter() < deadline:
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=0.5)
                except asyncio.TimeoutError:
                    if t_first_audio and quiet_since and time.perf_counter() - quiet_since > 1.0:
                        break
                    continue
                quiet_since = time.perf_counter()
                if msg.type == aiohttp.WSMsgType.BINARY:
                    if t_first_audio is None:
                        t_first_audio = time.perf_counter()
                elif msg.type == aiohttp.WSMsgType.TEXT:
                    events.append(json.loads(msg.data))
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    result["closed_early"] = True
                    break
            sender.cancel()
    latency = next((e for e in events if e.get("type") == "latency"), None)
    transcript = next((e for e in events if e.get("type") == "transcript"), None)
    errors = [e for e in events if e.get("type") == "error"]
    if t_first_audio and t_last_speech:
        result["e2e_client_ms"] = round((t_first_audio - t_last_speech) * 1000.0, 1)
    if latency:
        for key in ("asr_ms", "llm_ms", "llm_ttft_ms", "tts_ms", "first_audio_ms"):
            if latency.get(key) is not None:
                result[key] = latency[key]
    if transcript:
        result["transcript"] = transcript.get("text", "")
        result["asr_strategy"] = transcript.get("asr_strategy", "block")
    if errors:
        result["errors"] = [e.get("message", "")[:120] for e in errors]
    result["ok"] = bool(result.get("e2e_client_ms") and transcript and not errors)
    return result


async def drive(args) -> dict:
    base = f"ws://127.0.0.1:{args.port}"
    turns = []
    for lang in args.langs:
        clips = sorted((ROOT / "eval_data").glob(f"{lang}_*.wav"))
        if not clips:
            print(f"[skip] no starter clips for {lang}")
            continue
        for i in range(args.turns):
            wav = clips[i % len(clips)]
            t0 = time.perf_counter()
            try:
                result = await run_turn(base, lang, wav, i + 1, args.endpoint)
            except Exception as exc:                      # noqa: BLE001
                result = {"lang": lang, "clip": wav.name, "turn": i + 1,
                          "ok": False, "exception": str(exc)[:200]}
            turns.append(result)
            print(f"[{lang} {i + 1}/{args.turns}] "
                  f"e2e={result.get('e2e_client_ms')}ms "
                  f"ttft={result.get('llm_ttft_ms')}ms "
                  f"asr={result.get('asr_ms')}ms "
                  f"strategy={result.get('asr_strategy')} "
                  f"ok={result.get('ok')} "
                  f"({time.perf_counter() - t0:.1f}s)")
    return {"turns": turns}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--langs", nargs="+", default=["hi", "en"])
    parser.add_argument("--turns", type=int, default=20)
    parser.add_argument("--port", type=int, default=8014)
    parser.add_argument("--endpoint", type=float, default=None,
                        help="per-call end-of-turn silence override (s)")
    parser.add_argument("--out", default=str(
        ROOT / "benchmarks" / "results" / "realworld_v3" / "latency_v3.json"))
    args = parser.parse_args(argv)

    if not port_free(args.port):
        print(f"port {args.port} is occupied; identify the owner first "
              "(netstat -ano) or choose another port with --port")
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    log_path = out_path.with_name(out_path.stem + "_server.log")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    print(f"starting server on 127.0.0.1:{args.port} (log: {log_path.name})")
    with open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "src.call_server",
             "--host", "127.0.0.1", "--port", str(args.port), "--warm", *args.langs],
            cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            health = wait_health(args.port)
            print(f"server up: llm={health.get('llm', {}).get('backend')} "
                  f"threads stt={config.STT_NUM_THREADS} tts={config.TTS_NUM_THREADS}")
            with RSSSampler(proc.pid) as rss:
                started = time.strftime("%Y-%m-%dT%H:%M:%S")
                data = asyncio.run(drive(args))
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

    turns = data["turns"]
    ok_turns = [t for t in turns if t.get("ok")]
    per_lang = {}
    for lang in args.langs:
        lang_turns = [t for t in ok_turns if t["lang"] == lang]
        per_lang[lang] = {
            metric: stats([t[metric] for t in lang_turns if metric in t])
            for metric in ("e2e_client_ms", "first_audio_ms", "asr_ms",
                           "llm_ms", "llm_ttft_ms", "tts_ms")
        }
        strategies: dict[str, int] = {}
        for t in lang_turns:
            key = t.get("asr_strategy", "unknown")
            strategies[key] = strategies.get(key, 0) + 1
        per_lang[lang]["asr_strategy_counts"] = strategies
        per_lang[lang]["failed_turns"] = sum(
            1 for t in turns if t["lang"] == lang and not t.get("ok"))
    report = {
        "benchmark": "latency_v3",
        "started": started,
        "machine": {"platform": sys.platform, "cpu_count": os.cpu_count()},
        "config": {
            "langs": args.langs, "turns_per_lang": args.turns,
            "streaming": True, "backchannel": False,
            "stt_threads": config.STT_NUM_THREADS,
            "tts_threads": config.TTS_NUM_THREADS,
            "endpoint_override_s": args.endpoint,
            "endpoint_default_s": {l: config.endpoint_for(l) for l in args.langs},
            "endpoint_note": "e2e_client_ms includes the endpoint-silence wait "
                             "plus localhost transport; stage timings overlap "
                             "and are never summed",
        },
        "corpus": "TTS-synthesized starter clips (eval_data/), NOT real recordings",
        "llm": health.get("llm"),
        "server_rss": rss_summary,
        "per_lang": per_lang,
        "turns": turns,
    }
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out_path}")
    for lang, metrics in per_lang.items():
        e2e = metrics["e2e_client_ms"]
        ttft = metrics["llm_ttft_ms"]
        print(f"{lang}: n={e2e['n']} e2e p50={e2e['p50']} p90={e2e['p90']} "
              f"p95={e2e['p95']} ms | ttft p50={ttft['p50']} ms; "
              f"failed={metrics['failed_turns']}")
    return 0 if ok_turns else 1


if __name__ == "__main__":
    sys.exit(main())