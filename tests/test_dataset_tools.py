"""Dataset ingestion/report tooling tests (V2 Phase B).

Fixtures are generated tool-self-test WAVs in temp dirs — they never enter
the real manifest and are never counted as corpus recordings.
"""
import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "benchmarks"))
import ingest_dataset as ing  # noqa: E402
import dataset_report as rep  # noqa: E402
from validate_dataset import validate_entry  # noqa: E402


def make_wav(path: Path, rate=16000, channels=1, seconds=2.0, kind="tone"):
    n = int(rate * seconds)
    if kind == "silence":
        data = np.zeros(n * channels, dtype="<i2")
    elif kind == "clipped":
        data = np.full(n * channels, 32767, dtype="<i2")
    else:
        t = np.arange(n) / rate
        tone = (0.3 * np.sin(2 * np.pi * 220 * t) * 32767).astype("<i2")
        data = np.tile(tone, channels) if channels > 1 else tone
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data.tobytes())


def slot(eid, lang, noise="clean"):
    return {"id": eid, "lang": lang,
            "audio_path": f"evaluation/dataset/audio/{lang}/{eid}.wav",
            "status": "NOT_COLLECTED", "reference_text": None, "speaker_id": None,
            "consent": None, "noise_condition": noise, "device": None,
            "duration_s": None, "domain": "conversation", "prompt_hint": None,
            "target_speaker_group": 1, "collected_at": None, "notes": None}


class DatasetToolTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        self.manifest = self.root / "manifest.jsonl"
        self.entries = [slot("hi_001", "hi"), slot("hi_002", "hi"), slot("gu_001", "gu")]
        self.manifest.write_text(
            "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in self.entries),
            encoding="utf-8")
        self.audio = self.root / "rec.wav"
        make_wav(self.audio)

    def tearDown(self):
        self._td.cleanup()

    def ingest(self, **kw):
        args = dict(audio=self.audio, lang="hi", reference="नमस्ते", speaker="spk_hi_01",
                    consent=True, noise="clean", device="phone")
        args.update(kw)
        return ing.ingest(self.root, self.manifest, **args)

    def reload(self):
        return ing.load_manifest(self.manifest)

    def test_valid_ingest_fills_slot_and_validates(self):
        problems, entry = self.ingest()
        self.assertEqual(problems, [])
        self.assertEqual(entry["id"], "hi_001")
        self.assertEqual(entry["status"], "COLLECTED")
        self.assertIs(entry["transcript_verified"], False)
        self.assertEqual(entry["script"], "Devanagari")
        self.assertEqual(entry["sample_rate"], 16000)
        self.assertTrue((self.root / entry["audio_path"]).exists())
        stored = next(e for e in self.reload() if e["id"] == "hi_001")
        self.assertEqual(validate_entry(stored, self.root), [])

    def test_dry_run_writes_nothing(self):
        problems, _ = self.ingest(dry_run=True)
        self.assertEqual(problems, [])
        self.assertEqual(self.reload()[0]["status"], "NOT_COLLECTED")
        self.assertFalse((self.root / "evaluation/dataset/audio/hi/hi_001.wav").exists())

    def test_missing_consent_rejected(self):
        problems, _ = self.ingest(consent=False)
        self.assertTrue(any("consent" in p for p in problems))

    def test_invalid_lang_rejected(self):
        problems, _ = self.ingest(lang="xx")
        self.assertTrue(any("language" in p for p in problems))

    def test_missing_reference_rejected(self):
        problems, _ = self.ingest(reference="  ")
        self.assertTrue(any("reference" in p for p in problems))

    def test_silent_audio_rejected(self):
        make_wav(self.audio, kind="silence")
        problems, _ = self.ingest()
        self.assertTrue(any("silent" in p for p in problems))

    def test_clipped_audio_rejected(self):
        make_wav(self.audio, kind="clipped")
        problems, _ = self.ingest()
        self.assertTrue(any("clipping" in p for p in problems))

    def test_too_short_rejected(self):
        make_wav(self.audio, seconds=0.2)
        problems, _ = self.ingest()
        self.assertTrue(any("duration" in p for p in problems))

    def test_wrong_rate_needs_convert_flag(self):
        make_wav(self.audio, rate=48000)
        problems, _ = self.ingest()
        self.assertTrue(any("non-canonical" in p for p in problems))
        problems, entry = self.ingest(convert=True)
        self.assertEqual(problems, [])
        with wave.open(str(self.root / entry["audio_path"]), "rb") as w:
            self.assertEqual(w.getframerate(), 16000)
            self.assertEqual(w.getnchannels(), 1)
        originals = list((self.root / "evaluation/dataset/originals").iterdir())
        self.assertEqual(len(originals), 1)
        with wave.open(str(originals[0]), "rb") as w:
            self.assertEqual(w.getframerate(), 48000)

    def test_stereo_converted_to_mono(self):
        make_wav(self.audio, channels=2)
        problems, entry = self.ingest(convert=True)
        self.assertEqual(problems, [])
        with wave.open(str(self.root / entry["audio_path"]), "rb") as w:
            self.assertEqual(w.getnchannels(), 1)

    def test_duplicate_audio_rejected(self):
        problems, _ = self.ingest()
        self.assertEqual(problems, [])
        problems, _ = self.ingest(speaker="spk_hi_02")
        self.assertTrue(any("duplicate" in p for p in problems))

    def test_corrupted_audio_rejected(self):
        self.audio.write_bytes(b"not a wav file at all")
        problems, _ = self.ingest()
        self.assertTrue(any("corrupted" in p for p in problems))

    def test_missing_file_rejected(self):
        problems, _ = self.ingest(audio=self.root / "nope.wav")
        self.assertTrue(any("missing file" in p for p in problems))

    def test_slot_lang_mismatch_rejected(self):
        problems, _ = self.ingest(slot_id="gu_001")
        self.assertTrue(any("belongs to" in p for p in problems))

    def test_verify_flow(self):
        self.ingest()
        problems = ing.verify_transcript(self.manifest, "hi_001", "spk_hi_01")
        self.assertTrue(problems)  # recorder cannot self-verify
        problems = ing.verify_transcript(self.manifest, "hi_001", "spk_hi_02")
        self.assertEqual(problems, [])
        stored = next(e for e in self.reload() if e["id"] == "hi_001")
        self.assertIs(stored["transcript_verified"], True)
        self.assertEqual(validate_entry(stored, self.root), [])

    def test_validator_flags_verified_without_verifier(self):
        self.ingest()
        entries = self.reload()
        entries[0]["transcript_verified"] = True
        problems = validate_entry(entries[0], self.root)
        self.assertTrue(any("transcript_verified_by" in p for p in problems))

    def test_report_counts_actual(self):
        self.ingest()
        report = rep.build_report(self.manifest, self.root)
        self.assertEqual(report["collected_total"], 1)
        self.assertEqual(report["per_lang"]["hi"]["collected"], 1)
        self.assertEqual(report["per_lang"]["hi"]["distinct_speakers"], 1)
        self.assertEqual(report["per_lang"]["gu"]["collected"], 0)
        self.assertFalse(report["complete"])
        self.assertEqual(report["invalid_entries"], [])


if __name__ == "__main__":
    unittest.main()