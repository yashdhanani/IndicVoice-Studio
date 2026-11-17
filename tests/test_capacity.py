"""Model-free tests for the Phase G capacity analysis helpers.

These exercise the pure decision logic (cleanup detection, conservative
capacity recommendation, gauge peak extraction) without starting a server or
loading any model.
"""
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "benchmarks"))

from run_capacity import (  # noqa: E402
    CPUSampler, MetricsPoller, capacity_recommendation, cleanup_ok,
)


def level(n, success=1.0, loop=10.0, cpu=50.0):
    return {"level": n, "success_rate": success,
            "peak_event_loop_delay_ms": loop, "cpu": {"peak_pct": cpu}}


class CleanupTests(unittest.TestCase):
    def test_zero_sessions_is_clean(self):
        self.assertTrue(cleanup_ok({"active_sessions": 0}))

    def test_live_sessions_not_clean(self):
        self.assertFalse(cleanup_ok({"active_sessions": 2}))

    def test_missing_metrics_not_clean(self):
        self.assertFalse(cleanup_ok(None))
        self.assertFalse(cleanup_ok({}))


class CapacityRecommendationTests(unittest.TestCase):
    def test_all_safe_picks_highest(self):
        rec = capacity_recommendation([level(1), level(2), level(3), level(5)])
        self.assertEqual(rec["recommended_max_concurrency"], 5)
        self.assertEqual(rec["safe_levels"], [1, 2, 3, 5])

    def test_stops_at_first_unsafe_level(self):
        rec = capacity_recommendation([
            level(1), level(2), level(3, success=0.8), level(5)])
        self.assertEqual(rec["recommended_max_concurrency"], 2)
        self.assertEqual(rec["safe_levels"], [1, 2])

    def test_high_loop_delay_unsafe(self):
        rec = capacity_recommendation([level(1), level(2, loop=300.0)])
        self.assertEqual(rec["recommended_max_concurrency"], 1)

    def test_high_cpu_unsafe(self):
        rec = capacity_recommendation([level(1), level(2, cpu=97.0)])
        self.assertEqual(rec["recommended_max_concurrency"], 1)

    def test_no_safe_level_recommends_zero(self):
        rec = capacity_recommendation([level(1, success=0.5)])
        self.assertEqual(rec["recommended_max_concurrency"], 0)

    def test_unsorted_input_is_ordered(self):
        rec = capacity_recommendation([level(5), level(1), level(3), level(2)])
        self.assertEqual(rec["safe_levels"], [1, 2, 3, 5])

    def test_missing_gauges_treated_as_zero(self):
        lv = {"level": 1, "success_rate": 1.0}
        rec = capacity_recommendation([lv])
        self.assertEqual(rec["recommended_max_concurrency"], 1)


class MetricsPeaksTests(unittest.TestCase):
    def test_peaks_extract_max_per_gauge(self):
        mp = MetricsPoller.__new__(MetricsPoller)
        mp.series = [
            {"active_sessions": 1, "outbound_queue_total": 2,
             "outbound_queue_max": 2, "asr_executor_queue": 0,
             "event_loop_delay_ms": 5.0},
            {"active_sessions": 3, "outbound_queue_total": 9,
             "outbound_queue_max": 4, "asr_executor_queue": 2,
             "event_loop_delay_ms": 40.0},
        ]
        peaks = mp.peaks()
        self.assertTrue(peaks["available"])
        self.assertEqual(peaks["peak_active_sessions"], 3)
        self.assertEqual(peaks["peak_outbound_queue_total"], 9)
        self.assertEqual(peaks["peak_asr_executor_queue"], 2)
        self.assertEqual(peaks["peak_event_loop_delay_ms"], 40.0)

    def test_empty_series_unavailable(self):
        mp = MetricsPoller.__new__(MetricsPoller)
        mp.series = []
        self.assertFalse(mp.peaks()["available"])


class CPUSamplerTests(unittest.TestCase):
    def test_read_returns_valid_counters(self):
        # regression: _read must not raise NameError (ctypes was local to __init__)
        s = CPUSampler(interval=0.05)
        reading = s._read()
        self.assertIsNotNone(reading)
        idle, total = reading
        self.assertGreaterEqual(total, 0)
        self.assertGreaterEqual(idle, 0)
        self.assertLessEqual(idle, total)

    def test_sampler_produces_samples(self):
        with CPUSampler(interval=0.05) as s:
            time.sleep(0.2)
        self.assertTrue(s.samples)
        for _, pct in s.samples:
            self.assertGreaterEqual(pct, 0.0)
            self.assertLessEqual(pct, 100.0)
        self.assertTrue(s.summary()["available"])


if __name__ == "__main__":
    unittest.main()