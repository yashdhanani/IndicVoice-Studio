"""WebSocket integration tests against a real uvicorn server in a thread.

Uses the real local hi ASR + tiny TTS models and a stub LLM, so no cloud
calls are made. Covers: streaming and block turns end-to-end, token auth
(4401), ASR-error survival (D1), the telephony mu-law path, and the idle
watchdog (4408).
"""
import asyncio
import base64
import json
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import aiohttp
import numpy as np
import uvicorn

from src import config
from src.call_server import create_app, resample, ulaw_encode
from src.evaluate import read_wav
from src.sts_pipeline import STTEngine

ROOT = Path(__file__).resolve().parent.parent
WAV = ROOT / "eval_data" / "hi_01.wav"


class StubLLM:
    backend = "stub"
    model = "stub-1"

    def warm(self):
        pass

    def abort_active(self):
        pass

    def stream_chat(self, messages):
        yield "आपका ऑर्डर कल तक पहुँच जाएगा।"

    def reply(self, messages):
        return "आपका ऑर्डर कल तक पहुँच जाएगा।"


class WSTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.audio = read_wav(WAV)
        cls.pcm = (cls.audio * 32767).astype("<i2")
        app = create_app(agent_factory=StubLLM, streaming=True)
        cfg = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
        cls.server = uvicorn.Server(cfg)
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        deadline = time.perf_counter() + 30
        while not cls.server.started and time.perf_counter() < deadline:
            time.sleep(0.05)
        if not cls.server.started:
            raise RuntimeError("test server did not start")
        cls.port = cls.server.servers[0].sockets[0].getsockname()[1]
        cls.base = f"ws://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=10)

    async def _run_turn(self, path, pcm=None, timeout=30):
        """Feed audio at real-time pace + 1 s silence; collect events/audio."""
        pcm = self.pcm if pcm is None else pcm
        events, audio_bytes = [], 0
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(self.base + path, max_msg_size=0) as ws:
                async def send():
                    for i in range(0, len(pcm), 320):
                        await ws.send_bytes(pcm[i:i + 320].tobytes())
                        await asyncio.sleep(0.02)
                    for _ in range(50):
                        await ws.send_bytes(b"\x00" * 640)
                        await asyncio.sleep(0.02)

                sender = asyncio.create_task(send())
                deadline = time.perf_counter() + timeout
                got_latency = False
                while time.perf_counter() < deadline:
                    try:
                        msg = await asyncio.wait_for(ws.receive(), timeout=1.0)
                    except asyncio.TimeoutError:
                        if got_latency and audio_bytes:
                            break
                        continue
                    if msg.type == aiohttp.WSMsgType.BINARY:
                        audio_bytes += len(msg.data)
                    elif msg.type == aiohttp.WSMsgType.TEXT:
                        event = json.loads(msg.data)
                        events.append(event)
                        if event.get("type") == "latency" and audio_bytes:
                            got_latency = True
                            break
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break
                sender.cancel()
        return events, audio_bytes

    async def test_streaming_turn_end_to_end(self):
        events, audio_bytes = await self._run_turn("/ws/voice?lang=hi&backchannel=0")
        kinds = [e.get("type") for e in events]
        self.assertIn("partial_transcript", kinds)
        transcripts = [e for e in events if e.get("type") == "transcript"]
        self.assertEqual(len(transcripts), 1)
        self.assertTrue(transcripts[0]["text"])
        self.assertEqual(transcripts[0].get("asr_mode"), "streaming")
        self.assertIn(transcripts[0].get("asr_strategy"),
                      ("speculative", "full", "cloud"))
        self.assertIn("reply", kinds)
        self.assertIn("latency", kinds)
        latency = next(e for e in events if e.get("type") == "latency")
        self.assertGreater(latency["first_audio_ms"], 0)
        self.assertGreater(audio_bytes, 0)

    async def test_block_turn_end_to_end(self):
        events, audio_bytes = await self._run_turn(
            "/ws/voice?lang=hi&backchannel=0&streaming=0")
        transcripts = [e for e in events if e.get("type") == "transcript"]
        self.assertEqual(len(transcripts), 1)
        self.assertTrue(transcripts[0]["text"])
        self.assertNotIn("asr_mode", transcripts[0])
        self.assertNotIn("partial_transcript", [e.get("type") for e in events])
        self.assertGreater(audio_bytes, 0)

    async def test_token_auth(self):
        with mock.patch.object(config, "ACCESS_TOKEN", "test-secret-token"):
            async with aiohttp.ClientSession() as session:
                ws = await session.ws_connect(self.base + "/ws/voice?lang=hi")
                msg = await asyncio.wait_for(ws.receive(), timeout=5)
                self.assertEqual(msg.type, aiohttp.WSMsgType.CLOSE)
                self.assertEqual(msg.data, 4401)
                await ws.close()

                ws = await session.ws_connect(
                    self.base + "/ws/voice?lang=hi&token=test-secret-token")
                await ws.send_bytes(b"\x00" * 640)
                await asyncio.sleep(0.3)
                self.assertFalse(ws.closed)
                await ws.close()

    async def test_asr_error_does_not_drop_call(self):
        # D1 regression: a decode exception must produce an error event and
        # leave the socket usable for the next turn
        with mock.patch.object(STTEngine, "transcribe",
                               side_effect=RuntimeError("boom")):
            events, _ = await self._run_turn(
                "/ws/voice?lang=hi&backchannel=0&streaming=0", timeout=20)
        errors = [e for e in events if e.get("type") == "error"]
        self.assertTrue(errors)
        self.assertEqual(errors[0]["stage"], "asr")
        self.assertNotIn("transcript", [e.get("type") for e in events])
        # same server, next turn works
        events, audio_bytes = await self._run_turn(
            "/ws/voice?lang=hi&backchannel=0&streaming=0")
        self.assertIn("transcript", [e.get("type") for e in events])
        self.assertGreater(audio_bytes, 0)

    async def test_telephony_mulaw_turn(self):
        audio8k = resample(self.audio, 16000, 8000)
        payload = ulaw_encode(audio8k)
        silence = ulaw_encode(np.zeros(160, dtype=np.float32))
        events, media_frames = [], 0
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                self.base + "/ws/telephony?lang=hi&backchannel=0&streaming=0",
                max_msg_size=0,
            ) as ws:
                first = json.loads((await asyncio.wait_for(ws.receive(), 5)).data)
                self.assertEqual(first.get("event"), "connected")

                async def send():
                    for i in range(0, len(payload), 160):
                        frame = payload[i:i + 160]
                        await ws.send_str(json.dumps(
                            {"event": "media", "media": {"payload":
                             base64.b64encode(frame).decode()}}))
                        await asyncio.sleep(0.02)
                    for _ in range(50):
                        await ws.send_str(json.dumps(
                            {"event": "media", "media": {"payload":
                             base64.b64encode(silence).decode()}}))
                        await asyncio.sleep(0.02)

                sender = asyncio.create_task(send())
                deadline = time.perf_counter() + 30
                while time.perf_counter() < deadline:
                    try:
                        msg = await asyncio.wait_for(ws.receive(), timeout=1.0)
                    except asyncio.TimeoutError:
                        if media_frames and any(
                                e.get("type") == "latency" for e in events):
                            break
                        continue
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        break
                    event = json.loads(msg.data)
                    if event.get("event") == "media":
                        media_frames += 1
                        raw = base64.b64decode(event["media"]["payload"])
                        self.assertEqual(len(raw), 160)  # 20 ms at 8 kHz
                    else:
                        events.append(event)
                        if event.get("type") == "latency" and media_frames:
                            break
                sender.cancel()
        self.assertIn("transcript", [e.get("type") for e in events])
        self.assertGreater(media_frames, 0)

    async def test_idle_watchdog_closes_4408(self):
        with mock.patch.object(config, "SESSION_IDLE_SECONDS", 1.0):
            async with aiohttp.ClientSession() as session:
                ws = await session.ws_connect(self.base + "/ws/voice?lang=hi")
                msg = await asyncio.wait_for(ws.receive(), timeout=12)
                self.assertEqual(msg.type, aiohttp.WSMsgType.CLOSE)
                self.assertEqual(msg.data, 4408)


if __name__ == "__main__":
    unittest.main()