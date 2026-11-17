"""Regression tests for the V2 Phase F latency-budget analysis helpers.

All numbers here are synthetic TEST FIXTURES for exercising the math — they
are never reported as measured latency.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "benchmarks"))

from run_latency_budget import CONDITIONS, overlap_savings, per_lang_stats  # noqa: E402


def turn(lang, clip, asr, e2e, ok=True, strategy="speculative"):
    return {"lang": lang, "clip": clip, "asr_ms": asr, "e2e_client_ms": e2e,
            "first_audio_ms": e2e - 300, "ok": ok, "asr_strategy": strategy}


class OverlapSavingsTests(unittest.TestCase):
    def test_asr_hidden_vs_perceived_gap(self):
        # block: full decode at endpoint (asr 600); streaming: speculative (asr 50)
        # but E2E only drops 200 because LLM+TTS dominate the rest.
        stream = [turn("hi", "hi_01.wav", 50, 1100), turn("hi", "hi_02.wav", 60, 1200)]
        block = [turn("hi", "hi_01.wav", 600, 1300, strategy="full"),
                 turn("hi", "hi_02.wav", 650, 1400, strategy="full")]
        s = overlap_savings(stream, block)
        self.assertEqual(s["n_pairs"], 2)
        # p50 of two values uses the harness convention (upper-middle index)
        self.assertAlmostEqual(s["asr_time_hidden_ms"]["p50"], 590.0)
        self.assertAlmostEqual(s["perceived_e2e_saved_ms"]["p50"], 200.0)
        # the whole point: ASR savings != E2E savings
        self.assertGreater(s["asr_time_hidden_ms"]["p50"],
                           s["perceived_e2e_saved_ms"]["p50"])

    def test_pairs_by_lang_and_clip(self):
        stream = [turn("hi", "a.wav", 50, 1000), turn("en", "b.wav", 80, 1300)]
        block = [turn("en", "b.wav", 700, 1500, strategy="full")]
        s = overlap_savings(stream, block)
        self.assertEqual(s["n_pairs"], 1)  # only en/b matches

    def test_failed_turns_excluded(self):
        stream = [turn("hi", "a.wav", 50, 1000, ok=False)]
        block = [turn("hi", "a.wav", 600, 1300)]
        self.assertEqual(overlap_savings(stream, block)["n_pairs"], 0)

    def test_empty_is_safe(self):
        s = overlap_savings([], [])
        self.assertEqual(s["n_pairs"], 0)
        self.assertIsNone(s["asr_time_hidden_ms"]["p50"])


class PerLangStatsTests(unittest.TestCase):
    def test_strategy_counts_and_failures(self):
        turns = [turn("hi", "a.wav", 50, 1000),
                 turn("hi", "b.wav", 60, 1100, strategy="full"),
                 turn("hi", "c.wav", 0, 0, ok=False)]
        out = per_lang_stats(turns, ["hi"])
        self.assertEqual(out["hi"]["failed_turns"], 1)
        self.assertEqual(out["hi"]["asr_strategy_counts"], {"speculative": 1, "full": 1})
        self.assertEqual(out["hi"]["e2e_client_ms"]["n"], 2)

    def test_transport_residual_present(self):
        t = turn("hi", "a.wav", 50, 1000)
        t["transport_residual_ms"] = 40.0
        out = per_lang_stats([t], ["hi"])
        self.assertEqual(out["hi"]["transport_residual_ms"]["p50"], 40.0)


class ConditionMatrixTests(unittest.TestCase):
    def test_conditions_cover_required_axes(self):
        # idle/moderate/high CPU, 1 vs multi session, streaming vs block
        self.assertEqual(CONDITIONS["idle1s"], (0, 1, True))
        self.assertEqual(CONDITIONS["idle1b"], (0, 1, False))
        self.assertEqual(CONDITIONS["mod1s"][0], 2)
        self.assertEqual(CONDITIONS["high1s"][0], 4)
        self.assertEqual(CONDITIONS["idle3s"][1], 3)
        self.assertEqual(CONDITIONS["idle3b"], (0, 3, False))


if __name__ == "__main__":
    unittest.main()