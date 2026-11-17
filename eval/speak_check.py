"""Does the voice actually speak? Local, measured evidence per language.

For every reference sentence in the fixed eval corpus this script:

1. renders it with the *production* playback path (``TTSEngine.render_sentence``,
   the same humanised audio the server pushes to the speaker) and saves the wav;
2. measures objective signal health on that wav (duration, level, clipping,
   voiced fraction, speech-band energy, spectral centroid);
3. round-trips the saved wav through the *local* production recogniser and
   scores CER/WER against the reference text;
4. checks the transcript came back in the language's own script.

No cloud inference, no LLM, no playback on this machine. Every run writes a NEW
directory; previous results are never touched.

Caveat that must travel with every number: the audio is TTS-synthesised, so the
round-trip flatters the recogniser (same domain, clean channel). It is evidence
that the voice produces intelligible speech, NOT evidence about real callers.
Human listening / MOS is not performed here.

Usage:
    .venv313/Scripts/python.exe eval/speak_check.py
    .venv313/Scripts/python.exe eval/speak_check.py --langs hi,ta,en
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import unicodedata
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import config                                    # noqa: E402
from src.evaluate import CORPUS, cer, edit_distance, normalise, read_wav, wer  # noqa: E402
from src.sts_pipeline import shared_stt                   # noqa: E402
from src.tts_engine import TTSEngine                      # noqa: E402

LANGS = ["hi", "gu", "mr", "bn", "ta", "te", "kn", "ml", "pa", "or", "as", "en"]

#: Engineering gates chosen for this check (not user-specified tolerances).
#: Gates use the punctuation-corrected score (see clean_norm); the raw harness
#: score is reported alongside it for comparability with earlier eval runs.
GATE = {
    "min_duration_s": 0.4,
    "min_rms_dbfs": -35.0,
    "min_voiced_frac": 0.30,
    "max_clip_frac": 0.002,
    "min_speech_band_ratio": 0.50,
    "max_cer_clean": 0.15,
    "max_wer_clean": 0.30,
}

EXPECTED_SCRIPT = {
    "hi": "devanagari", "mr": "devanagari", "gu": "gujarati", "bn": "bengali",
    "as": "bengali", "pa": "gurmukhi", "ta": "tamil", "te": "telugu",
    "kn": "kannada", "ml": "malayalam", "or": "oriya", "en": "latin",
}

_DIGIT_WORDS = "zero one two three four five six seven eight nine".split()


def clean_norm(text: str) -> str:
    """NFC + lower-case, drop every punctuation/symbol codepoint, collapse space.

    ``src.evaluate.normalise`` keeps U+0964 (danda) because it lies inside the
    Devanagari block it preserves, so a perfect Hindi transcript still scores
    ~1/len characters of error. This variant removes punctuation by Unicode
    category instead of by block, which is what CER/WER are meant to measure.
    """
    text = unicodedata.normalize("NFC", text or "").lower()
    kept = [" " if unicodedata.category(ch).startswith(("P", "S", "Z")) else ch
            for ch in text]
    return " ".join("".join(kept).split())


def cer_clean(ref: str, hyp: str) -> float:
    r, h = clean_norm(ref).replace(" ", ""), clean_norm(hyp).replace(" ", "")
    return edit_distance(list(r), list(h)) / max(len(r), 1)


def wer_clean(ref: str, hyp: str) -> float:
    r, h = clean_norm(ref).split(), clean_norm(hyp).split()
    return edit_distance(r, h) / max(len(r), 1)


def expand_digits(text: str) -> str:
    """whisper-base writes 'one two three' as '1-2-3'; undo that for diagnosis."""
    return re.sub(r"\d+", lambda m: " ".join(_DIGIT_WORDS[int(c)] for c in m.group()), text)


def dbfs(value: float) -> float:
    return round(20 * np.log10(max(value, 1e-9)), 2)


def signal_stats(audio: np.ndarray, rate: int) -> dict:
    """Objective health of one rendered clip. No perceptual judgement."""
    if audio.size == 0:
        return {"samples": 0, "duration_s": 0.0, "audible": False}
    frame = max(1, int(rate * 0.02))
    count = len(audio) // frame
    blocks = audio[: count * frame].reshape(count, frame)
    energy = np.sqrt((blocks.astype(np.float64) ** 2).mean(axis=1))
    peak_frame = float(energy.max()) if energy.size else 0.0
    voiced = np.flatnonzero(energy > max(peak_frame * 0.06, 1e-4))
    rms = float(np.sqrt((audio.astype(np.float64) ** 2).mean()))
    peak = float(np.abs(audio).max())
    spectrum = np.abs(np.fft.rfft(audio.astype(np.float64))) ** 2
    freqs = np.fft.rfftfreq(len(audio), 1.0 / rate)
    total = float(spectrum.sum()) or 1.0
    band = float(spectrum[(freqs >= 300) & (freqs <= 3400)].sum()) / total
    centroid = float((freqs * spectrum).sum() / total)
    lead = float(voiced[0] * frame / rate) if voiced.size else len(audio) / rate
    trail = float((len(audio) - (voiced[-1] + 1) * frame) / rate) if voiced.size else 0.0
    return {
        "samples": int(audio.size),
        "sample_rate": int(rate),
        "duration_s": round(len(audio) / rate, 3),
        "rms_dbfs": dbfs(rms),
        "peak_dbfs": dbfs(peak),
        "clip_frac": round(float(np.mean(np.abs(audio) >= 0.999)), 5),
        "dc_offset": round(float(audio.mean()), 5),
        "voiced_frac": round(float(voiced.size / max(count, 1)), 3),
        "lead_silence_s": round(lead, 3),
        "trail_silence_s": round(trail, 3),
        "speech_band_ratio": round(band, 3),
        "spectral_centroid_hz": round(centroid, 1),
    }


def gate_signal(stats: dict) -> list[str]:
    fails = []
    if stats.get("duration_s", 0) < GATE["min_duration_s"]:
        fails.append("duration")
    if stats.get("rms_dbfs", -99) < GATE["min_rms_dbfs"]:
        fails.append("level")
    if stats.get("voiced_frac", 0) < GATE["min_voiced_frac"]:
        fails.append("voiced_fraction")
    if stats.get("clip_frac", 1) > GATE["max_clip_frac"]:
        fails.append("clipping")
    if stats.get("speech_band_ratio", 0) < GATE["min_speech_band_ratio"]:
        fails.append("speech_band_energy")
    return fails


def local_stt(lang: str):
    """Force a local recogniser: never route this check to cloud ASR."""
    backend = "indic" if config.has_indic_asr(lang) else "whisper"
    return shared_stt(backend, lang)


def check_language(lang: str, out_dir: Path, sentences: list[str]) -> dict:
    voice = TTSEngine(lang)
    stt = local_stt(lang)
    audio_dir = out_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, reference in enumerate(sentences, 1):
        started = time.perf_counter()
        raw = voice.synthesize(reference)
        raw_ms = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        rendered = voice.render_sentence(reference)
        render_ms = (time.perf_counter() - started) * 1000

        name = f"{lang}_{index:02d}.wav"
        path = audio_dir / name
        voice.save_wav(path, rendered)

        # score the artifact that was written, not the in-memory array
        heard = read_wav(path)
        started = time.perf_counter()
        hypothesis = stt.transcribe(heard, config.SAMPLE_RATE)
        asr_ms = (time.perf_counter() - started) * 1000

        stats = signal_stats(rendered, voice.sample_rate)
        raw_stats = signal_stats(raw, voice.sample_rate)
        signal_fails = gate_signal(stats)
        c, w = round(cer(reference, hypothesis), 3), round(wer(reference, hypothesis), 3)
        cc, wc = round(cer_clean(reference, hypothesis), 3), round(wer_clean(reference, hypothesis), 3)
        itn = round(cer_clean(reference, expand_digits(hypothesis)), 3) if lang == "en" else None
        script = config.detect_script(hypothesis) or ("latin" if hypothesis else "")
        script_ok = (not hypothesis) or script == EXPECTED_SCRIPT[lang]
        intelligible = cc <= GATE["max_cer_clean"] and wc <= GATE["max_wer_clean"]
        notes = []
        if c > 0 and cc == 0:
            notes.append("raw-harness error is punctuation only (danda counted as a character)")
        if lang == "en" and cc > 0 and itn == 0:
            notes.append("miss is whisper digit formatting ('1-2-3' for 'one two three'), not missing speech")
        if not hypothesis:
            notes.append("empty transcript from the local recogniser")
        rows.append({
            "wav": f"audio/{name}",
            "reference": reference,
            "prepared": voice.prepare(reference),
            "hypothesis": hypothesis,
            "cer": c,
            "wer": w,
            "cer_clean": cc,
            "wer_clean": wc,
            "cer_clean_digit_expanded": itn,
            "script": script,
            "script_ok": bool(script_ok),
            "tts_backend": voice.backend,
            "asr_backend": getattr(stt, "backend", "?"),
            "raw_synth_ms": round(raw_ms, 1),
            "render_ms": round(render_ms, 1),
            "asr_ms": round(asr_ms, 1),
            "render_rtf": round(render_ms / max(stats["duration_s"] * 1000, 1), 3),
            "signal": stats,
            "raw_signal": raw_stats,
            "signal_gate_fails": signal_fails,
            "intelligible": bool(intelligible),
            "notes": notes,
            "status": ("PASS (automated)" if not signal_fails and intelligible and script_ok
                       else "FAIL" if signal_fails else "PARTIAL"),
        })
        print(f"  {name} cer={c:.3f} clean={cc:.3f} wer={w:.3f} {stats['duration_s']:.2f}s "
              f"rms={stats['rms_dbfs']}dBFS voiced={stats['voiced_frac']} "
              f"-> {rows[-1]['status']}", flush=True)

    audible = all(not r["signal_gate_fails"] for r in rows)
    scored = all(r["intelligible"] and r["script_ok"] for r in rows)
    status = ("PASS (automated)" if audible and scored
              else "FAIL" if not audible else "PARTIAL")
    return {
        "lang": lang,
        "n": len(rows),
        "tts_backend": voice.backend,
        "asr_backend": getattr(stt, "backend", "?"),
        "sample_rate": voice.sample_rate,
        "cer_mean": round(statistics.mean(r["cer"] for r in rows), 3),
        "wer_mean": round(statistics.mean(r["wer"] for r in rows), 3),
        "cer_clean_mean": round(statistics.mean(r["cer_clean"] for r in rows), 3),
        "wer_clean_mean": round(statistics.mean(r["wer_clean"] for r in rows), 3),
        "cer_clean_max": max(r["cer_clean"] for r in rows),
        "duration_mean_s": round(statistics.mean(r["signal"]["duration_s"] for r in rows), 3),
        "render_rtf_mean": round(statistics.mean(r["render_rtf"] for r in rows), 3),
        "audible_all": audible,
        "status": status,
        "rows": rows,
    }


def render_report(results: list[dict], gates: dict, run_dir: Path) -> str:
    lines = [
        "# IndicVoice — does the voice speak? (local measured check)",
        "",
        f"Run: `{run_dir.name}` · generated {time.strftime('%Y-%m-%d %H:%M:%S')} · "
        f"host CPU-only, no cloud inference, no LLM, no playback on this machine.",
        "",
        "## What was measured",
        "",
        "Each corpus sentence was rendered through the production playback path "
        "(`TTSEngine.render_sentence`, humanised — the same audio the server pushes to "
        "the speaker), saved as a mono PCM16 wav, then:",
        "",
        "* objective signal health of the saved wav (duration, RMS/peak, clipping, "
        "voiced fraction, 300–3400 Hz energy ratio, spectral centroid);",
        "* round-trip through the local production recogniser, CER/WER vs the reference;",
        "* script check on the transcript.",
        "",
        "## Two CER/WER columns, and why",
        "",
        "* `cer` / `wer` — exactly what `src.evaluate` computes, comparable with earlier "
        "eval runs. Its `normalise` keeps U+0964 (danda) because that codepoint sits inside "
        "the Devanagari block it preserves, so a *perfect* Hindi transcript still scores "
        "about 1/len ≈ 0.04. That is a scoring artifact, not speech error.",
        "* `cer_clean` / `wer_clean` — punctuation and symbols removed by Unicode category "
        "before scoring. **The gates use this column.** The production harness was not modified.",
        "* `cer_itn` (English only) — clean CER after expanding whisper's digits back to words "
        "(`1-2-3` → `one two three`). Diagnostic only, never used by a gate.",
        "",
        "## Gates (engineering thresholds chosen for this check)",
        "",
        "```json", json.dumps(gates, indent=2), "```",
        "",
        "Status vocabulary: PASS (automated) / PARTIAL / FAIL. "
        "**Human listening and MOS: NOT TESTED** — nobody listened to these clips as part of "
        "this run; the wavs are packaged so that listening can happen.",
        "",
        "## Per-language result",
        "",
        "| lang | n | TTS | ASR | CER raw | CER clean | CER clean max | WER clean | mean s | render RTF | audible | status |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        if not r.get("n"):
            lines.append(f"| {r['lang']} | 0 | {r.get('tts_backend','?')} | - | - | - | - | - | - | - | NO | {r['status']} |")
            continue
        lines.append(
            f"| {r['lang']} | {r['n']} | {r['tts_backend']} | {r['asr_backend']} | "
            f"{r['cer_mean']:.3f} | {r['cer_clean_mean']:.3f} | {r['cer_clean_max']:.3f} | "
            f"{r['wer_clean_mean']:.3f} | {r['duration_mean_s']:.2f} | {r['render_rtf_mean']:.2f} | "
            f"{'yes' if r['audible_all'] else 'NO'} | {r['status']} |"
        )
    lines += ["", "## Per-clip detail", ""]
    for r in results:
        lines.append(f"### {r['lang']} — {r['status']}")
        lines.append("")
        if not r.get("n"):
            lines.append(f"* run error: {r.get('error', 'unknown')}")
            lines.append("")
            continue
        for row in r["rows"]:
            s = row["signal"]
            extra = f", cer_itn {row['cer_clean_digit_expanded']:.3f}" if row["cer_clean_digit_expanded"] is not None else ""
            lines.append(
                f"* `{row['wav']}` — {row['status']}; CER raw {row['cer']:.3f} / clean {row['cer_clean']:.3f}{extra}, "
                f"WER clean {row['wer_clean']:.3f}; "
                f"{s['duration_s']:.2f}s, RMS {s['rms_dbfs']} dBFS, peak {s['peak_dbfs']} dBFS, "
                f"clipped {s['clip_frac'] * 100:.3f}%, voiced {s['voiced_frac'] * 100:.0f}%, "
                f"speech-band {s['speech_band_ratio'] * 100:.0f}%, centroid {s['spectral_centroid_hz']:.0f} Hz; "
                f"render {row['render_ms']:.0f} ms, ASR {row['asr_ms']:.0f} ms"
            )
            lines.append(f"  * ref: {row['reference']}")
            lines.append(f"  * heard: {row['hypothesis'] or '(empty transcript)'}")
            if row["signal_gate_fails"]:
                lines.append(f"  * signal gate fails: {', '.join(row['signal_gate_fails'])}")
            if not row["script_ok"]:
                lines.append(f"  * script mismatch: got {row['script']}, expected {EXPECTED_SCRIPT[r['lang']]}")
            for note in row["notes"]:
                lines.append(f"  * note: {note}")
        lines.append("")
    lines += [
        "## Caveats (read before quoting any number)",
        "",
        "* Audio is **TTS-synthesised**, not real recordings. The round-trip shares the "
        "synthesis domain and a clean channel, so it flatters the recogniser. These CER/WER "
        "values are an intelligibility proxy for the voice, not production ASR accuracy, and "
        "they count as 0 real recordings collected.",
        "* Assamese is decoded with the Bengali Conformer (no Assamese ONNX export exists); "
        "Bengali orthography in the transcript is expected and scores as errors.",
        "* A low CER proves the recogniser recovered the words; it does not prove naturalness, "
        "prosody, or absence of artefacts. Only human listening can judge those: NOT TESTED.",
        "* One render per sentence, single speaker (sid 0), default speed. Run-to-run thermal "
        "variance on this 15 W laptop affects the millisecond columns, not the audio.",
        "* Signal gates prove the output is audible speech-band energy, not silence, noise or "
        "clipping. They cannot prove the words sound right to a native listener.",
        "",
    ]
    return "\n".join(lines)


COVER = """# Speak-check evidence bundle

Open `report.md` first. `audio/` holds every rendered clip (24 kHz mono PCM16 wav),
named `<lang>_<NN>.wav`; `results.json` is the machine-readable form of the report.

What this is: a local, CPU-only measurement of whether the production voice renders
audible, intelligible speech in each of the 12 languages, using the same
`render_sentence` path the live server plays.

What this is NOT: real-caller evidence, a MOS study, or a production-readiness claim.
The audio is synthesised by the same engine that is being tested, so the ASR
round-trip flatters the result. Human listening has not been performed.

To listen: play the wavs in `audio/` and judge naturalness yourself; the report's
CER/WER columns only say whether a local recogniser recovered the reference words.

Reproduce: `.venv313/Scripts/python.exe eval/speak_check.py` (writes a new run dir).
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local TTS render + round-trip speak check")
    parser.add_argument("--langs", default=",".join(LANGS))
    parser.add_argument("--sentences", type=int, default=3, help="corpus sentences per language")
    parser.add_argument("--out", default=None, help="run directory (default: a new timestamped dir)")
    parser.add_argument("--no-zip", action="store_true")
    args = parser.parse_args(argv)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = Path(args.out) if args.out else ROOT / "eval" / f"speak_check_{stamp}"
    if run_dir.exists() and any(run_dir.iterdir()):
        print(f"refusing to write into non-empty {run_dir}", file=sys.stderr)
        return 2
    run_dir.mkdir(parents=True, exist_ok=True)

    langs = [config.resolve_lang(x.strip()) for x in args.langs.split(",") if x.strip()]
    results = []
    for lang in langs:
        sentences = CORPUS[lang][: args.sentences]
        print(f"[{lang}] tts={config.tts_backend(lang)} sentences={len(sentences)}", flush=True)
        try:
            results.append(check_language(lang, run_dir, sentences))
        except Exception as exc:
            print(f"[{lang}] ERROR {type(exc).__name__}: {exc}", flush=True)
            results.append({"lang": lang, "n": 0, "status": "FAIL", "error": f"{type(exc).__name__}: {exc}",
                            "rows": [], "audible_all": False, "cer_mean": None, "wer_mean": None,
                            "cer_max": None, "duration_mean_s": 0, "render_rtf_mean": 0,
                            "tts_backend": config.tts_backend(lang), "asr_backend": "?", "sample_rate": 0})

    payload = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "run": run_dir.name,
        "source": "synthetic (TTS render of the fixed eval corpus)",
        "cloud_inference": False,
        "playback_on_host": False,
        "human_listening": "NOT TESTED",
        "gates": GATE,
        "languages": results,
    }
    (run_dir / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report = render_report(results, GATE, run_dir)
    (run_dir / "report.md").write_text(report, encoding="utf-8")
    (run_dir / "README.md").write_text(COVER, encoding="utf-8")
    print("\n" + report.split("## Per-clip detail")[0])

    if not args.no_zip:
        zip_path = run_dir.with_suffix(".zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as bundle:
            for name in ("README.md", "report.md", "results.json"):
                bundle.write(run_dir / name, name)
            for wav in sorted((run_dir / "audio").glob("*.wav")):
                bundle.write(wav, f"audio/{wav.name}")
        print(f"bundle -> {zip_path} ({zip_path.stat().st_size / 1e6:.2f} MB)")
    print(f"run dir -> {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())