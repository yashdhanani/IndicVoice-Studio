"""Turn-taking regressions: barge-in audio, language switching, endpointing.

Three defects found in the 2026-11-18 audit:

1. A barge-in cancelled playback, but the TTS worker was usually mid-clause and
   pushed that clause to the sink 100-600 ms later -- the interrupted reply kept
   talking over the user.
2. A short Latin-script turn ("ok", "hello") flipped the whole session to
   English, because script detection treated any Latin text as English.
3. The end-of-turn silence was fixed at session start, so a Hindi call (0.26 s)
   that switched to English kept a 0.26 s endpoint although English needs
   0.45 s.
"""

from __future__ import annotations

import types
import unittest

import numpy as np

from src import config
from src.call_server import AudioSink, CallSession
from src.sts_pipeline import VoiceAgent


def _audio(seconds: float = 0.1) -> np.ndarray:
    return np.full(int(config.SAMPLE_RATE * seconds), 0.1, dtype=np.float32)


class BargeInSinkTests(unittest.TestCase):
    def test_cancelled_sink_drops_late_clause(self):
        sent: list[np.ndarray] = []
        flushes: list[int] = []
        sink = AudioSink(emit=sent.append, on_flush=lambda: flushes.append(1))

        sink.push(_audio())
        self.assertEqual(len(sent), 1)

        sink.cancel()                      # user interrupted here
        sink.push(_audio())                # the in-flight clause finishes late
        self.assertEqual(len(sent), 1, "stale audio must not be emitted after barge-in")
        self.assertFalse(sink.is_speaking)
        self.assertEqual(len(flushes), 1)

    def test_next_turn_speaks_again_after_resume(self):
        sent: list[np.ndarray] = []
        sink = AudioSink(emit=sent.append)
        sink.cancel()
        sink.push(_audio())
        self.assertEqual(sent, [])
        sink.resume()
        sink.push(_audio())
        self.assertEqual(len(sent), 1)

    def test_closed_sink_stays_muted(self):
        sent: list[np.ndarray] = []
        sink = AudioSink(emit=sent.append)
        sink.close()
        sink.push(_audio())
        self.assertEqual(sent, [])


class LanguageSwitchEvidenceTests(unittest.TestCase):
    def _agent(self, current: str = "hi") -> VoiceAgent:
        agent = VoiceAgent.__new__(VoiceAgent)
        agent.cfg = types.SimpleNamespace(auto_lang=True)
        agent.current_lang = current
        agent._stt = {}
        agent.stt = object()
        agent._recognizer = lambda lang: object()   # no model load in tests
        return agent

    def test_single_latin_word_does_not_flip_hindi_session(self):
        agent = self._agent("hi")
        self.assertEqual(agent.maybe_switch_language("ok"), "hi")
        self.assertEqual(agent.maybe_switch_language("hello there"), "hi")

    def test_real_english_sentence_switches(self):
        agent = self._agent("hi")
        self.assertEqual(
            agent.maybe_switch_language("can you check my order status"), "en"
        )

    def test_indic_script_switches_on_one_word(self):
        agent = self._agent("hi")
        self.assertEqual(agent.maybe_switch_language("வணக்கம்"), "ta")
        self.assertEqual(agent.current_lang, "ta")

    def test_hi_family_default_still_wins_ties(self):
        agent = self._agent("mr")
        self.assertEqual(agent.maybe_switch_language("नमस्कार"), "mr")


class EndpointRetuneTests(unittest.TestCase):
    def _session(self, override: float | None) -> CallSession:
        session = CallSession.__new__(CallSession)
        session._endpoint_override = override
        session.min_silence = config.ENDPOINT_SILENCE
        session.streamer = types.SimpleNamespace(endpoint_silence=config.ENDPOINT_SILENCE)
        return session

    def test_switch_to_english_lengthens_endpoint(self):
        session = self._session(None)
        session._retune_endpoint("en")
        self.assertAlmostEqual(session.streamer.endpoint_silence,
                               config.endpoint_for("en"))
        self.assertAlmostEqual(session.min_silence, config.endpoint_for("en"))

    def test_switch_back_shortens_endpoint(self):
        session = self._session(None)
        session._retune_endpoint("en")
        session._retune_endpoint("hi")
        self.assertAlmostEqual(session.streamer.endpoint_silence,
                               config.ENDPOINT_SILENCE)

    def test_explicit_override_is_not_overwritten(self):
        session = self._session(0.6)
        session._retune_endpoint("en")
        self.assertAlmostEqual(session.streamer.endpoint_silence, config.ENDPOINT_SILENCE)

    def test_switch_to_gujarati_uses_0_35(self):
        # F4: Gujarati turns split at 0.26 s on synthetic audio (endpoint fired
        # 2.24 s early); 0.35 s keeps the utterance whole. Real-speech
        # validation still pending.
        session = self._session(None)
        session._retune_endpoint("gu")
        self.assertAlmostEqual(session.streamer.endpoint_silence,
                               config.endpoint_for("gu"))
        self.assertAlmostEqual(session.min_silence, config.endpoint_for("gu"))
        self.assertAlmostEqual(config.endpoint_for("gu"), 0.35)


if __name__ == "__main__":
    unittest.main()
