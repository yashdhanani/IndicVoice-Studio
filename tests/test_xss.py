"""Static XSS regression checks (Hardening V1 B3).

Server-provided text (transcripts, replies, health strings, error messages)
must reach the DOM through textContent, never through innerHTML templates.
These tests pin that property so a future edit cannot silently reintroduce
an injection sink.
"""
import re
import unittest
from pathlib import Path

from src.call_server import _INDEX_HTML

ROOT = Path(__file__).resolve().parent.parent
APP_JS = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

#: the only expressions allowed inside innerHTML templates: compile-time
#: constants, locally computed booleans, or client-side timestamps
ALLOWED_INTERPOLATIONS = {
    'role === "you" ? "You" : "IndicVoice"',
    "fmtTime(m.time)",
    "l.native",
    "l.en",
    "l.code",
    'ttsOk ? "dot-ok" : "dot-bad"',
    'ttsOk ? "ready" : "missing"',
    'asrOk ? "dot-ok" : "dot-warn"',
    'asrOk ? "ASR local" : "ASR cloud"',
}


class TestServerFallbackPage(unittest.TestCase):
    def test_index_html_uses_textcontent_not_innerhtml(self):
        self.assertNotIn("innerHTML", _INDEX_HTML)
        self.assertIn("textContent", _INDEX_HTML)

    def test_index_html_has_no_other_injection_sinks(self):
        for sink in ("insertAdjacentHTML", "document.write", "outerHTML"):
            self.assertNotIn(sink, _INDEX_HTML)


class TestBrowserClient(unittest.TestCase):
    def test_message_text_rendered_via_textcontent(self):
        self.assertIn("body.textContent = text", APP_JS)
        self.assertIn("el.textContent = text", APP_JS)

    def test_health_backend_rendered_via_textcontent(self):
        # D22 regression: v.backend comes from the server's /health JSON
        self.assertIn('.vtag-backend").textContent = v.backend', APP_JS)

    def test_innerhtml_templates_only_interpolate_safe_values(self):
        assignments = re.findall(
            r"innerHTML\s*=\s*(`[^`]*`|\"[^\"]*\"|'[^']*')", APP_JS)
        self.assertTrue(assignments)
        for template in assignments:
            for expr in re.findall(r"\$\{([^}]*)\}", template):
                self.assertIn(
                    expr.strip(), ALLOWED_INTERPOLATIONS,
                    f"unsafe innerHTML interpolation: ${{{expr}}}")

    def test_no_other_html_injection_sinks(self):
        for sink in ("insertAdjacentHTML", "document.write", "outerHTML"):
            self.assertNotIn(sink, APP_JS)


if __name__ == "__main__":
    unittest.main()