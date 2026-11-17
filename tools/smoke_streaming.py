"""Smoke test: stream a real recording into the live call server both ways.

    python -m src.call_server --port 8000          # in another terminal
    python tools/smoke_streaming.py eval_data/hi_01.wav hi

Prints the transcript, ASR mode/strategy and the server's latency event for
streaming and block mode, so the two can be compared on the same audio.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aiohttp

from src.evaluate import read_wav


async def one_run(wav: Path, lang: str, streaming: bool, server: str) -> dict:
    audio = read_wav(wav)
    pcm = (audio * 32767).astype("<i2")
    frame = 320  # 20 ms at 16 kHz
    silence = b"\x00" * (frame * 2) * 50  # 1 s of trailing silence
    url = server.replace("http", "ws", 1).rstrip("/")
    url += f"/ws/voice?lang={lang}&backchannel=0&streaming={'1' if streaming else '0'}"

    events: list[dict] = []
    audio_back = 0
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(url, max_msg_size=0) as ws:
            async def send():
                for i in range(0, len(pcm), frame):
                    await ws.send_bytes(pcm[i : i + frame].tobytes())
                    await asyncio.sleep(0.02)
                for _ in range(50):
                    await ws.send_bytes(silence)
                    await asyncio.sleep(0.02)

            sender = asyncio.create_task(send())
            deadline = time.perf_counter() + 45
            quiet = time.perf_counter()
            while time.perf_counter() < deadline:
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=2.0)
                except asyncio.TimeoutError:
                    if audio_back and time.perf_counter() - quiet > 3.0:
                        break
                    continue
                if msg.type == aiohttp.WSMsgType.BINARY:
                    audio_back += len(msg.data)
                    quiet = time.perf_counter()
                elif msg.type == aiohttp.WSMsgType.TEXT:
                    event = json.loads(msg.data)
                    events.append(event)
                    if event.get("type") == "latency" and audio_back:
                        break
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
            sender.cancel()
    return {"events": events, "audio_bytes": audio_back}


async def main() -> None:
    wav = Path(sys.argv[1] if len(sys.argv) > 1 else "eval_data/hi_01.wav")
    lang = sys.argv[2] if len(sys.argv) > 2 else "hi"
    server = sys.argv[3] if len(sys.argv) > 3 else "http://127.0.0.1:8000"
    for streaming in (True, False):
        result = await one_run(wav, lang, streaming, server)
        mode = "streaming" if streaming else "block"
        print(f"\n=== {mode} ===")
        for event in result["events"]:
            kind = event.get("type")
            if kind == "partial_transcript":
                print(f"  partial: {event['text']}")
            elif kind == "transcript":
                print(f"  transcript: {event['text']}  "
                      f"(asr={event['asr_ms']}ms mode={event.get('asr_mode', 'block')} "
                      f"strategy={event.get('asr_strategy', '-')})")
            elif kind == "latency":
                print(f"  latency: {event}")
            elif kind == "reply":
                print(f"  reply: {event['text']}")
        print(f"  audio back: {result['audio_bytes']} bytes")


if __name__ == "__main__":
    asyncio.run(main())