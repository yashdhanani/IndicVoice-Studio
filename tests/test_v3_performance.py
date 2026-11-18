"""V3 Phase B regression tests: thread knobs, amortised audio buffer,
event-driven sender and the dedicated ASR executor.

Model-free where possible (fast CI tier); the tiny-TTS loader test injects a
fake module so no onnxruntime session is created.
"""
from __future__ import annotations

import asyncio
import os
import queue
import subprocess
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import numpy as np

from src import config
from src.call_server import CallSession, create_app
from src.streaming_stt import StreamingSTT

ROOT = Path(__file__).resolve().parent.parent
RATE = 16000


class RecordingEngine:
    """Fake engine that records length + checksum of every decode's audio."""

    backend = "indic"

    def __init__(self, delay=0.0, text="ok"):
        self.delay = delay
        self.text = text
        self.calls: list[tuple[int, float]] = []
        self._lock = threading.Lock()

    def transcribe(self, samples, sample_rate=RATE):
        with self._lock:
            self.calls.append((len(samples), float(np.sum(samples))))
        if self.delay:
            time.sleep(self.delay)
        return self.text


class BufferGrowthTests(unittest.TestCase):
    def setUp(self):
        self.streamer = StreamingSTT()

    def tearDown(self):
        self.streamer.close()

    def test_appends_preserve_exact_content(self):
        rng = np.random.default_rng(7)
        chunks = [rng.standard_normal(320).astype(np.float32) for _ in range(200)]
        self.streamer.start(RecordingEngine())
        for chunk in chunks:
            self.streamer.accept(chunk)
        expected = np.concatenate(chunks)
        np.testing.assert_array_equal(self.streamer._buf, expected)
        self.assertGreaterEqual(len(self.streamer._storage), len(expected))

    def test_seed_then_growth_preserves_content(self):
        seed = np.full(1600, 0.25, dtype=np.float32)
        self.streamer.start(RecordingEngine(), seed=seed)
        tail = np.full(3200, -0.5, dtype=np.float32)
        for i in range(0, len(tail), 320):
            self.streamer.accept(tail[i:i + 320])
        np.testing.assert_array_equal(self.streamer._buf, np.concatenate([seed, tail]))

    def test_finalize_detaches_store_from_next_utterance(self):
        # a slow decode holds the old buffer; the next utterance must not
        # overwrite samples while that decode is still running
        engine = RecordingEngine(delay=0.4)
        self.streamer.start(engine)
        loud = np.full(RATE, 0.3, dtype=np.float32)
        for i in range(0, len(loud), 320):
            self.streamer.accept(loud[i:i + 320])
        result = {}

        def finalize():
            result["text"], result["info"] = self.streamer.finalize()

        worker = threading.Thread(target=finalize)
        worker.start()
        time.sleep(0.1)                      # decode is now in flight
        self.streamer.start(RecordingEngine())
        other = np.full(RATE, -0.9, dtype=np.float32)
        for i in range(0, len(other), 320):
            self.streamer.accept(other[i:i + 320])
        worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result["text"], "ok")
        length, checksum = engine.calls[-1]
        self.assertEqual(length, RATE)
        self.assertAlmostEqual(checksum, 0.3 * RATE, places=2)

    def test_cancel_resets_storage(self):
        self.streamer.start(RecordingEngine())
        self.streamer.accept(np.full(3200, 0.5, dtype=np.float32))
        self.streamer.cancel()
        self.assertEqual(len(self.streamer._buf), 0)
        self.streamer.start(RecordingEngine())
        self.streamer.accept(np.full(320, 0.1, dtype=np.float32))
        np.testing.assert_array_equal(self.streamer._buf, np.full(320, 0.1, dtype=np.float32))


class FakeWS:
    def __init__(self):
        self.sent = []

    async def send_text(self, text):
        self.sent.append(("text", text))

    async def send_bytes(self, data):
        self.sent.append(("bytes", data))


def bare_session(loop) -> CallSession:
    s = CallSession.__new__(CallSession)
    s.out = queue.Queue(maxsize=4096)
    s.closed = False
    s._wake = asyncio.Event()
    s.loop = loop
    s.ws = FakeWS()
    s.mode = "browser"
    return s


class SenderTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_thread_puts_are_delivered_without_executor(self):
        loop = asyncio.get_running_loop()
        s = bare_session(loop)
        task = asyncio.create_task(s.sender())
        done = threading.Event()

        def produce():
            for i in range(50):
                s._put({"type": "reply", "text": str(i)})
            done.set()

        threading.Thread(target=produce, daemon=True).start()
        deadline = time.perf_counter() + 5
        while len(s.ws.sent) < 50 and time.perf_counter() < deadline:
            await asyncio.sleep(0.01)
        self.assertTrue(done.is_set())
        self.assertEqual(len(s.ws.sent), 50)
        # the sender must not occupy the default executor (the V2 defect)
        self.assertIsNone(getattr(loop, "_default_executor", None))
        s.closed = True
        s._signal()
        await asyncio.wait_for(task, timeout=2)

    async def test_close_wakes_blocked_sender(self):
        s = bare_session(asyncio.get_running_loop())
        task = asyncio.create_task(s.sender())
        await asyncio.sleep(0.05)            # sender is now parked on _wake
        s.closed = True
        s._signal()
        await asyncio.wait_for(task, timeout=2)
        self.assertTrue(task.done())

    async def test_binary_audio_delivered(self):
        s = bare_session(asyncio.get_running_loop())
        task = asyncio.create_task(s.sender())
        s._put(b"\x01\x02\x03\x04")
        deadline = time.perf_counter() + 2
        while not s.ws.sent and time.perf_counter() < deadline:
            await asyncio.sleep(0.01)
        self.assertEqual(s.ws.sent, [("bytes", b"\x01\x02\x03\x04")])
        s.closed = True
        s._signal()
        await asyncio.wait_for(task, timeout=2)

    async def test_full_queue_still_closes_session(self):
        s = bare_session(asyncio.get_running_loop())
        s.out = queue.Queue(maxsize=1)
        closed = []
        s.close = lambda: closed.append(True)
        s._put(b"first")
        s._put(b"second")
        self.assertEqual(closed, [True])


class LifespanExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def test_lifespan_creates_and_shuts_down_asr_pool(self):
        app = create_app()
        async with app.router.lifespan_context(app):
            executor = app.state.asr_executor
            self.assertIsInstance(executor, ThreadPoolExecutor)
            self.assertEqual(executor._max_workers, max(1, config.ASR_WORKERS))
        self.assertTrue(executor._shutdown)

    async def test_dedicated_pool_queues_beyond_workers(self):
        # the asr_executor_queue gauge reads this pool's work queue; prove it
        # actually accumulates when all workers are busy
        app = create_app()
        async with app.router.lifespan_context(app):
            ex = app.state.asr_executor
            release = threading.Event()
            try:
                for _ in range(ex._max_workers + 2):
                    ex.submit(release.wait, 5)
                deadline = time.perf_counter() + 3
                while ex._work_queue.qsize() < 2 and time.perf_counter() < deadline:
                    await asyncio.sleep(0.01)
                self.assertGreaterEqual(ex._work_queue.qsize(), 2)
            finally:
                release.set()


class ConfigKnobTests(unittest.TestCase):
    def test_env_overrides(self):
        env = {**os.environ, "INDICVOICE_STT_THREADS": "3",
               "INDICVOICE_TTS_THREADS": "2", "INDICVOICE_ASR_WORKERS": "1",
               "PYTHONIOENCODING": "utf-8"}
        out = subprocess.run(
            [sys.executable, "-c",
             "from src import config; print(config.STT_NUM_THREADS, "
             "config.TTS_NUM_THREADS, config.ASR_WORKERS)"],
            cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), "3 2 1")

    def test_defaults_are_sane(self):
        self.assertGreaterEqual(config.STT_NUM_THREADS, 1)
        self.assertGreaterEqual(config.TTS_NUM_THREADS, 0)
        self.assertGreaterEqual(config.ASR_WORKERS, 1)


class LatencyEventTests(unittest.TestCase):
    """Phase C: llm_ttft_ms must measure request-start -> first token, not
    speech-end -> first token (which includes the ASR->LLM handoff)."""

    def _emit(self, marks, now=1001.0):
        import types
        from src import call_server
        s = CallSession.__new__(CallSession)
        s.out = queue.Queue(maxsize=16)
        s.closed = False
        s.mode = "browser"
        s.agent = types.SimpleNamespace(marks=marks)
        s._turn = {"asr_ms": 120.0, "t_speech_end": 1000.0}
        with mock.patch.object(call_server.time, "perf_counter", return_value=now):
            s._emit_audio(np.zeros(160, dtype=np.float32))
        items = [s.out.get_nowait() for _ in range(s.out.qsize())]
        return next(e for e in items
                    if isinstance(e, dict) and e.get("type") == "latency")

    def test_ttft_is_request_to_first_token(self):
        lat = self._emit({"llm_request": 1000.2, "llm_first": 1000.7,
                          "tts_start": 1000.8})
        self.assertEqual(lat["llm_ttft_ms"], 500.0)
        self.assertEqual(lat["llm_ms"], 700.0)
        self.assertEqual(lat["tts_ms"], 200.0)
        self.assertEqual(lat["first_audio_ms"], 1000.0)

    def test_missing_request_mark_reports_none_not_fake(self):
        lat = self._emit({"llm_first": 1000.7, "tts_start": 1000.8})
        self.assertIsNone(lat["llm_ttft_ms"])
        self.assertEqual(lat["llm_ms"], 700.0)


class TinyThreadRoutingTests(unittest.TestCase):
    def test_tiny_loader_uses_knob_not_sherpa_arg_and_caches(self):
        import types
        captured = []

        class FakeTiny:
            sample_rate = 24000

            @classmethod
            def from_pretrained(cls, path, threads=None, **kw):
                captured.append(threads)
                return cls()

        fake = types.ModuleType("indic_tiny_tts")
        fake.TinyTTSOnnx = FakeTiny
        from src import tts_engine
        # patch.dict(sys.modules) drops every module first imported INSIDE the
        # context on exit; sherpa's C extension cannot re-initialise in the same
        # process ("type already registered"), so snapshot it before patching.
        import sherpa_onnx  # noqa: F401
        key = ("hi", "tiny", 2, "cpu", "")
        tts_engine._TTS_CACHE.pop(key, None)
        with mock.patch.dict(sys.modules, {"indic_tiny_tts": fake}), \
                mock.patch.object(config, "TTS_NUM_THREADS", 2):
            shared = tts_engine._build_shared_tts("hi", "tiny", 4, "cpu")
            again = tts_engine._build_shared_tts("hi", "tiny", 8, "cpu")
        try:
            self.assertEqual(captured, [2])     # knob wins over sherpa arg
            self.assertIs(shared, again)        # one load per knob value
        finally:
            tts_engine._TTS_CACHE.pop(key, None)


if __name__ == "__main__":
    unittest.main()