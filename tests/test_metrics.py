"""Regression tests for the /metrics operational endpoint (V2 Phase G/J).

Model-free: create_app with a stub LLM loads no models, so these run in the
fast CI tier. Verifies fail-closed auth, the metric shape, and that no
transcript/audio/client-IP data is exposed.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
import unittest
from unittest import mock

import aiohttp
import uvicorn

from src import config
from src.call_server import create_app


class StubLLM:
    backend = "stub"
    model = "stub-1"

    def warm(self):
        pass

    def abort_active(self):
        pass

    def stream_chat(self, messages):
        yield "ok"

    def reply(self, messages):
        return "ok"


class MetricsTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
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
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=10)

    async def _get(self, path):
        async with aiohttp.ClientSession() as s:
            async with s.get(self.base + path) as r:
                return r.status, await r.json()

    async def test_open_dev_metrics_shape_and_privacy(self):
        with mock.patch.object(config, "ACCESS_TOKEN", ""):
            status, body = await self._get("/metrics")
        self.assertEqual(status, 200)
        for key in ("active_sessions", "client_ips", "outbound_queue_total",
                    "outbound_queue_max", "asr_executor_queue",
                    "event_loop_delay_ms", "uptime_s", "rss_mb", "caps", "privacy"):
            self.assertIn(key, body)
        self.assertEqual(body["active_sessions"], 0)
        self.assertGreaterEqual(body["event_loop_delay_ms"], 0)
        self.assertIn("no transcripts", body["privacy"])
        # privacy: no transcript/audio/IP-bearing fields
        blob = json.dumps(body)
        self.assertNotIn("transcript", blob.replace("no transcripts", ""))
        self.assertNotIn("127.0.0.1", blob)
        self.assertEqual(body["caps"]["max_sessions_per_ip"], 8)

    async def test_token_required_when_configured(self):
        with mock.patch.object(config, "ACCESS_TOKEN", "secret-token"):
            s_none, _ = await self._get("/metrics")
            s_wrong, _ = await self._get("/metrics?token=wrong")
            s_ok, body = await self._get("/metrics?token=secret-token")
        self.assertEqual(s_none, 401)
        self.assertEqual(s_wrong, 401)
        self.assertEqual(s_ok, 200)
        self.assertIn("active_sessions", body)

    async def test_metrics_does_not_consume_tickets(self):
        # metrics gates on the long-lived token only; it must not touch the
        # single-use ticket store (a monitor polling should not burn tickets)
        from src import call_server
        with mock.patch.object(config, "ACCESS_TOKEN", "secret-token"):
            call_server._tickets["keep-me"] = time.time() + 60
            await self._get("/metrics?token=secret-token")
            self.assertIn("keep-me", call_server._tickets)
            call_server._tickets.pop("keep-me", None)


if __name__ == "__main__":
    unittest.main()