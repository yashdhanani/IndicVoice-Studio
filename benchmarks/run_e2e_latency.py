"""End-to-end first-audio latency benchmark (Production Hardening V1, Phase F).

Starts a real call server (real ASR + configured LLM + real TTS, no stubs)
on a free localhost port, drives sequential real-time turns from the
synthetic starter corpus, and measures:

  e2e_client_ms   last speech frame sent -> first audio byte received
                  (includes the endpoint-silence wait; this is what a caller
                  experiences after they stop talking)
  first_audio_ms  server-side: end-of-speech -> first audio emitted
  asr_ms / llm_ms / tts_ms   server-reported stage timings

Stage timings OVERLAP in the streaming pipeline (LLM socket warm-up, TTS
starts on the first sentence while ASR stats are already reported); they are
reported separately and never summed into an "E2E" number.

Corpus caveat: eval_data/*.wav are TTS-synthesized starter clips, NOT real
human recordings. Results describe pipeline latency on this machine, not
real-world acoustic robustness.

Usage:
    python benchmarks/run_e2e_latency.py --langs hi en --turns 20
    python benchmarks/run_e2e_latency.py --port 8010 --out benchmarks/results/production_v1/e2e_v1.json

The script refuses to run if the chosen port is occupied, and only ever
terminates the server process it started itself.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import aiohttp  # noqa: E402

from src.evaluate import read_wav  # noqa: E402


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, int(round(pct / 100.0 * len(ordered) + 0.5)) - 1))
    return round(ordered[k], 1)


def stats(values: list[float]) -> dict:
    return {
        "n": len(values),
        "min": round(min(values), 1) if values else None,
        "p50": percentile(values, 50),
        "p90": percentile(values, 90),
        "p95": percentile(values, 95),
        "max": round(max(values), 1) if values else None,
        "mean": round(sum(values) / len(values), 1) if values else None,
    }


class RSSSampler:
    """Working-set sampler for the server process (no psutil dependency).

    On Windows the venv python.exe is a small launcher that spawns the real
    interpreter as a child; sampling the launcher would report ~6 MB instead
    of the model-loaded server. We follow the child when one exists.
    """

    def __init__(self, pid: int):
        self.pid = pid
        self.samples: list[tuple[float, float]] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._handle = None
        self._child_checked = False
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            self._pmc_cls = PMC
            self._ctypes = ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.OpenProcess.restype = wintypes.HANDLE
            self._handle = kernel32.OpenProcess(0x0400 | 0x0010, False, pid)

    def _find_child(self) -> int | None:
        """First child process of self.pid (the venv launcher's interpreter)."""
        ctypes = self._ctypes
        from ctypes import wintypes

        class PE32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_wchar * 260),
            ]

        snap = ctypes.windll.kernel32.CreateToolhelp32Snapshot(0x2, 0)
        if not snap or snap == wintypes.HANDLE(-1).value:
            return None
        try:
            entry = PE32W()
            entry.dwSize = ctypes.sizeof(PE32W)
            ok = ctypes.windll.kernel32.Process32FirstW(snap, ctypes.byref(entry))
            while ok:
                if entry.th32ParentProcessID == self.pid:
                    return entry.th32ProcessID
                ok = ctypes.windll.kernel32.Process32NextW(snap, ctypes.byref(entry))
        finally:
            ctypes.windll.kernel32.CloseHandle(snap)
        return None

    def _read_mb(self) -> float | None:
        if sys.platform == "win32":
            if not self._child_checked:
                self._child_checked = True
                child = self._find_child()
                if child:
                    handle = self._ctypes.windll.kernel32.OpenProcess(
                        0x0400 | 0x0010, False, child)
                    if handle:
                        if self._handle:
                            self._ctypes.windll.kernel32.CloseHandle(self._handle)
                        self._handle = handle
                        self.pid = child
            if not self._handle:
                return None
            pmc = self._pmc_cls()
            pmc.cb = self._ctypes.sizeof(pmc)
            ok = self._ctypes.windll.psapi.GetProcessMemoryInfo(
                self._handle, self._ctypes.byref(pmc), pmc.cb)
            return pmc.WorkingSetSize / (1024 * 1024) if ok else None
        try:
            for line in Path(f"/proc/{self.pid}/status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
        except OSError:
            return None
        return None

    def _run(self):
        t0 = time.perf_counter()
        while not self._stop.is_set():
            mb = self._read_mb()
            if mb is not None:
                self.samples.append((round(time.perf_counter() - t0, 1), round(mb, 1)))
            self._stop.wait(2.0)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=3)
        if self._handle:
            self._ctypes.windll.kernel32.CloseHandle(self._handle)

    def summary(self) -> dict:
        if not self.samples:
            return {"available": False}
        values = [mb for _, mb in self.samples]
        return {
            "available": True,
            "peak_mb": round(max(values), 1),
            "final_mb": values[-1],
            "samples": len(values),
        }


async def run_turn(base: str, lang: str, wav: Path, turn_idx: int) -> dict:
    audio = read_wav(wav)
    pcm = (audio * 32767).astype("<i2")
    result: dict = {
        "lang": lang, "clip": wav.name, "turn": turn_idx,
        "audio_s": round(len(audio) / 16000.0, 2),
    }
    events: list[dict] = []
    t_first_audio = None
    t_last_speech = None
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(
            f"{base}/ws/voice?lang={lang}&backchannel=0", max_msg_size=0,
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
                    event = json.loads(msg.data)
                    events.append(event)
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
        for key in ("asr_ms", "llm_ms", "tts_ms", "first_audio_ms"):
            if latency.get(key) is not None:
                result[key] = latency[key]
    if transcript:
        result["transcript"] = transcript.get("text", "")
        result["asr_strategy"] = transcript.get("asr_strategy", "block")
    if errors:
        result["errors"] = [e.get("message", "")[:120] for e in errors]
    result["ok"] = bool(result.get("e2e_client_ms") and transcript and not errors)
    return result


def wait_health(port: int, timeout: float = 180.0) -> dict:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            time.sleep(1.0)
    raise RuntimeError(f"server on port {port} did not become healthy in {timeout}s")


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


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
                result = await run_turn(base, lang, wav, i + 1)
            except Exception as exc:                      # noqa: BLE001
                result = {"lang": lang, "clip": wav.name, "turn": i + 1,
                          "ok": False, "exception": str(exc)[:200]}
            turns.append(result)
            print(f"[{lang} {i + 1}/{args.turns}] "
                  f"e2e={result.get('e2e_client_ms')}ms "
                  f"first_audio={result.get('first_audio_ms')}ms "
                  f"asr={result.get('asr_ms')}ms "
                  f"strategy={result.get('asr_strategy')} "
                  f"ok={result.get('ok')} "
                  f"({time.perf_counter() - t0:.1f}s)")
    return {"turns": turns}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--langs", nargs="+", default=["hi", "en"])
    parser.add_argument("--turns", type=int, default=20, help="turns per language")
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--out", default=str(ROOT / "benchmarks" / "results" / "production_v1" / "e2e_v1.json"))
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
                  f"auth={health.get('auth')}")
            with RSSSampler(proc.pid) as rss:
                started = time.strftime("%Y-%m-%dT%H:%M:%S")
                data = asyncio.run(drive(args))
                rss_summary = rss.summary()
                rss_series = rss.samples
        finally:
            # Windows: the venv launcher's child must die too -> kill the tree
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
            for metric in ("e2e_client_ms", "first_audio_ms", "asr_ms", "llm_ms", "tts_ms")
        }
        per_lang[lang]["failed_turns"] = sum(
            1 for t in turns if t["lang"] == lang and not t.get("ok"))
    report = {
        "benchmark": "e2e_v1",
        "started": started,
        "machine": {"platform": sys.platform, "cpu_count": os.cpu_count()},
        "config": {"langs": args.langs, "turns_per_lang": args.turns,
                   "streaming": True, "backchannel": False,
                   "endpoint_note": "e2e_client_ms includes the endpoint-silence wait "
                                    "(0.26 s hi-family / 0.45 s en) plus localhost transport"},
        "corpus": "TTS-synthesized starter clips (eval_data/), NOT real recordings",
        "llm": health.get("llm"),
        "server_rss": rss_summary,
        "per_lang": per_lang,
        "turns": turns,
        "rss_series_mb": rss_series,
    }
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out_path}")
    for lang, metrics in per_lang.items():
        e2e = metrics["e2e_client_ms"]
        print(f"{lang}: n={e2e['n']} e2e p50={e2e['p50']} p90={e2e['p90']} "
              f"p95={e2e['p95']} ms; failed={metrics['failed_turns']}")
    return 0 if ok_turns else 1


if __name__ == "__main__":
    sys.exit(main())