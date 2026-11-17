"""WebSocket integration tests against a real uvicorn server in a thread.

Uses the real local hi ASR + tiny TTS models and a stub LLM, so no cloud
calls are made. Covers: streaming and block turns end-to-end, token auth
(4401), ASR-error survival (D1), the telephony mu-law path, and the idle
watchdog (4408).
"""
import asyncio
import base64
import json
import queue
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import aiohttp
import numpy as np
import uvicorn

from src import config
from src.call_server import (
    MAX_SESSIONS_PER_IP,
    _bind_security_error,
    create_app,
    resample,
    ulaw_encode,
)
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
        # fast CI tier: these tests need local models + starter clips, which
        # are git-ignored; skip (never silently pass) when they are absent
        models_present = (
            Path(config.VAD_PATH).exists()
            and (config.tts_model_dir("hi") / "model.onnx").exists()
            and config.has_indic_asr("hi")
        )
        if not models_present or not WAV.exists():
            raise unittest.SkipTest("local hi models / starter WAVs not present")
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

    # -- Production Hardening V1: P0 security gates -------------------------- #

    async def _expect_close(self, path, code, headers=None, send=None):
        async with aiohttp.ClientSession() as session:
            ws = await session.ws_connect(self.base + path, headers=headers or {})
            if send is not None:
                await send(ws)
            deadline = time.perf_counter() + 10
            while time.perf_counter() < deadline:
                msg = await asyncio.wait_for(ws.receive(), timeout=10)
                if msg.type == aiohttp.WSMsgType.TEXT:
                    continue  # e.g. telephony "connected" before the close
                self.assertEqual(msg.type, aiohttp.WSMsgType.CLOSE)
                self.assertEqual(msg.data, code)
                return
            self.fail(f"no close frame with code {code}")

    async def test_foreign_origin_rejected(self):
        await self._expect_close(
            "/ws/voice?lang=hi", 4403, headers={"Origin": "http://evil.example"})

    async def test_localhost_origin_allowed(self):
        async with aiohttp.ClientSession() as session:
            ws = await session.ws_connect(
                self.base + "/ws/voice?lang=hi",
                headers={"Origin": f"http://127.0.0.1:{self.port}"})
            await ws.send_bytes(b"\x00" * 640)
            await asyncio.sleep(0.3)
            self.assertFalse(ws.closed)
            await ws.close()

    async def test_allowlisted_origin_allowed(self):
        with mock.patch.object(config, "ALLOWED_ORIGINS", ("https://calls.example.com",)):
            async with aiohttp.ClientSession() as session:
                ws = await session.ws_connect(
                    self.base + "/ws/voice?lang=hi",
                    headers={"Origin": "https://calls.example.com"})
                await ws.send_bytes(b"\x00" * 640)
                await asyncio.sleep(0.3)
                self.assertFalse(ws.closed)
                await ws.close()

    async def test_oversized_voice_frame_closes_1009(self):
        async def send(ws):
            await ws.send_bytes(b"\x00" * 70000)
        await self._expect_close("/ws/voice?lang=hi", 1009, send=send)

    async def test_oversized_telephony_payload_closes_1009(self):
        async def send(ws):
            await ws.send_str(json.dumps(
                {"event": "media", "media": {"payload": "A" * 40000}}))
        await self._expect_close("/ws/telephony?lang=hi", 1009, send=send)

    async def test_malformed_telephony_json_closes_1003(self):
        async def send(ws):
            await ws.send_str("this is not json")
        await self._expect_close("/ws/telephony?lang=hi", 1003, send=send)

    async def test_per_ip_session_limit(self):
        async with aiohttp.ClientSession() as session:
            held = []
            try:
                for _ in range(MAX_SESSIONS_PER_IP):
                    held.append(await session.ws_connect(self.base + "/ws/voice?lang=hi"))
                ws = await session.ws_connect(self.base + "/ws/voice?lang=hi")
                msg = await asyncio.wait_for(ws.receive(), timeout=10)
                self.assertEqual(msg.type, aiohttp.WSMsgType.CLOSE)
                self.assertEqual(msg.data, 4429)
            finally:
                for ws in held:
                    await ws.close()
            # slots are released on disconnect
            await asyncio.sleep(0.5)
            ws = await session.ws_connect(self.base + "/ws/voice?lang=hi")
            await ws.send_bytes(b"\x00" * 640)
            await asyncio.sleep(0.3)
            self.assertFalse(ws.closed)
            await ws.close()

    # -- Production Hardening V1: B1/B2/B5 ----------------------------------- #

    async def test_empty_and_invalid_token_rejected(self):
        with mock.patch.object(config, "ACCESS_TOKEN", "test-secret-token"):
            await self._expect_close("/ws/voice?lang=hi&token=", 4401)
            await self._expect_close("/ws/voice?lang=hi&token=wrong", 4401)

    async def _post_ticket(self, session, headers=None):
        return await session.post(
            f"http://127.0.0.1:{self.port}/auth/ticket", headers=headers or {})

    async def test_ticket_endpoint_auth(self):
        with mock.patch.object(config, "ACCESS_TOKEN", "test-secret-token"):
            async with aiohttp.ClientSession() as session:
                r = await self._post_ticket(session)
                self.assertEqual(r.status, 401)
                r = await self._post_ticket(
                    session, {"Authorization": "Bearer wrong"})
                self.assertEqual(r.status, 401)
                r = await self._post_ticket(
                    session, {"Authorization": "Bearer test-secret-token"})
                self.assertEqual(r.status, 200)
                body = await r.json()
                self.assertTrue(body["ticket"])
                self.assertGreater(body["expires_in"], 0)

    async def test_ticket_single_use(self):
        with mock.patch.object(config, "ACCESS_TOKEN", "test-secret-token"):
            async with aiohttp.ClientSession() as session:
                r = await self._post_ticket(
                    session, {"Authorization": "Bearer test-secret-token"})
                ticket = (await r.json())["ticket"]
                ws = await session.ws_connect(
                    self.base + f"/ws/voice?lang=hi&ticket={ticket}")
                await ws.send_bytes(b"\x00" * 640)
                await asyncio.sleep(0.3)
                self.assertFalse(ws.closed)
                await ws.close()
            # the same ticket must not open a second session
            await self._expect_close(f"/ws/voice?lang=hi&ticket={ticket}", 4401)

    async def test_expired_ticket_rejected(self):
        with mock.patch.object(config, "ACCESS_TOKEN", "test-secret-token"), \
                mock.patch.object(config, "TICKET_TTL_SECONDS", 0.0):
            async with aiohttp.ClientSession() as session:
                r = await self._post_ticket(
                    session, {"Authorization": "Bearer test-secret-token"})
                ticket = (await r.json())["ticket"]
            await self._expect_close(f"/ws/voice?lang=hi&ticket={ticket}", 4401)

    async def test_ticket_endpoint_needs_token_configured(self):
        with mock.patch.object(config, "ACCESS_TOKEN", ""):
            async with aiohttp.ClientSession() as session:
                r = await self._post_ticket(
                    session, {"Authorization": "Bearer anything"})
                self.assertEqual(r.status, 400)

    async def test_health_reports_auth_mode(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{self.port}/health") as r:
                self.assertEqual((await r.json())["auth"], "open-dev")
            with mock.patch.object(config, "ACCESS_TOKEN", "x"):
                async with session.get(f"http://127.0.0.1:{self.port}/health") as r:
                    self.assertEqual((await r.json())["auth"], "token")

    async def test_max_session_duration_closes_4410(self):
        with mock.patch.object(config, "MAX_SESSION_SECONDS", 0.5):
            async with aiohttp.ClientSession() as session:
                ws = await session.ws_connect(self.base + "/ws/voice?lang=hi")
                msg = await asyncio.wait_for(ws.receive(), timeout=12)
                self.assertEqual(msg.type, aiohttp.WSMsgType.CLOSE)
                self.assertEqual(msg.data, 4410)


class TestOutboundQueueCap(unittest.TestCase):
    def test_full_queue_closes_session(self):
        from src.call_server import CallSession
        s = CallSession.__new__(CallSession)
        s.closed = False
        s.out = queue.Queue(maxsize=1)
        s.close = lambda: setattr(s, "closed", True)
        s._put(b"first")
        self.assertFalse(s.closed)
        s._put(b"second")
        self.assertTrue(s.closed)


class TestBindSecurity(unittest.TestCase):
    def test_non_localhost_without_token_fails_closed(self):
        for host in ("0.0.0.0", "192.168.1.5", "10.0.0.2"):
            self.assertIsNotNone(_bind_security_error(host, ""))

    def test_non_localhost_with_token_ok(self):
        self.assertIsNone(_bind_security_error("0.0.0.0", "secret"))

    def test_localhost_open_ok(self):
        for host in ("127.0.0.1", "localhost", "::1"):
            self.assertIsNone(_bind_security_error(host, ""))

    def test_main_refuses_insecure_bind(self):
        from src.call_server import main
        with mock.patch.object(config, "ACCESS_TOKEN", ""):
            self.assertEqual(main(["--host", "0.0.0.0", "--no-warm"]), 1)


if __name__ == "__main__":
    unittest.main()