"""Unit tests for text normalisation, sentence splitting and transcript cleaning."""
import re
import unittest

import numpy as np

from src.sts_pipeline import _clean_transcript, _trim_silence
from src.text_normalizer import SentenceSplitter, TextNormalizer, number_to_words


class TestTextNormalizer(unittest.TestCase):
    def setUp(self):
        self.hi = TextNormalizer("hi")
        self.en = TextNormalizer("en")

    def test_currency(self):
        out = self.hi.normalize("कुल ₹500 है।")
        self.assertNotIn("₹", out)
        self.assertFalse(re.search(r"\d", out), out)
        self.assertIn("रुपये", out)

    def test_phone_digits_become_words(self):
        out = self.hi.normalize("मेरा नंबर 9876543210 है।")
        self.assertFalse(re.search(r"\d", out), out)

    def test_date(self):
        out = self.hi.normalize("डिलीवरी 12/05/2026 को होगी।")
        self.assertNotIn("/", out)
        self.assertFalse(re.search(r"\d", out), out)

    def test_otp_digit_by_digit(self):
        out = self.en.normalize("Your OTP is 4321.")
        self.assertNotIn("4321", out)
        self.assertIn("four", out)
        self.assertIn("three", out)

    def test_markdown_stripped(self):
        out = self.en.normalize("**Bold** and `code` here.")
        self.assertNotIn("*", out)
        self.assertNotIn("`", out)

    def test_empty(self):
        self.assertEqual(self.hi.normalize("   "), "")

    def test_number_to_words_zero(self):
        self.assertTrue(number_to_words(0, "hi"))

    def test_all_languages_construct(self):
        for lang in ("hi", "gu", "mr", "bn", "ta", "te", "kn", "ml", "pa", "or", "as", "en"):
            TextNormalizer(lang)


class TestSentenceSplitter(unittest.TestCase):
    def test_incremental(self):
        sp = SentenceSplitter("hi")
        self.assertEqual(sp.feed("आपका ऑर्डर कल "), [])
        out = sp.feed("तक पहुँच जाएगा। ")
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0].endswith("।"))
        self.assertEqual(sp.flush(), [])

    def test_flush_tail(self):
        sp = SentenceSplitter("en")
        sp.feed("No punctuation here")
        self.assertEqual(sp.flush(), ["No punctuation here"])
        self.assertEqual(sp.flush(), [])

    def test_danda_boundary(self):
        sp = SentenceSplitter("hi")
        out = sp.feed("पहला वाक्य। दूसरा वाक्य। ")
        self.assertEqual(len(out), 2)

    def test_split_sentences_static(self):
        n = TextNormalizer("en")
        parts = n.split_sentences("One. Two. Three.")
        self.assertEqual(len(parts), 3)


class TestCleanTranscript(unittest.TestCase):
    def test_hallucinations_dropped(self):
        for bad in ("", "  ", "thank you.", "Thanks for watching!", "[music]", "you"):
            self.assertEqual(_clean_transcript(bad), "")

    def test_single_word_answer_preserved(self):
        # D7 regression: "एक" (= "one") is a legitimate answer to a number question
        self.assertEqual(_clean_transcript("एक"), "एक")
        self.assertEqual(_clean_transcript("हाँ"), "हाँ")
        self.assertEqual(_clean_transcript("two"), "two")

    def test_whitespace_stripped(self):
        self.assertEqual(_clean_transcript("  मेरा ऑर्डर  "), "मेरा ऑर्डर")


class TestTrimSilence(unittest.TestCase):
    def test_trims_leading_and_trailing(self):
        speech = np.full(16000, 0.3, dtype=np.float32)
        pad = np.zeros(16000, dtype=np.float32)
        x = np.concatenate([pad, speech, pad])
        y = _trim_silence(x, 16000)
        self.assertLess(len(y), len(x))
        self.assertGreater(len(y), 16000)          # keeps 0.1 s padding each side
        self.assertLess(len(y), 16000 + 2 * 1600 + 64)

    def test_all_silence_unchanged(self):
        x = np.zeros(16000, dtype=np.float32)
        self.assertEqual(len(_trim_silence(x, 16000)), len(x))

    def test_short_audio_unchanged(self):
        x = np.ones(100, dtype=np.float32)
        np.testing.assert_array_equal(_trim_silence(x, 16000), x)


if __name__ == "__main__":
    unittest.main()