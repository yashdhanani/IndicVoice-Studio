"""Regression tests for the V2 Phase E human-evaluation tooling.

All audio and ratings here are synthetic TEST FIXTURES for exercising the
tools — they are never reported as listening results.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
HVQ = ROOT / "evaluation" / "human_voice_quality"
sys.path.insert(0, str(HVQ))

from prepare_samples import build_package, write_wav  # noqa: E402
from score_responses import (  # noqa: E402
    DIMENSIONS, aggregate, build_report, render_markdown,
)

UTTERANCES = {
    "dimensions": list(DIMENSIONS),
    "scale": {"points": 5, "anchors": {str(i): f"anchor {i}" for i in range(1, 6)}},
    "status": "test fixture",
    "utterances": [
        {"key": "greeting", "texts": {"hi": "नमस्ते", "en": "Hello"}},
        {"key": "statement", "texts": {"hi": "कल आएगा", "en": "It arrives tomorrow"}},
    ],
}


def fake_synth(lang, text):
    t = np.arange(8000, dtype=np.float32) / 16000.0
    return 0.2 * np.sin(2 * np.pi * 220 * t), 16000


def failing_synth(lang, text):
    if lang == "en":
        raise RuntimeError("voice unavailable")
    return fake_synth(lang, text)


class BuildPackageTests(unittest.TestCase):
    def test_anonymized_package_and_repeats(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            report = build_package(UTTERANCES, fake_synth, out, seed=7,
                                   repeats=2, langs=("hi", "en"))
            public = json.loads((out / "package.json").read_text(encoding="utf-8"))
            smap = json.loads((out / "private" / "sample_map.json").read_text(encoding="utf-8"))
            self.assertEqual(report["n_unique"], 4)
            self.assertEqual(report["n_repeats"], 4)
            self.assertEqual(public["n_samples"], 8)
            self.assertEqual(len(set(public["samples"])), 8)
            # public package must not leak language or text
            blob = json.dumps(public, ensure_ascii=False)
            for u in UTTERANCES["utterances"]:
                for text in u["texts"].values():
                    self.assertNotIn(text, blob)
            self.assertNotIn('"lang"', blob)
            # repeats point at a same-language original
            for code, info in smap.items():
                if info["repeat_of"]:
                    orig = smap[info["repeat_of"]]
                    self.assertEqual(orig["lang"], info["lang"])
                    self.assertEqual(orig["utterance"], info["utterance"])
                    self.assertIsNone(orig["repeat_of"])
            # every public sample has a real WAV
            for code in public["samples"]:
                with wave.open(str(out / "audio" / f"{code}.wav"), "rb") as w:
                    self.assertEqual(w.getnchannels(), 1)
                    self.assertEqual(w.getsampwidth(), 2)
                    self.assertEqual(w.getframerate(), 16000)
            self.assertTrue((out / "forms" / "rating_form.csv").exists())

    def test_seeded_order_is_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            orders = []
            for i in range(2):
                out = Path(tmp) / f"p{i}"
                build_package(UTTERANCES, fake_synth, out, seed=42,
                              repeats=1, langs=("hi", "en"))
                public = json.loads((out / "package.json").read_text(encoding="utf-8"))
                smap = json.loads((out / "private" / "sample_map.json").read_text(encoding="utf-8"))
                orders.append([(smap[c]["lang"], smap[c]["utterance"],
                                smap[c]["repeat_of"] is not None)
                               for c in public["samples"]])
            self.assertEqual(orders[0], orders[1])

    def test_language_failure_is_reported_not_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            report = build_package(UTTERANCES, failing_synth, out, seed=1,
                                   repeats=2, langs=("hi", "en"))
            self.assertIn("en", report["failures"])
            self.assertEqual(report["langs_ok"], ["hi"])
            self.assertEqual(report["n_unique"], 2)

    def test_write_wav_clips(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.wav"
            write_wav(path, np.array([2.0, -2.0, 0.5], dtype=np.float32), 16000)
            with wave.open(str(path), "rb") as w:
                data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
            self.assertEqual(data[0], 32767)
            self.assertEqual(data[1], -32767)


def rated(value):
    return {d: value for d in DIMENSIONS}


MAP = {
    "aaa111": {"lang": "hi", "utterance": "greeting", "repeat_of": None},
    "bbb222": {"lang": "hi", "utterance": "statement", "repeat_of": None},
    "ccc333": {"lang": "en", "utterance": "greeting", "repeat_of": None},
    "ddd444": {"lang": "hi", "utterance": "greeting", "repeat_of": "aaa111"},
}
RESPONSES = [
    {"listener_id": "L1",
     "ratings": {"aaa111": rated(4), "bbb222": rated(3),
                 "ccc333": rated(2), "ddd444": rated(5)},
     "feedback": {"aaa111": "slightly flat ending"}},
    {"listener_id": "L2",
     "ratings": {"aaa111": rated(5), "bbb222": rated(4),
                 "ccc333": rated(3), "ddd444": rated(5)}},
]


class ScoreTests(unittest.TestCase):
    def test_no_responses_is_not_tested(self):
        report = build_report(MAP, [])
        self.assertEqual(report["status"], "NOT TESTED")
        self.assertEqual(report["per_lang"], {})
        self.assertIn("NOT ITU-T MOS", report["metric_label"])
        self.assertIn("NOT TESTED", render_markdown(report))

    def test_aggregate_means_sd_and_counts(self):
        report = build_report(MAP, RESPONSES)
        self.assertEqual(report["status"], "COLLECTED")
        hi = report["per_lang"]["hi"]
        self.assertEqual(hi["n_listeners"], 2)
        self.assertEqual(hi["n_utterances"], 2)
        overall = hi["dimensions"]["overall"]
        self.assertEqual(overall["n_ratings"], 6)
        self.assertAlmostEqual(overall["mean"], 26 / 6, places=3)
        import statistics
        self.assertAlmostEqual(overall["sd"],
                               statistics.stdev([4, 3, 5, 5, 4, 5]), places=3)
        en = report["per_lang"]["en"]["dimensions"]["overall"]
        self.assertEqual(en["mean"], 2.5)
        self.assertEqual(en["n_ratings"], 2)

    def test_repeat_consistency(self):
        report = build_report(MAP, RESPONSES)
        rc = report["per_lang"]["hi"]["repeat_consistency"]
        self.assertEqual(rc["n_pairs_rated"], 2)
        self.assertAlmostEqual(rc["mean_abs_delta"], 0.5)
        self.assertEqual(rc["max_abs_delta"], 1)

    def test_qualitative_feedback_collected(self):
        report = build_report(MAP, RESPONSES)
        fb = report["qualitative_feedback"]["hi"]
        self.assertEqual(len(fb), 1)
        self.assertEqual(fb[0]["text"], "slightly flat ending")

    def test_invalid_ratings_and_codes_flagged(self):
        bad = [{"listener_id": "L3",
                "ratings": {"aaa111": {**rated(4), "overall": 7},
                            "zzz999": rated(3)}}]
        result = aggregate(MAP, bad)
        self.assertTrue(any("outside 1-5" in p for p in result["problems"]))
        self.assertTrue(any("unknown sample code" in p for p in result["problems"]))
        self.assertEqual(result["per_lang"]["hi"]["dimensions"]["overall"]["n_ratings"], 0)
        self.assertEqual(result["per_lang"]["hi"]["dimensions"]["pronunciation"]["n_ratings"], 1)


if __name__ == "__main__":
    unittest.main()