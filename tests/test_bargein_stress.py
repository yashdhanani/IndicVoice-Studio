"""Stress tests for barge-in cancellation (D9)."""
import threading
import unittest

import numpy as np

from src.call_server import AudioSink


class BargeInStressTests(unittest.TestCase):
    def test_rapid_bargein_no_stale_audio(self):
        emitted = []
        lock = threading.Lock()

        def emit(audio):
            with lock:
                emitted.append(len(audio))

        sink = AudioSink(emit, target_rate=16000)
        rng = np.random.default_rng(0)
        for _ in range(5):
            sink.resume()
            for i in range(10):
                sink.push(rng.standard_normal(320).astype(np.float32))
            sink.cancel()
            before = len(emitted)
            sink.push(rng.standard_normal(320).astype(np.float32))
            self.assertEqual(len(emitted), before, "stale audio emitted after cancel")
        sink.resume()
        sink.push(rng.standard_normal(320).astype(np.float32))
        self.assertGreater(len(emitted), 0)

    def test_concurrent_cancel_push_threadsafe(self):
        emitted = []
        lock = threading.Lock()

        def emit(audio):
            with lock:
                emitted.append(len(audio))

        sink = AudioSink(emit, target_rate=16000)
        rng = np.random.default_rng(1)
        errors = []

        def worker(idx):
            try:
                for _ in range(200):
                    if idx % 2 == 0:
                        sink.resume()
                        sink.push(rng.standard_normal(160).astype(np.float32))
                    else:
                        sink.cancel()
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertFalse(errors, errors)

    def test_is_speaking_resets_on_cancel(self):
        sink = AudioSink(lambda a: None, target_rate=16000)
        sink.resume()
        sink.push(np.ones(16000, dtype=np.float32))
        self.assertTrue(sink.is_speaking)
        sink.cancel()
        self.assertFalse(sink.is_speaking)


if __name__ == "__main__":
    unittest.main()
