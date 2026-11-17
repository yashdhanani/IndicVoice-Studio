"""Model-free tests for the Phase J pilot monitor's pure helpers.

Verifies secret redaction, threshold alerting, secret-free status formatting
and peak summarisation — without a server or any model.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from pilot_monitor import (  # noqa: E402
    check_alerts, format_status, peak_summary, redact,
)

THRESH = {"loop_ms": 250.0, "queue": 64, "asr_queue": 8, "rss_mb": 1500.0, "sessions": 5}


class RedactTests(unittest.TestCase):
    def test_token_value_redacted(self):
        out = redact("http://127.0.0.1:8000/metrics?token=super-secret")
        self.assertNotIn("super-secret", out)
        self.assertIn("REDACTED", out)

    def test_ticket_value_redacted(self):
        out = redact("ws://h/ws/voice?lang=hi&ticket=abc123secret")
        self.assertNotIn("abc123secret", out)

    def test_other_params_preserved(self):
        out = redact("http://h/metrics?lang=hi&token=xyz")
        self.assertIn("lang=hi", out)
        self.assertNotIn("xyz", out)

    def test_no_query_unchanged(self):
        self.assertEqual(redact("http://h/metrics"), "http://h/metrics")


class AlertTests(unittest.TestCase):
    def test_no_alerts_when_healthy(self):
        m = {"event_loop_delay_ms": 10, "outbound_queue_max": 2,
             "asr_executor_queue": 0, "rss_mb": 900, "active_sessions": 1}
        self.assertEqual(check_alerts(m, THRESH), [])

    def test_each_threshold_triggers(self):
        m = {"event_loop_delay_ms": 300, "outbound_queue_max": 100,
             "asr_executor_queue": 10, "rss_mb": 1600, "active_sessions": 6}
        alerts = check_alerts(m, THRESH)
        self.assertEqual(len(alerts), 5)

    def test_missing_gauges_do_not_crash(self):
        self.assertEqual(check_alerts({}, THRESH), [])

    def test_boundary_not_exceeded(self):
        m = {"event_loop_delay_ms": 250, "active_sessions": 5}
        self.assertEqual(check_alerts(m, THRESH), [])


class FormatTests(unittest.TestCase):
    def test_status_is_secret_free(self):
        m = {"active_sessions": 2, "client_ips": 1, "outbound_queue_total": 3,
             "outbound_queue_max": 2, "asr_executor_queue": 0,
             "event_loop_delay_ms": 5, "rss_mb": 900, "uptime_s": 10}
        line = format_status(m)
        self.assertIn("sessions=2", line)
        self.assertNotIn("token", line)
        self.assertNotIn("transcript", line)

    def test_missing_gauges_render_dash(self):
        self.assertIn("sessions=-", format_status({}))


class PeakSummaryTests(unittest.TestCase):
    def test_peaks(self):
        series = [{"active_sessions": 1, "rss_mb": 800, "event_loop_delay_ms": 5},
                  {"active_sessions": 3, "rss_mb": 1000, "event_loop_delay_ms": 40}]
        s = peak_summary(series)
        self.assertEqual(s["samples"], 2)
        self.assertEqual(s["peak_active_sessions"], 3)
        self.assertEqual(s["peak_rss_mb"], 1000)
        self.assertEqual(s["peak_event_loop_delay_ms"], 40)

    def test_empty_series(self):
        s = peak_summary([])
        self.assertEqual(s["samples"], 0)
        self.assertIsNone(s["peak_rss_mb"])


if __name__ == "__main__":
    unittest.main()