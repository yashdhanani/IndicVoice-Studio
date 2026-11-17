"""Phase I security revalidation — targeted, model-free regression tests.

Independently re-checks the fail-closed auth, constant-time token compare,
single-use/expiring tickets, Origin allowlisting, inbound frame caps, the
insecure-bind refusal, and startup log redaction. These run without models or
cloud keys (the log-redaction test mocks the model-existence check and uvicorn).
"""
import io
import contextlib
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from src import call_server, config


def fake_ws(origin=None):
    headers = {} if origin is None else {"origin": origin}
    return types.SimpleNamespace(headers=headers, client=types.SimpleNamespace(host="127.0.0.1"))


class AuthorisedTests(unittest.TestCase):
    def test_open_dev_when_no_token(self):
        with mock.patch.object(config, "ACCESS_TOKEN", ""):
            self.assertTrue(call_server._authorised({}))
            self.assertTrue(call_server._authorised({"token": "anything"}))

    def test_fail_closed_without_credentials(self):
        with mock.patch.object(config, "ACCESS_TOKEN", "secret"):
            self.assertFalse(call_server._authorised({}))
            self.assertFalse(call_server._authorised({"token": ""}))
            self.assertFalse(call_server._authorised({"ticket": ""}))

    def test_wrong_token_rejected(self):
        with mock.patch.object(config, "ACCESS_TOKEN", "secret"):
            self.assertFalse(call_server._authorised({"token": "wrong"}))
            self.assertFalse(call_server._authorised({"token": "secre"}))
            self.assertFalse(call_server._authorised({"token": "secretX"}))

    def test_correct_token_accepted(self):
        with mock.patch.object(config, "ACCESS_TOKEN", "secret"):
            self.assertTrue(call_server._authorised({"token": "secret"}))

    def test_valid_ticket_accepted_once(self):
        with mock.patch.object(config, "ACCESS_TOKEN", "secret"), \
                mock.patch.dict(call_server._tickets, {}, clear=True):
            ticket = call_server._issue_ticket()
            self.assertTrue(call_server._authorised({"ticket": ticket}))
            self.assertFalse(call_server._authorised({"ticket": ticket}))

    def test_unknown_ticket_rejected(self):
        with mock.patch.object(config, "ACCESS_TOKEN", "secret"), \
                mock.patch.dict(call_server._tickets, {}, clear=True):
            self.assertFalse(call_server._authorised({"ticket": "nope"}))


class TicketTests(unittest.TestCase):
    def test_tickets_are_unique_and_high_entropy(self):
        with mock.patch.dict(call_server._tickets, {}, clear=True):
            tickets = [call_server._issue_ticket() for _ in range(200)]
            self.assertEqual(len(set(tickets)), 200)
            # token_urlsafe(24) -> 32 chars, ~192 bits
            self.assertTrue(all(len(t) >= 32 for t in tickets))

    def test_single_use(self):
        with mock.patch.dict(call_server._tickets, {}, clear=True):
            t = call_server._issue_ticket()
            self.assertTrue(call_server._consume_ticket(t))
            self.assertFalse(call_server._consume_ticket(t))

    def test_expired_ticket_rejected(self):
        with mock.patch.dict(call_server._tickets, {}, clear=True), \
                mock.patch.object(config, "TICKET_TTL_SECONDS", 0.0):
            t = call_server._issue_ticket()
            self.assertFalse(call_server._consume_ticket(t))

    def test_stale_tickets_purged_on_issue(self):
        with mock.patch.dict(call_server._tickets, {}, clear=True), \
                mock.patch.object(config, "TICKET_TTL_SECONDS", 0.0):
            stale = call_server._issue_ticket()
            self.assertIn(stale, call_server._tickets)
            with mock.patch.object(config, "TICKET_TTL_SECONDS", 60.0):
                call_server._issue_ticket()
            self.assertNotIn(stale, call_server._tickets)


class OriginTests(unittest.TestCase):
    def test_no_origin_allowed_for_non_browser(self):
        self.assertTrue(call_server._origin_ok(fake_ws(None)))

    def test_localhost_origins_allowed(self):
        for o in ("http://localhost:8000", "http://127.0.0.1:8000",
                  "http://[::1]:8000", "HTTP://LOCALHOST:8000"):
            self.assertTrue(call_server._origin_ok(fake_ws(o)), o)

    def test_foreign_origin_rejected(self):
        for o in ("http://evil.example", "https://evil.example:443",
                  "http://localhost.evil.com", "http://127.0.0.1.evil.com"):
            self.assertFalse(call_server._origin_ok(fake_ws(o)), o)

    def test_allowlisted_origin_allowed(self):
        with mock.patch.object(config, "ALLOWED_ORIGINS", ("https://calls.example.com",)):
            self.assertTrue(call_server._origin_ok(fake_ws("https://calls.example.com")))
            self.assertFalse(call_server._origin_ok(fake_ws("https://other.example.com")))


class FrameCapTests(unittest.TestCase):
    def test_inbound_caps_not_weakened(self):
        self.assertEqual(call_server.MAX_VOICE_FRAME_BYTES, 64 * 1024)
        self.assertEqual(call_server.MAX_TELEPHONY_TEXT_BYTES, 64 * 1024)
        self.assertEqual(call_server.MAX_TELEPHONY_PAYLOAD_CHARS, 32 * 1024)
        self.assertEqual(call_server.MAX_SESSIONS_PER_IP, 8)


class BindSecurityTests(unittest.TestCase):
    def test_non_localhost_without_token_fails_closed(self):
        for host in ("0.0.0.0", "192.168.1.5", "10.0.0.2", "::"):
            self.assertIsNotNone(call_server._bind_security_error(host, ""))

    def test_non_localhost_with_token_ok(self):
        self.assertIsNone(call_server._bind_security_error("0.0.0.0", "secret"))

    def test_localhost_open_ok(self):
        for host in ("127.0.0.1", "localhost", "::1"):
            self.assertIsNone(call_server._bind_security_error(host, ""))


class LogRedactionTests(unittest.TestCase):
    def _run_main_capture(self, token):
        """Run main() with models/uvicorn mocked; capture stdout."""
        with tempfile.TemporaryDirectory() as td:
            vad = Path(td) / "vad.onnx"
            vad.write_bytes(b"x")
            tts_dir = Path(td) / "tts"
            tts_dir.mkdir()
            (tts_dir / "model.onnx").write_bytes(b"x")
            buf = io.StringIO()
            with mock.patch.object(config, "ACCESS_TOKEN", token), \
                    mock.patch.object(config, "VAD_PATH", vad), \
                    mock.patch.object(config, "tts_model_dir", return_value=tts_dir), \
                    mock.patch.object(call_server, "create_app", return_value=object()), \
                    mock.patch.object(call_server, "warm_up"), \
                    mock.patch("uvicorn.run") as run, \
                    mock.patch("src.sts_pipeline.LLMClient") as llm, \
                    contextlib.redirect_stdout(buf):
                llm.return_value.backend = "groq"
                llm.return_value.model = "m"
                rc = call_server.main(["--host", "127.0.0.1", "--port", "8099", "--no-warm"])
            self.assertEqual(rc, 0)
            run.assert_called_once()
            # access logs must stay suppressed so ?token= URLs are not logged
            self.assertEqual(run.call_args.kwargs.get("log_level"), "warning")
            return buf.getvalue()

    def test_token_value_never_printed(self):
        out = self._run_main_capture("super-secret-token-value")
        self.assertNotIn("super-secret-token-value", out)
        self.assertIn("<your-token>", out)  # placeholder only

    def test_open_dev_warning_when_no_token(self):
        out = self._run_main_capture("")
        self.assertIn("open access, localhost development only", out)


if __name__ == "__main__":
    unittest.main()