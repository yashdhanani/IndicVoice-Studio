"""State-machine tests for StreamingSTT using a fake engine (no models needed).

Covers the three safety mechanisms measured into existence during the A/B
runs: predicted-cost partial gating, the finalize staleness guard, and
post-miss speculation suppression.
"""
import threading
import time
import unittest

import numpy as np

from src.streaming_stt import StreamingSTT

RATE = 16000
CHUNK = 320  # 20 ms


def loud(seconds, amp=0.3):
    return np.full(int(RATE * seconds), amp, dtype=np.float32)


def quiet(seconds, amp=0.005):
    return np.full(int(RATE * seconds), amp, dtype=np.float32)


def silence(seconds):
    return np.zeros(int(RATE * seconds), dtype=np.float32)


def feed(streamer, audio):
    for i in range(0, len(audio), CHUNK):
        streamer.accept(audio[i:i + CHUNK])


def feed_realtime(streamer, audio):
    """Pace like the server does; fast-feeding starves the decode worker."""
    for i in range(0, len(audio), CHUNK):
        streamer.accept(audio[i:i + CHUNK])
        time.sleep(0.02)


def wait_until(pred, timeout=5.0):
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return False


class FakeEngine:
    def __init__(self, delay=0.01, text="hello world", backend="indic"):
        self.delay = delay
        self.text = text
        self.backend = backend
        self.calls = []
        self._lock = threading.Lock()

    def transcribe(self, samples, sample_rate=RATE):
        with self._lock:
            self.calls.append(len(samples))
        time.sleep(self.delay)
        return self.text


class TestStreamingSTT(unittest.TestCase):
    def setUp(self):
        self.partials_seen = []
        self.streamer = StreamingSTT(on_partial=self.partials_seen.append)

    def tearDown(self):
        self.streamer.close()

    def test_empty_utterance(self):
        self.streamer.start(FakeEngine())
        text, info = self.streamer.finalize()
        self.assertEqual(text, "")
        self.assertEqual(info["strategy"], "empty")

    def test_max_buffer_cap(self):
        streamer = StreamingSTT(max_buffer=1.0)
        try:
            streamer.start(FakeEngine())
            feed(streamer, loud(2.0))
            self.assertEqual(len(streamer._buf), RATE)
            text, _ = streamer.finalize()
            self.assertEqual(text, "hello world")
        finally:
            streamer.close()

    def test_speculative_finalize(self):
        engine = FakeEngine()
        self.streamer.start(engine)
        feed(self.streamer, loud(1.0))
        feed(self.streamer, silence(0.3))
        text, info = self.streamer.finalize()
        self.assertEqual(text, "hello world")
        self.assertEqual(info["strategy"], "speculative")
        self.assertGreaterEqual(info["partials"], 1)
        self.assertGreaterEqual(len(self.partials_seen), 1)

    def test_cloud_backend_skips_speculation(self):
        engine = FakeEngine(backend="groq")
        self.streamer.start(engine)
        feed(self.streamer, loud(1.0))
        feed(self.streamer, silence(0.3))
        text, info = self.streamer.finalize()
        self.assertEqual(text, "hello world")
        self.assertEqual(info["strategy"], "cloud")
        self.assertEqual(info["partials"], 0)
        self.assertEqual(len(engine.calls), 1)  # only the finalize decode

    def test_loud_resume_invalidates_speculation(self):
        engine = FakeEngine()
        self.streamer.start(engine)
        feed(self.streamer, loud(1.0))
        feed(self.streamer, silence(0.2))
        self.assertTrue(wait_until(lambda: self.streamer._spec_text is not None))
        feed(self.streamer, loud(0.5))          # caller keeps talking
        self.assertIsNone(self.streamer._spec_text)
        self.assertEqual(self.streamer._spec_misses, 1)
        feed_realtime(self.streamer, silence(0.3))
        text, info = self.streamer.finalize()
        self.assertEqual(text, "hello world")
        self.assertEqual(info["strategy"], "speculative")
        self.assertGreaterEqual(len(engine.calls), 2)

    def test_quiet_resume_below_rms_gate_discards_stale_spec(self):
        # the kn_02 accuracy hole: speech resumes below peak*0.06, so the RMS
        # gate never sees it; the staleness guard must catch the buffer growth
        engine = FakeEngine()
        self.streamer.start(engine)
        feed(self.streamer, loud(1.0))
        feed(self.streamer, silence(0.2))
        self.assertTrue(wait_until(lambda: self.streamer._spec_text is not None))
        feed(self.streamer, quiet(0.6))         # inaudible to the RMS gate
        feed(self.streamer, silence(0.3))
        text, info = self.streamer.finalize()
        self.assertEqual(info["strategy"], "full")
        self.assertEqual(text, "hello world")   # fresh decode, same accuracy
        self.assertGreaterEqual(len(engine.calls), 2)

    def test_post_miss_suppression_waits_for_near_endpoint(self):
        engine = FakeEngine()
        self.streamer.start(engine)
        feed(self.streamer, loud(1.0))
        feed(self.streamer, silence(0.2))
        self.assertTrue(wait_until(lambda: self.streamer._spec_text is not None))
        feed(self.streamer, loud(0.5))
        feed_realtime(self.streamer, silence(0.14))  # past speculate_after, below endpoint-0.02
        # no speculative decode may be requested yet (a trailing partial is fine)
        self.assertFalse(self.streamer._spec_requested)
        feed_realtime(self.streamer, silence(0.15))  # now past 0.24 s
        text, info = self.streamer.finalize()
        self.assertEqual(info["strategy"], "speculative")
        self.assertEqual(text, "hello world")

    def test_slow_engine_partials_are_cost_gated(self):
        engine = FakeEngine(delay=0.5)          # > partial_max_decode (0.4 s)
        self.streamer.start(engine)
        feed(self.streamer, loud(0.6))
        # first partial is ungated (no cost history); let it finish
        self.assertTrue(wait_until(lambda: self.streamer._decode_ms > 0, timeout=3))
        feed(self.streamer, loud(2.0))
        time.sleep(0.15)
        self.assertLessEqual(self.streamer._partials, 1)
        feed(self.streamer, silence(0.3))
        text, info = self.streamer.finalize()
        self.assertEqual(text, "hello world")
        self.assertEqual(info["strategy"], "speculative")

    def test_cancel_discards_everything(self):
        self.streamer.start(FakeEngine())
        feed(self.streamer, loud(1.0))
        self.streamer.cancel()
        text, info = self.streamer.finalize()
        self.assertEqual(text, "")
        self.assertEqual(info["strategy"], "empty")

    def test_restart_resets_state(self):
        engine = FakeEngine()
        self.streamer.start(engine)
        feed(self.streamer, loud(1.0))
        feed(self.streamer, silence(0.3))
        self.streamer.finalize()
        self.streamer.start(engine)
        self.assertEqual(self.streamer._partials, 0)
        self.assertEqual(self.streamer._spec_misses, 0)
        feed(self.streamer, loud(0.8))
        feed(self.streamer, silence(0.3))
        text, info = self.streamer.finalize()
        self.assertEqual(text, "hello world")
        self.assertEqual(info["strategy"], "speculative")


if __name__ == "__main__":
    unittest.main()