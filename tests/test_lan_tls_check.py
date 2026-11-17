"""Regression tests for benchmarks/check_lan_tls.py helpers (V2 Phase D).

The full TLS/WSS check is a benchmark (it starts a real server); these tests
cover its pure helpers so CI's fast tier exercises them without models.
"""
from __future__ import annotations

import socket
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "benchmarks"))

from check_lan_tls import _report, inspect_cert, port_free  # noqa: E402

try:
    import cryptography  # noqa: F401
    HAVE_CRYPTO = True
except ImportError:
    HAVE_CRYPTO = False


class PortFreeTests(unittest.TestCase):
    def test_occupied_port_is_not_free(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            self.assertFalse(port_free(s.getsockname()[1]))

    def test_unbound_port_is_free(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        self.assertTrue(port_free(port))


class ReportTests(unittest.TestCase):
    def test_all_pass_requires_every_check_pass(self):
        checks = [{"id": "L1", "name": "x", "status": "PASS", "detail": ""}]
        self.assertTrue(_report(8444, checks, None)["all_pass"])
        checks.append({"id": "L2", "name": "y", "status": "FAIL", "detail": ""})
        self.assertFalse(_report(8444, checks, None)["all_pass"])

    def test_empty_checks_are_not_all_pass(self):
        self.assertFalse(_report(8444, [], None)["all_pass"])

    def test_contract_states_physical_not_tested(self):
        report = _report(8444, [], None)
        self.assertIn("NOT TESTED", report["contract"])


@unittest.skipUnless(HAVE_CRYPTO, "cryptography not installed (fast CI tier)")
class InspectCertTests(unittest.TestCase):
    def test_generated_self_signed_cert(self):
        from src.tls_cert import ensure_certificate

        with tempfile.TemporaryDirectory() as tmp:
            cert_path, key_path = ensure_certificate(directory=Path(tmp))
            info = inspect_cert(cert_path)
            self.assertTrue(info["self_signed"])
            self.assertIn("127.0.0.1", info["sans"])
            self.assertIn("localhost", info["sans"])
            self.assertGreater(info["days_remaining"], 800)
            # public properties only: nothing from the private key file
            self.assertNotIn(key_path.read_text()[:40], str(info))

    def test_missing_cert_raises(self):
        with self.assertRaises(FileNotFoundError):
            inspect_cert(Path("does-not-exist-cert.pem"))


if __name__ == "__main__":
    unittest.main()