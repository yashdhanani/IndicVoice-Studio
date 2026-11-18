"""Executor pressure tests (D13)."""
import concurrent.futures
import time
import unittest

import numpy as np


class ExecutorPressureTests(unittest.TestCase):
    def test_executor_handles_concurrent_finalize(self):
        from concurrent.futures import ThreadPoolExecutor

        pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="asr-test")

        def fake_finalize(audio):
            time.sleep(0.1)
            return "transcript", {"cer": 0.0}

        rng = np.random.default_rng(2)
        audios = [rng.standard_normal(16000).astype(np.float32) for _ in range(20)]

        futures = [pool.submit(fake_finalize, a) for a in audios]
        results = [f.result(timeout=10) for f in concurrent.futures.as_completed(futures)]
        self.assertEqual(len(results), 20)
        pool.shutdown(wait=True)

    def test_executor_queue_does_not_deadlock(self):
        from concurrent.futures import ThreadPoolExecutor

        pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="asr-test2")

        def slow(x):
            time.sleep(0.05)
            return x * 2

        futs = [pool.submit(slow, i) for i in range(50)]
        vals = [f.result(timeout=10) for f in futs]
        self.assertEqual(sorted(vals), sorted(i * 2 for i in range(50)))
        pool.shutdown(wait=True)


if __name__ == "__main__":
    unittest.main()
