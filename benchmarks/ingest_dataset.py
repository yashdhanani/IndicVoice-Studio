"""Ingest genuine human recordings into the evaluation dataset (V2 Phase B).

Validates a candidate recording against every acceptance check, optionally
converts it to the canonical format (16 kHz mono PCM16 WAV, original preserved
under evaluation/dataset/originals/), and fills a NOT_COLLECTED manifest slot.
This tool NEVER creates audio, NEVER writes reference text, and NEVER marks
consent or transcript verification on its own -- those are human assertions
passed explicitly on the command line.

Usage:
    python benchmarks/ingest_dataset.py --audio rec.wav --lang hi \
        --speaker spk_hi_01 --reference "मेरा ऑर्डर कहाँ तक पहुँचा?" \
        --noise clean --device phone --consent [--id hi_001] [--convert] \
        [--environment "quiet room"] [--dry-run]

    python benchmarks/ingest_dataset.py verify --id hi_001 --verifier spk_hi_02

Exit codes: 0 = ingested (or dry-run clean); 1 = rejected with reasons.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import wave
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
LANGS = ("hi", "bn", "ta", "te", "kn", "ml", "mr", "gu", "pa", "or", "as", "en")
SCRIPTS = {"hi": "Devanagari", "mr": "Devanagari", "bn": "Bengali", "as": "Bengali",
           "ta": "Tamil", "te": "Telugu", "kn": "Kannada", "ml": "Malayalam",
           "pa": "Gurmukhi", "or": "Odia", "gu": "Gujarati", "en": "Latin"}
NOISE = ("clean", "office", "street")
DEVICES = ("phone", "laptop", "headset", "other")
CANON_RATE = 16000
CLIP_LIMIT = 0.01        # >1% of samples at full scale = clipping
SILENCE_RMS = 1e-4       # below this the recording is effectively empty
MIN_S, MAX_S = 0.5, 60.0


def inspect_audio(path: Path) -> dict:
    """Read a WAV and return format + signal facts. Raises on unreadable audio."""
    with wave.open(str(path), "rb") as wav:
        channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
        frames = wav.getnframes()
        raw = wav.readframes(frames)
    if width != 2:
        raise ValueError(f"not PCM16 (sample width {width}); convert externally first")
    data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    duration = len(data) / float(rate) if rate else 0.0
    rms = float(np.sqrt(np.mean(data ** 2))) if data.size else 0.0
    clip_ratio = float(np.mean(np.abs(data) >= 0.999)) if data.size else 0.0
    return {"rate": rate, "channels": channels, "width": width, "frames": frames,
            "duration_s": round(duration, 3), "rms": rms, "clip_ratio": clip_ratio,
            "sha256": hashlib.sha256(raw).hexdigest(), "mono_data": data}


def convert_to_canonical(info: dict, src: Path, dst: Path, originals: Path) -> None:
    """Resample/downmix to 16 kHz mono PCM16; keep the untouched original."""
    from scipy.signal import resample_poly
    data = info["mono_data"]
    rate = info["rate"]
    if rate != CANON_RATE:
        from math import gcd
        g = gcd(rate, CANON_RATE)
        data = resample_poly(data, CANON_RATE // g, rate // g)
    pcm = np.clip(data * 32768.0, -32768, 32767).astype("<i2")
    dst.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dst), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(CANON_RATE)
        wav.writeframes(pcm.tobytes())
    originals.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, originals / (dst.stem + src.suffix))


def load_manifest(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def save_manifest(path: Path, entries: list[dict]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries),
                   encoding="utf-8")
    tmp.replace(path)


def check_candidate(info: dict, lang: str, reference: str, speaker: str,
                    consent: bool, noise: str, device: str,
                    entries: list[dict], convert: bool) -> list[str]:
    """Every rejection reason for a candidate recording (empty list = accept)."""
    problems = []
    if lang not in LANGS:
        problems.append(f"invalid language code '{lang}'")
    if not isinstance(reference, str) or not reference.strip():
        problems.append("missing reference text (must be human-written, never ASR output)")
    if not speaker or not speaker.strip():
        problems.append("missing pseudonymous speaker_id")
    if consent is not True:
        problems.append("incomplete consent record: --consent asserts recorded speaker permission")
    if noise not in NOISE:
        problems.append(f"noise_condition must be one of {NOISE}")
    if device not in DEVICES:
        problems.append(f"device must be one of {DEVICES}")
    if info["frames"] == 0 or info["duration_s"] <= 0:
        problems.append("empty audio (zero frames)")
    if not MIN_S <= info["duration_s"] <= MAX_S:
        problems.append(f"duration {info['duration_s']}s outside {MIN_S}-{MAX_S} s")
    if info["rms"] < SILENCE_RMS:
        problems.append(f"effectively silent audio (RMS {info['rms']:.2e})")
    if info["clip_ratio"] > CLIP_LIMIT:
        problems.append(f"clipping: {info['clip_ratio']:.1%} of samples at full scale")
    if (info["rate"] != CANON_RATE or info["channels"] != 1) and not convert:
        problems.append(f"non-canonical format ({info['rate']} Hz, {info['channels']} ch); "
                        "pass --convert to resample (original is preserved)")
    for e in entries:
        if e.get("status") == "COLLECTED" and e.get("audio_sha256") == info["sha256"]:
            problems.append(f"duplicate audio: identical PCM already collected as {e['id']}")
            break
    return problems


def ingest(root: Path, manifest: Path, audio: Path, lang: str, reference: str,
           speaker: str, consent: bool, noise: str, device: str,
           slot_id: str | None = None, convert: bool = False,
           environment: str | None = None, dry_run: bool = False) -> tuple[list[str], dict | None]:
    """Validate and (unless dry_run) fill a slot. Returns (problems, entry)."""
    if not audio.exists():
        return [f"missing file: {audio}"], None
    try:
        info = inspect_audio(audio)
    except (wave.Error, EOFError, ValueError) as exc:
        return [f"corrupted or unsupported audio: {exc}"], None
    entries = load_manifest(manifest)
    problems = check_candidate(info, lang, reference, speaker, consent, noise,
                               device, entries, convert)
    if problems:
        return problems, None
    if slot_id:
        slot = next((e for e in entries if e["id"] == slot_id), None)
        if slot is None:
            return [f"unknown slot id '{slot_id}'"], None
    else:
        slot = next((e for e in entries if e["lang"] == lang
                     and e["status"] == "NOT_COLLECTED"), None)
        if slot is None:
            return [f"no NOT_COLLECTED slot left for '{lang}'"], None
    if slot["status"] != "NOT_COLLECTED":
        return [f"slot {slot['id']} is {slot['status']}, not NOT_COLLECTED"], None
    if slot["lang"] != lang:
        return [f"slot {slot['id']} belongs to '{slot['lang']}', not '{lang}'"], None

    rel_audio = Path(slot["audio_path"])
    if dry_run:
        return [], {**slot, "status": "COLLECTED(dry-run)", "duration_s": info["duration_s"]}
    dst = root / rel_audio
    if info["rate"] != CANON_RATE or info["channels"] != 1:
        convert_to_canonical(info, audio, dst, root / "evaluation" / "dataset" / "originals")
        final = inspect_audio(dst)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(audio, dst)
        final = info
    slot.update({
        "status": "COLLECTED",
        "reference_text": reference.strip(),
        "speaker_id": speaker.strip(),
        "consent": True,
        "noise_condition": noise,
        "device": device,
        "duration_s": final["duration_s"],
        "collected_at": date.today().isoformat(),
        "script": SCRIPTS.get(lang),
        "sample_rate": CANON_RATE,
        "environment": environment,
        "transcript_verified": False,
        "transcript_verified_by": None,
        "audio_sha256": final["sha256"],
        "notes": None,
    })
    save_manifest(manifest, entries)
    return [], slot


def verify_transcript(manifest: Path, slot_id: str, verifier: str) -> list[str]:
    """Record a human assertion that the reference matches the audio."""
    entries = load_manifest(manifest)
    slot = next((e for e in entries if e["id"] == slot_id), None)
    if slot is None:
        return [f"unknown slot id '{slot_id}'"]
    if slot["status"] != "COLLECTED":
        return [f"slot {slot_id} is not COLLECTED"]
    if not verifier or not verifier.strip():
        return ["missing pseudonymous verifier id"]
    if verifier.strip() == slot.get("speaker_id"):
        return ["verifier should be a second native/fluent speaker, not the recorder"]
    slot["transcript_verified"] = True
    slot["transcript_verified_by"] = verifier.strip()
    save_manifest(manifest, entries)
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd")
    p_ing = sub.add_parser("ingest", help="validate + fill a slot (default)")
    for p in (parser, p_ing):
        p.add_argument("--audio")
        p.add_argument("--lang")
        p.add_argument("--reference")
        p.add_argument("--reference-file", help="UTF-8 file with the human reference text")
        p.add_argument("--speaker")
        p.add_argument("--consent", action="store_true",
                       help="asserts recorded informed consent was obtained")
        p.add_argument("--noise", default="clean", choices=NOISE)
        p.add_argument("--device", default="phone", choices=DEVICES)
        p.add_argument("--id", dest="slot_id", default=None)
        p.add_argument("--convert", action="store_true")
        p.add_argument("--environment", default=None)
        p.add_argument("--dry-run", action="store_true")
        p.add_argument("--manifest", default=str(ROOT / "evaluation" / "dataset_manifest.jsonl"))
        p.add_argument("--root", default=str(ROOT))
    p_ver = sub.add_parser("verify", help="record human transcript verification")
    p_ver.add_argument("--id", required=True)
    p_ver.add_argument("--verifier", required=True)
    p_ver.add_argument("--manifest", default=str(ROOT / "evaluation" / "dataset_manifest.jsonl"))
    args = parser.parse_args(argv)

    manifest = Path(args.manifest)
    if args.cmd == "verify":
        problems = verify_transcript(manifest, args.id, args.verifier)
    else:
        reference = args.reference
        if args.reference_file:
            reference = Path(args.reference_file).read_text(encoding="utf-8")
        missing = [k for k in ("audio", "lang", "speaker") if not getattr(args, k)]
        if missing or not reference:
            print("rejected: " + "; ".join(
                [f"missing --{k}" for k in missing]
                + (["missing --reference/--reference-file"] if not reference else [])))
            return 1
        problems, slot = ingest(Path(args.root), manifest, Path(args.audio), args.lang,
                                reference, args.speaker, args.consent, args.noise,
                                args.device, args.slot_id, args.convert,
                                args.environment, args.dry_run)
        if not problems:
            print(f"{'dry-run OK' if args.dry_run else 'ingested'}: {slot['id']} "
                  f"({slot.get('duration_s', '?')}s, {args.lang})")
    if problems:
        print("rejected:")
        for p in problems:
            print(f"  - {p}")
        return 1
    if args.cmd == "verify":
        print(f"transcript verified: {args.id} by {args.verifier}")
    return 0


if __name__ == "__main__":
    sys.exit(main())