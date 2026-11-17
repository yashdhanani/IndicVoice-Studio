"""Regression test: A/B sub-manifests must keep audio paths resolvable.

The counterbalanced A/B branch writes per-order sub-manifests next to --out.
Audio paths in the source manifest are relative to the source manifest's
directory, so they must be rewritten to absolute paths (defect found when the
re-run crashed with FileNotFoundError in the results directory).
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src import evaluate


class TestABSubManifestPaths(unittest.TestCase):
    def test_sub_manifest_audio_paths_absolute(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            audio_dir = root / "eval_data"
            audio_dir.mkdir()
            (audio_dir / "clip.wav").write_bytes(b"RIFF")
            manifest = audio_dir / "manifest.json"
            entries = [{"id": f"c{i}", "lang": "hi", "audio_file": "clip.wav",
                        "reference": "x"} for i in range(4)]
            manifest.write_text(json.dumps(entries), encoding="utf-8")
            out = root / "results" / "ab.json"

            seen = []

            def fake_eval(sub, backend, mode=None, asr_only=False):
                seen.append((Path(sub), mode))
                return []

            with mock.patch.object(evaluate, "evaluate_manifest", fake_eval), \
                 mock.patch.object(evaluate, "summarise", lambda rows: {}), \
                 mock.patch.object(evaluate, "render_markdown", lambda s: ""):
                rc = evaluate.main(["--manifest", str(manifest), "--mode", "ab",
                                    "--asr-only", "--out", str(out)])
            self.assertEqual(rc, 0)
            self.assertEqual([m for _, m in seen],
                             ["block", "streaming", "streaming", "block"])
            for sub, _ in seen:
                self.assertEqual(sub.parent, out.parent)
                for entry in json.loads(sub.read_text(encoding="utf-8")):
                    p = Path(entry["audio_file"])
                    self.assertTrue(p.is_absolute())
                    self.assertTrue(p.exists())


if __name__ == "__main__":
    unittest.main()