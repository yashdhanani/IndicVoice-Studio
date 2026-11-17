"""Unit tests for the audio codecs and helpers in src.call_server."""
import unittest

import numpy as np

from src.call_server import (
    frame_audio,
    float_to_pcm16,
    pcm16_to_float,
    resample,
    ulaw_decode,
    ulaw_encode,
)


class TestPCM16(unittest.TestCase):
    def test_roundtrip(self):
        x = np.linspace(-1.0, 1.0, 1600, dtype=np.float32)
        y = pcm16_to_float(float_to_pcm16(x))
        self.assertEqual(len(y), len(x))
        self.assertLess(float(np.abs(y - x).max()), 1e-4)

    def test_odd_byte_count_is_trimmed(self):
        self.assertEqual(len(pcm16_to_float(b"\x00\x00\x00")), 1)

    def test_clipping(self):
        y = pcm16_to_float(float_to_pcm16(np.array([2.0, -2.0], dtype=np.float32)))
        self.assertLessEqual(float(np.abs(y).max()), 1.0)

    def test_empty(self):
        self.assertEqual(len(pcm16_to_float(b"")), 0)


class TestUlaw(unittest.TestCase):
    def test_roundtrip_sine(self):
        t = np.arange(1600, dtype=np.float32) / 16000
        x = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        y = ulaw_decode(ulaw_encode(x))
        self.assertEqual(len(y), len(x))
        # mu-law is companded 8-bit: ~1% relative error on loud samples
        loud = np.abs(x) > 0.05
        rel = np.abs(y[loud] - x[loud]) / np.abs(x[loud])
        self.assertLess(float(rel.max()), 0.06)

    def test_silence_is_near_zero(self):
        y = ulaw_decode(ulaw_encode(np.zeros(160, dtype=np.float32)))
        self.assertLess(float(np.abs(y).max()), 0.01)

    def test_sign_preserved(self):
        x = np.array([0.5, -0.5, 0.1, -0.1], dtype=np.float32)
        y = ulaw_decode(ulaw_encode(x))
        np.testing.assert_array_equal(np.sign(y), np.sign(x))


class TestResample(unittest.TestCase):
    def test_8k_to_16k_length(self):
        x = np.zeros(800, dtype=np.float32)
        self.assertEqual(len(resample(x, 8000, 16000)), 1600)

    def test_same_rate_is_identity(self):
        x = np.arange(100, dtype=np.float32)
        np.testing.assert_array_equal(resample(x, 16000, 16000), x)

    def test_empty(self):
        self.assertEqual(len(resample(np.zeros(0, dtype=np.float32), 8000, 16000)), 0)


class TestFrameAudio(unittest.TestCase):
    def test_padding(self):
        frames = frame_audio(np.ones(500, dtype=np.float32), 512)
        self.assertEqual(len(frames), 1)
        self.assertEqual(len(frames[0]), 512)
        self.assertEqual(float(frames[0][500:].sum()), 0.0)

    def test_exact_multiple(self):
        frames = frame_audio(np.ones(1024, dtype=np.float32), 512)
        self.assertEqual(len(frames), 2)


if __name__ == "__main__":
    unittest.main()