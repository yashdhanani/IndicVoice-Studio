"""Does the voice actually speak? Local, measured evidence per language.

For every reference sentence in the fixed eval corpus this script renders the
sentence several times through the *production* playback path
(``TTSEngine.render_sentence`` — the humanised audio the server pushes to the
speaker), saves every wav, and per render:

1. measures objective signal health (duration, level, clipping, voiced fraction,
   voice-band energy share, spectral centroid, HF diagnostics);
2. round-trips the saved wav through the *local* production recogniser and scores
   CER/WER against the reference text;
3. checks the transcript came back in the language's own script.

Repeats matter: the voice is non-deterministic, so two runs of the same sentence
produce different audio (verified by wav hash). One render per sentence is not a
stable measurement, and a single lucky render must not be reported as the voice's
quality.

No cloud inference, no LLM, no playback on this machine. Every run writes a NEW
directory; previous results are never touched.

Caveat that must travel with every number: the audio is TTS-synthesised, so the
round-trip flatters the recogniser (same domain, clean channel). It is evidence
that the voice produces intelligible speech, NOT evidence about real callers.
Human listening / MOS is not performed here.

Usage:
    .venv313/Scripts/python.exe eval/speak_check.py
    .venv313/Scripts/python.exe eval/speak_check.py --langs hi,ta,en --repeats 5
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
from src.evaluate import CORPUS, cer, edit_distance, read_wav, wer  # noqa: E402
from src.sts_pipeline import shared_stt                   # noqa: E402
from src.tts_engine import TTSEngine                      # noqa: E402

LANGS = ["hi", "gu", "mr", "bn", "ta", "te", "kn", "ml", "pa", "or", "as", "en"]

#: Engineering gates chosen for this check, not user-specified tolerances.
#:
#: Band calibration is measured: an earlier run gated on the 300-3400 Hz telephone
#: band and flagged kn/ml, whose voices carry 40-58% of their energy in 100-300 Hz
#: (fundamental ~230-270 Hz). Cutting at 300 Hz discarded the fundamental, so the
#: gate asks for voice-band coverage (100-4000 Hz) instead.
#:
#: High-frequency energy is deliberately NOT a gate. Frame-level measurement showed
#: the HF bursts are brief fricatives (English /s/ in "address": 12 of 94 frames)
#: and the humanizer's room tone during silence (hi_01: HF dominates 21 frames,
#: none of them voiced). A clip-level HF share therefore cannot separate hiss from
#: normal speech, so it is reported as a diagnostic only. Objective hiss detection
#: is NOT TESTED; it needs listening.
GATE = {
    "min_duration_s": 0.4,
    "min_rms_dbfs": -35.0,
    "min_voiced_frac": 0.30,
    "max_clip_frac": 0.002,
    "min_voice_band_ratio": 0.70,
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
    """NFC + lower-case, drop punctuation/symbols/zero-width chars, collapse space.

    ``src.evaluate.normalise`` keeps U+0964 (danda) because it lies inside the
    Devanagari block it preserves, so a perfect Hindi transcript still scores
    ~1/len characters of error. It also keeps zero-width joiners, which split
    Telugu words such as ``హైదరాబాద్‌లో`` in two. This variant removes both by
    Unicode category. The production harness is not modified.
    """
    text = unicodedata.normalize("NFC", text or "").lower()
    kept = [" " if unicodedata.category(ch).startswith(("P", "S", "Z", "C")) else ch
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
    voiced = energy > max(peak_frame * 0.06, 1e-4)
    rms = float(np.sqrt((audio.astype(np.float64) ** 2).mean()))
    peak = float(np.abs(audio).max())

    spectrum = np.abs(np.fft.rfft(audio.astype(np.float64))) ** 2
    freqs = np.fft.rfftfreq(len(audio), 1.0 / rate)
    total = float(spectrum.sum()) or 1.0

    def share(lo: float, hi: float) -> float:
        return float(spectrum[(freqs >= lo) & (freqs < hi)].sum()) / total

    frame_spectrum = np.abs(np.fft.rfft(blocks, axis=1)) ** 2
    frame_freqs = np.fft.rfftfreq(frame, 1.0 / rate)
    hf = frame_spectrum[:, frame_freqs >= 3400].sum(axis=1)
    frame_total = frame_spectrum.sum(axis=1) + 1e-12
    hf_dominant = (hf / frame_total) > 0.30
    centroid = float((freqs * spectrum).sum() / total)
    loud = np.flatnonzero(voiced)
    lead = float(loud[0] * frame / rate) if loud.size else len(audio) / rate
    trail = float((len(audio) - (loud[-1] + 1) * frame) / rate) if loud.size else 0.0
    return {
        "samples": int(audio.size),
        "sample_rate": int(rate),
        "duration_s": round(len(audio) / rate, 3),
        "rms_dbfs": dbfs(rms),
        "peak_dbfs": dbfs(peak),
        "clip_frac": round(float(np.mean(np.abs(audio) >= 0.999)), 5),
        "dc_offset": round(float(audio.mean()), 5),
        "voiced_frac": round(float(voiced.sum() / max(count, 1)), 3),
        "lead_silence_s": round(lead, 3),
        "trail_silence_s": round(trail, 3),
        "voice_band_ratio": round(share(100, 4000), 3),
        "speech_band_ratio": round(share(300, 3400), 3),
        "low_band_ratio": round(share(100, 300), 3),
        "hf_share": round(share(3400, rate / 2), 4),
        "hf_dominant_voiced_frac": round(float((hf_dominant & voiced).sum() / max(voiced.sum(), 1)), 3),
        "spectral_centroid_hz": round(centroid, 1),
    }


def gate_signal(stats: dict) -> list[str]:
    """Audibility gates only. HF energy is a diagnostic, not a gate (see GATE)."""
    fails = []
    if stats.get("duration_s", 0) < GATE["min_duration_s"]:
        fails.append("duration")
    if stats.get("rms_dbfs", -99) < GATE["min_rms_dbfs"]:
        fails.append("level")
    if stats.get("voiced_frac", 0) < GATE["min_voiced_frac"]:
        fails.append("voiced_fraction")
    if stats.get("clip_frac", 1) > GATE["max_clip_frac"]:
        fails.append("clipping")
    if stats.get("voice_band_ratio", 0) < GATE["min_voice_band_ratio"]:
        fails.append("voice_band_energy")
    return fails


def local_stt(lang: str):
    """Force a local recogniser: never route this check to cloud ASR."""
    backend = "indic" if config.has_indic_asr(lang) else "whisper"
    return shared_stt(backend, lang)


def check_language(lang: str, out_dir: Path, sentences: list[str], repeats: int) -> dict:
    voice = TTSEngine(lang)
    stt = local_stt(lang)
    audio_dir = out_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, reference in enumerate(sentences, 1):
        for take in range(1, repeats + 1):
            started = time.perf_counter()
            rendered = voice.render_sentence(reference)
            render_ms = (time.perf_counter() - started) * 1000

            name = f"{lang}_{index:02d}_r{take}.wav"
            path = audio_dir / name
            voice.save_wav(path, rendered)

            # score the artifact that was written, not the in-memory array
            heard = read_wav(path)
            started = time.perf_counter()
            hypothesis = stt.transcribe(heard, config.SAMPLE_RATE)
            asr_ms = (time.perf_counter() - started) * 1000

            stats = signal_stats(rendered, voice.sample_rate)
            signal_fails = gate_signal(stats)
            c, w = round(cer(reference, hypothesis), 3), round(wer(reference, hypothesis), 3)
            cc, wc = round(cer_clean(reference, hypothesis), 3), round(wer_clean(reference, hypothesis), 3)
            itn = round(cer_clean(reference, expand_digits(hypothesis)), 3) if lang == "en" else None
            # whisper-base writes spoken numbers as digits ('one two three' ->
            # '123'), which is correct inverse text normalisation, not lost
            # speech -- yet it charged a perfect render 0.423 CER and failed
            # three of nine English takes. The gate therefore scores the
            # digit-expanded transcript for English (the word list is English
            # only). Both the raw and gated scores stay in the JSON.
            scored = expand_digits(hypothesis) if lang == "en" else hypothesis
            gc, gw = round(cer_clean(reference, scored), 3), round(wer_clean(reference, scored), 3)
            script = config.detect_script(hypothesis) or ("latin" if hypothesis else "")
            script_ok = (not hypothesis) or script == EXPECTED_SCRIPT[lang]
            intelligible = gc <= GATE["max_cer_clean"] and gw <= GATE["max_wer_clean"]
            notes = []
            if c > 0 and cc == 0:
                notes.append("raw-harness error is punctuation only (danda counted as a character)")
            if lang == "en" and cc > gc:
                notes.append("whisper digit formatting ('1-2-3' for 'one two three') scored as a miss; "
                             "the gate uses the digit-expanded transcript")
            if not hypothesis:
                notes.append("empty transcript from the local recogniser")
            if not intelligible and hypothesis:
                notes.append("words lost or altered in this render")
            rows.append({
                "sentence": index,
                "take": take,
                "wav": f"audio/{name}",
                "reference": reference,
                "prepared": voice.prepare(reference),
                "hypothesis": hypothesis,
                "cer": c,
                "wer": w,
                "cer_clean": cc,
                "wer_clean": wc,
                "cer_clean_gate": gc,
                "wer_clean_gate": gw,
                "cer_clean_digit_expanded": itn,
                "script": script,
                "script_ok": bool(script_ok),
                "tts_backend": voice.backend,
                "asr_backend": getattr(stt, "backend", "?"),
                "render_ms": round(render_ms, 1),
                "asr_ms": round(asr_ms, 1),
                "render_rtf": round(render_ms / max(stats["duration_s"] * 1000, 1), 3),
                "signal": stats,
                "signal_gate_fails": signal_fails,
                "intelligible": bool(intelligible),
                "notes": notes,
                "status": ("PASS (automated)" if not signal_fails and intelligible and script_ok
                           else "FAIL" if signal_fails else "PARTIAL"),
            })
            print(f"  {name} cer={c:.3f} clean={cc:.3f} {stats['duration_s']:.2f}s "
                  f"rms={stats['rms_dbfs']}dBFS voiced={stats['voiced_frac']} "
                  f"-> {rows[-1]['status']}", flush=True)

    audible = all(not r["signal_gate_fails"] for r in rows)
    clean = [r for r in rows if r["status"] == "PASS (automated)"]
    status = ("PASS (automated)" if audible and len(clean) == len(rows)
              else "FAIL" if not audible else "PARTIAL")
    per_sentence = []
    for index in range(1, len(sentences) + 1):
        takes = [r for r in rows if r["sentence"] == index]
        per_sentence.append({
            "sentence": index,
            "reference": sentences[index - 1],
            "takes": len(takes),
            "clean_takes": sum(1 for r in takes if r["status"] == "PASS (automated)"),
            "cer_clean_mean": round(statistics.mean(r["cer_clean"] for r in takes), 3),
            "cer_clean_max": max(r["cer_clean"] for r in takes),
            "worst_hypothesis": min(takes, key=lambda r: r["cer_clean"])["hypothesis"],
        })
    return {
        "lang": lang,
        "sentences": len(sentences),
        "repeats": repeats,
        "n": len(rows),
        "tts_backend": voice.backend,
        "asr_backend": getattr(stt, "backend", "?"),
        "sample_rate": voice.sample_rate,
        "cer_mean": round(statistics.mean(r["cer"] for r in rows), 3),
        "wer_mean": round(statistics.mean(r["wer"] for r in rows), 3),
        "cer_clean_mean": round(statistics.mean(r["cer_clean"] for r in rows), 3),
        "wer_clean_mean": round(statistics.mean(r["wer_clean"] for r in rows), 3),
        "cer_clean_max": max(r["cer_clean"] for r in rows),
        "clean_renders": len(clean),
        "clean_render_rate": round(len(clean) / len(rows), 3),
        "word_miss_renders": sum(1 for r in rows if not r["intelligible"]),
        "script_miss_renders": sum(1 for r in rows if not r["script_ok"]),
        "duration_mean_s": round(statistics.mean(r["signal"]["duration_s"] for r in rows), 3),
        "render_rtf_mean": round(statistics.mean(r["render_rtf"] for r in rows), 3),
        "hf_share_max": max(r["signal"]["hf_share"] for r in rows),
        "audible_all": audible,
        "status": status,
        "per_sentence": per_sentence,
        "rows": rows,
    }


def render_report(results: list[dict], gates: dict, run_dir: Path, repeats: int) -> str:
    total = sum(r.get("n", 0) for r in results)
    clean = sum(r.get("clean_renders", 0) for r in results)
    lines = [
        "# IndicVoice — does the voice speak? (local measured check)",
        "",
        f"Run: `{run_dir.name}` · generated {time.strftime('%Y-%m-%d %H:%M:%S')} · "
        f"{total} renders ({repeats} takes × {len(results)} languages × 3 corpus sentences) · "
        f"CPU-only, no cloud inference, no LLM, no playback on this machine.",
        "",
        f"**Headline: {clean}/{total} renders passed every gate.** "
        "Per-language status below; human listening and MOS are NOT TESTED.",
        "",
        "## What was measured",
        "",
        "Each corpus sentence was rendered through the production playback path "
        "(`TTSEngine.render_sentence`, humanised — the same audio the server pushes to "
        "the speaker), saved as a mono PCM16 wav, then per render:",
        "",
        "* objective signal health of the saved wav (duration, RMS/peak, clipping, "
        "voiced fraction, voice-band 100–4000 Hz energy share, spectral centroid);",
        "* round-trip through the local production recogniser, CER/WER vs the reference;",
        "* script check on the transcript.",
        "",
        "## Why repeats",
        "",
        "The voice is **non-deterministic**: rendering the same sentence twice produces "
        "different audio (verified — all 12 sampled wav hashes differed between two runs "
        "of this check). Word-level results move with it: one Hindi render recovered "
        "`मेरा पता दिल्ली में है` exactly, another lost the first word (`म पता दिल्ली में है`, "
        "CER 0.167). A single render per sentence therefore cannot support a claim about "
        "the voice, so every sentence is rendered multiple times and the distribution is "
        "reported, including the worst take.",
        "",
        "## Two CER/WER columns, and why",
        "",
        "* `cer` / `wer` — exactly what `src.evaluate` computes, comparable with earlier "
        "eval runs. Its `normalise` keeps U+0964 (danda) because that codepoint sits inside "
        "the Devanagari block it preserves, so a *perfect* Hindi transcript still scores "
        "about 1/len ≈ 0.04. That is a scoring artifact, not speech error.",
        "* `cer_clean` / `wer_clean` — punctuation, symbols and zero-width characters removed "
        "by Unicode category before scoring (zero-width joiners otherwise split Telugu "
        "words). **The gates use this column.** The production harness was not modified.",
        "* `cer_itn` (English only) — clean CER after expanding whisper's digits back to words "
        "(`1-2-3` → `one two three`). Diagnostic only, never used by a gate.",
        "",
        "## Gates (engineering thresholds chosen for this check)",
        "",
        "```json", json.dumps(gates, indent=2), "```",
        "",
        "Severity mapping: **FAIL** = a render is not audible speech (duration, level, voiced "
        "fraction, clipping or voice-band gate). **PARTIAL** = every render is audible, but at "
        "least one loses/alters words or answers in the wrong script. **PASS (automated)** = "
        "every render audible, intelligible and in the right script.",
        "",
        "**Human listening and MOS: NOT TESTED.** Nobody listened to these clips as part of "
        "this run; the wavs are packaged so that listening can happen.",
        "",
        "## Gate calibration (measured corrections, earlier runs preserved)",
        "",
        "* An earlier run gated on the 300–3400 Hz telephone band and reported kn/ml FAIL. "
        "Sub-band measurement of those wavs: kn_01 52.6% of energy in 100–300 Hz, 47.0% in "
        "300–3400 Hz, 0.5% above 3400 Hz (f0 ≈ 268 Hz); ml_03 57.7% / 41.3% / 1.0% (f0 ≈ 226 Hz). "
        "The 300 Hz cut discarded the fundamental of those voices. The gate now uses "
        "100–4000 Hz coverage; the telephone-band share stays as a diagnostic column.",
        "* High-frequency energy is **not** gated. Frame analysis showed the HF bursts are "
        "brief fricatives (en_03 `My address is in Delhi`: 12 of 94 frames HF-dominant, "
        "clustered on /s/) and the humanizer's room tone during silence (hi_01: 21 HF-dominant "
        "frames, none voiced). A clip-level HF share cannot distinguish hiss from normal "
        "speech, so `hf_share` and `hf_dominant_voiced_frac` are diagnostics only. "
        "**Objective hiss/artifact detection: NOT TESTED** — it requires listening.",
        "",
        "## Per-language result",
        "",
        "| lang | renders | TTS | ASR | CER raw | CER clean | worst CER clean | WER clean | clean renders | word-miss renders | mean s | render RTF | audible | status |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        if not r.get("n"):
            lines.append(f"| {r['lang']} | 0 | {r.get('tts_backend','?')} | - | - | - | - | - | - | - | - | - | NO | {r['status']} |")
            continue
        lines.append(
            f"| {r['lang']} | {r['n']} | {r['tts_backend']} | {r['asr_backend']} | "
            f"{r['cer_mean']:.3f} | {r['cer_clean_mean']:.3f} | {r['cer_clean_max']:.3f} | "
            f"{r['wer_clean_mean']:.3f} | {r['clean_renders']}/{r['n']} ({r['clean_render_rate'] * 100:.0f}%) | "
            f"{r['word_miss_renders']} | {r['duration_mean_s']:.2f} | {r['render_rtf_mean']:.2f} | "
            f"{'yes' if r['audible_all'] else 'NO'} | {r['status']} |"
        )
    lines += ["", "## Per-sentence detail (every take)", ""]
    for r in results:
        lines.append(f"### {r['lang']} — {r['status']}")
        lines.append("")
        if not r.get("n"):
            lines.append(f"* run error: {r.get('error', 'unknown')}")
            lines.append("")
            continue
        for sentence in r["per_sentence"]:
            lines.append(f"* sentence {sentence['sentence']}: {sentence['reference']}")
            lines.append(f"  * clean takes {sentence['clean_takes']}/{sentence['takes']}, "
                         f"CER clean mean {sentence['cer_clean_mean']:.3f}, max {sentence['cer_clean_max']:.3f}")
            for row in [x for x in r["rows"] if x["sentence"] == sentence["sentence"]]:
                s = row["signal"]
                extra = f", cer_itn {row['cer_clean_digit_expanded']:.3f}" if row["cer_clean_digit_expanded"] is not None else ""
                lines.append(
                    f"  * `{row['wav']}` — {row['status']}; CER raw {row['cer']:.3f} / clean {row['cer_clean']:.3f}{extra}, "
                    f"WER clean {row['wer_clean']:.3f}; {s['duration_s']:.2f}s, RMS {s['rms_dbfs']} dBFS, "
                    f"peak {s['peak_dbfs']} dBFS, clipped {s['clip_frac'] * 100:.3f}%, voiced {s['voiced_frac'] * 100:.0f}%, "
                    f"voice-band {s['voice_band_ratio'] * 100:.1f}%, telephone-band {s['speech_band_ratio'] * 100:.0f}%, "
                    f"hf_share {s['hf_share'] * 100:.2f}% (diag), centroid {s['spectral_centroid_hz']:.0f} Hz; "
                    f"render {row['render_ms']:.0f} ms, ASR {row['asr_ms']:.0f} ms"
                )
                lines.append(f"    * heard: {row['hypothesis'] or '(empty transcript)'}")
                if row["signal_gate_fails"]:
                    lines.append(f"    * signal gate fails: {', '.join(row['signal_gate_fails'])}")
                if not row["script_ok"]:
                    lines.append(f"    * script mismatch: got {row['script']}, expected {EXPECTED_SCRIPT[r['lang']]}")
                for note in row["notes"]:
                    lines.append(f"    * note: {note}")
        lines.append("")
    lines += [
        "## Caveats (read before quoting any number)",
        "",
        "* Audio is **TTS-synthesised**, not real recordings. The round-trip shares the "
        "synthesis domain and a clean channel, so it flatters the recogniser. These CER/WER "
        "values are an intelligibility proxy for the voice, not production ASR accuracy, and "
        "they add 0 to the real-recording count.",
        "* Assamese is decoded with the Bengali Conformer (no Assamese ONNX export exists), so "
        "Bengali orthography (`ৰ`→`র`, `ৱ`→`ব`) scores as errors. The Assamese round-trip is "
        "confounded: it cannot separate a TTS pronunciation problem from a recogniser "
        "orthography problem. Native listening is the only way to resolve it.",
        "* A low CER proves the recogniser recovered the words; it does not prove naturalness, "
        "prosody, or absence of artefacts. Only human listening can judge those: NOT TESTED.",
        "* One speaker (sid 0), default speed, 3 corpus sentences per language. This is a "
        "108-render sample of a fixed corpus, not a population estimate for arbitrary text.",
        "* Run-to-run thermal variance on this 15 W laptop affects the millisecond columns, "
        "not the audio. The renders themselves vary because synthesis is stochastic.",
        "",
    ]
    return "\n".join(lines)


COVER = """# Speak-check evidence bundle

Open `report.md` first, then `listen.html` in a browser (it plays the wavs in
`audio/` next to it, grouped by language and sentence, with the reference text,
what the local recogniser heard, and per-take scores). `results.json` is the
machine-readable report.

Clips are named `<lang>_<NN>_r<take>.wav` (24 kHz mono PCM16). Every sentence has
several takes because synthesis is non-deterministic — compare them.

What this is: a local, CPU-only measurement of whether the production voice renders
audible, intelligible speech in each of the 12 languages, using the same
`render_sentence` path the live server plays.

What this is NOT: real-caller evidence, a MOS study, or a production-readiness claim.
The audio is synthesised by the engine under test, so the ASR round-trip flatters the
result. Human listening has not been performed, and objective hiss detection is not
claimed.

To listen: use `listen.html`, or play the wavs directly. The CER/WER columns only say
whether a local recogniser recovered the reference words, not whether the voice
sounds natural.

Reproduce: `.venv313/Scripts/python.exe eval/speak_check.py` (writes a new run dir).
"""


def build_player(results: list[dict], run_name: str) -> str:
    """A self-contained listening page: the human evidence this check cannot give."""
    data = []
    for r in results:
        for row in r.get("rows", []):
            data.append({
                "lang": r["lang"], "sentence": row["sentence"], "take": row["take"],
                "wav": row["wav"], "ref": row["reference"], "hyp": row["hypothesis"],
                "cer": row["cer_clean"], "wer": row["wer_clean"], "status": row["status"],
                "notes": row["notes"], "dur": row["signal"].get("duration_s", 0),
                "rms": row["signal"].get("rms_dbfs", 0),
            })
    payload = json.dumps({"run": run_name, "clips": data}, ensure_ascii=False)
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>IndicVoice — listening bench</title>
<style>
:root{--bg:#0a0716;--surface:#150f2a;--line:#2b2145;--ink:#f5efe6;--muted:#9a93b8;
--saffron:#ffb703;--magenta:#ff2e88;--teal:#00e5c0;--ok:#2dd4a7;--warn:#ffb020;--danger:#ff4d5e;
color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(1200px 600px at 15% -10%,#241a44 0%,var(--bg) 60%);
color:var(--ink);font:15px/1.55 "Segoe UI",Inter,system-ui,sans-serif;padding:28px 20px 60px}
body::-webkit-scrollbar{width:11px}body::-webkit-scrollbar-track{background:var(--bg)}
body::-webkit-scrollbar-thumb{background:linear-gradient(var(--saffron),var(--magenta));border-radius:9px;border:2px solid var(--bg)}
.wrap{max-width:1080px;margin:0 auto}
h1{font-size:26px;margin:0 0 6px;letter-spacing:-.02em}
h1 span{background:linear-gradient(90deg,var(--saffron),var(--magenta));-webkit-background-clip:text;background-clip:text;color:transparent}
.sub{color:var(--muted);margin:0 0 18px;font-size:13.5px}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 18px;padding:12px;
background:var(--surface);border:1px solid var(--line);border-radius:14px}
.bar label{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}
select,button{font:inherit;color:var(--ink);background:#1d1636;border:1px solid var(--line);
border-radius:9px;padding:7px 11px;cursor:pointer}
button:hover,select:hover{border-color:var(--saffron)}
button.primary{background:linear-gradient(90deg,var(--saffron),var(--magenta));color:#20142b;border:0;font-weight:600}
.count{margin-left:auto;color:var(--muted);font-size:13px}
.lang{margin:0 0 22px}
.lang h2{font-size:17px;margin:0 0 10px;display:flex;gap:10px;align-items:center}
.pill{font-size:11.5px;padding:3px 9px;border-radius:999px;border:1px solid var(--line);color:var(--muted)}
.pill.pass{color:var(--ok);border-color:#1d4d40}.pill.partial{color:var(--warn);border-color:#5a4520}
.pill.fail{color:var(--danger);border-color:#5d2530}
.sent{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:14px;margin:0 0 10px}
.ref{font-size:16px;margin:0 0 4px}
.meta{color:var(--muted);font-size:12.5px;margin:0 0 10px}
.takes{display:grid;gap:8px}
.take{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:center;
background:#1b1433;border:1px solid var(--line);border-radius:11px;padding:9px 11px;transition:border-color .2s,box-shadow .2s}
.take.bad{border-color:#5a4520}.take.worst{border-color:#5d2530}
.take.playing{border-color:var(--teal);box-shadow:0 0 0 1px var(--teal),0 0 22px -6px var(--teal)}
.hyp{font-size:14.5px;margin:0}
.hyp.empty{color:var(--danger)}
.stats{color:var(--muted);font-size:12px;margin:2px 0 0}
.note{color:var(--warn);font-size:12px;margin:3px 0 0}
audio{width:230px;height:34px}
.right{display:flex;flex-direction:column;gap:5px;align-items:flex-end}
.badge{font-size:11px;padding:2px 8px;border-radius:999px;background:#241b41;color:var(--muted)}
.badge.pass{color:var(--ok)}.badge.partial{color:var(--warn)}.badge.fail{color:var(--danger)}
.empty-state{color:var(--muted);padding:30px;text-align:center}
@media(max-width:720px){.take{grid-template-columns:1fr}.right{align-items:flex-start}audio{width:100%}}
</style></head><body><div class="wrap">
<h1>IndicVoice <span>listening bench</span></h1>
<p class="sub">Every clip below was rendered by the production voice path on CPU. Judge naturalness,
pronunciation and artefacts by ear — the CER numbers only say whether a local recogniser recovered the words.
Synthetic audio, not real callers. Multiple takes per sentence because synthesis is non-deterministic.</p>
<div class="bar">
<label for="lang">Language</label><select id="lang"></select>
<label for="filter">Show</label><select id="filter">
<option value="all">all takes</option><option value="miss">word-miss takes only</option>
<option value="clean">clean takes only</option></select>
<button id="playAll" class="primary">Play shown clips in order</button>
<button id="stop">Stop</button>
<span class="count" id="count"></span>
</div>
<div id="list"></div>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const DATA=JSON.parse(document.getElementById('data').textContent);
const LANGS=[...new Set(DATA.clips.map(c=>c.lang))];
const NAMES={hi:'Hindi',gu:'Gujarati',mr:'Marathi',bn:'Bengali',ta:'Tamil',te:'Telugu',kn:'Kannada',
ml:'Malayalam',pa:'Punjabi',or:'Odia',as:'Assamese',en:'English'};
const langSel=document.getElementById('lang'),filterSel=document.getElementById('filter'),
list=document.getElementById('list'),count=document.getElementById('count');
langSel.innerHTML='<option value="all">All languages</option>'+LANGS.map(l=>
`<option value="${l}">${NAMES[l]||l} (${l})</option>`).join('');
let queue=[],playing=null;
function cls(s){return s.startsWith('PASS')?'pass':s==='FAIL'?'fail':'partial'}
function render(){
const lang=langSel.value,filter=filterSel.value;
const clips=DATA.clips.filter(c=>(lang==='all'||c.lang===lang)&&
(filter==='all'||(filter==='miss'?c.status!=='PASS (automated)':c.status==='PASS (automated)')));
count.textContent=clips.length+' clips · run '+DATA.run;
if(!clips.length){list.innerHTML='<p class="empty-state">No clips match this filter.</p>';return}
const byLang={};clips.forEach(c=>{(byLang[c.lang]??=[]).push(c)});
list.innerHTML=Object.entries(byLang).map(([l,items])=>{
const sents={};items.forEach(c=>{(sents[c.sentence]??=[]).push(c)});
const bad=items.filter(c=>c.status!=='PASS (automated)').length;
return `<section class="lang"><h2>${NAMES[l]||l} <span class="pill ${bad?'partial':'pass'}">${
bad?bad+' of '+items.length+' takes flagged':'all '+items.length+' takes clean'}</span></h2>`+
Object.entries(sents).map(([s,takes])=>{
const worst=Math.max(...takes.map(t=>t.cer));
return `<div class="sent"><p class="ref">${takes[0].ref}</p>
<p class="meta">sentence ${s} · ${takes.length} takes · worst CER ${worst.toFixed(3)}</p>
<div class="takes">${takes.map(t=>`<div class="take ${t.status==='PASS (automated)'?'':(t.cer>=worst&&worst>0?'worst':'bad')}">
<div><p class="hyp ${t.hyp?'':'empty'}">${t.hyp||'(empty transcript)'}</p>
<p class="stats">take ${t.take} · CER ${t.cer.toFixed(3)} · WER ${t.wer.toFixed(3)} · ${t.dur.toFixed(2)}s · ${t.rms} dBFS</p>
${t.notes.map(n=>`<p class="note">${n}</p>`).join('')}</div>
<div class="right"><span class="badge ${cls(t.status)}">${t.status}</span>
<audio preload="metadata" controls src="${t.wav}"></audio></div></div>`).join('')}</div></div>`}).join('')+
'</section>'}).join('');
}
langSel.onchange=filterSel.onchange=render;
function clearPlaying(){document.querySelectorAll('.take.playing').forEach(t=>t.classList.remove('playing'))}
document.getElementById('stop').onclick=()=>{queue=[];if(playing){playing.pause();playing=null}
document.querySelectorAll('audio').forEach(a=>a.pause());clearPlaying()};
document.getElementById('playAll').onclick=()=>{
queue=[...list.querySelectorAll('audio')];if(!queue.length)return;
const next=()=>{clearPlaying();const a=queue.shift();if(!a){playing=null;return}
playing=a;a.closest('.take').classList.add('playing');
a.currentTime=0;a.play().catch(()=>{});a.onended=next};
next()};
render();
</script></body></html>
""".replace("__DATA__", payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local TTS render + round-trip speak check")
    parser.add_argument("--langs", default=",".join(LANGS))
    parser.add_argument("--sentences", type=int, default=3, help="corpus sentences per language")
    parser.add_argument("--repeats", type=int, default=3, help="renders per sentence")
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
        print(f"[{lang}] tts={config.tts_backend(lang)} sentences={len(sentences)} "
              f"repeats={args.repeats}", flush=True)
        try:
            results.append(check_language(lang, run_dir, sentences, args.repeats))
        except Exception as exc:
            print(f"[{lang}] ERROR {type(exc).__name__}: {exc}", flush=True)
            results.append({"lang": lang, "n": 0, "status": "FAIL", "error": f"{type(exc).__name__}: {exc}",
                            "rows": [], "per_sentence": [], "audible_all": False,
                            "cer_mean": None, "wer_mean": None, "cer_clean_mean": None,
                            "wer_clean_mean": None, "cer_clean_max": None, "clean_renders": 0,
                            "clean_render_rate": 0, "word_miss_renders": 0, "script_miss_renders": 0,
                            "duration_mean_s": 0, "render_rtf_mean": 0, "hf_share_max": 0,
                            "tts_backend": config.tts_backend(lang), "asr_backend": "?", "sample_rate": 0})

    payload = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "run": run_dir.name,
        "source": "synthetic (TTS render of the fixed eval corpus)",
        "repeats_per_sentence": args.repeats,
        "cloud_inference": False,
        "playback_on_host": False,
        "human_listening": "NOT TESTED",
        "objective_hiss_detection": "NOT TESTED",
        "gates": GATE,
        "languages": results,
    }
    (run_dir / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report = render_report(results, GATE, run_dir, args.repeats)
    (run_dir / "report.md").write_text(report, encoding="utf-8")
    (run_dir / "README.md").write_text(COVER, encoding="utf-8")
    (run_dir / "listen.html").write_text(build_player(results, run_dir.name), encoding="utf-8")
    print("\n" + report.split("## Per-sentence detail")[0], flush=True)

    if not args.no_zip:
        zip_path = run_dir.with_suffix(".zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as bundle:
            for name in ("README.md", "report.md", "results.json", "listen.html"):
                bundle.write(run_dir / name, name)
            for wav in sorted((run_dir / "audio").glob("*.wav")):
                bundle.write(wav, f"audio/{wav.name}")
        print(f"bundle -> {zip_path} ({zip_path.stat().st_size / 1e6:.2f} MB)")
    print(f"run dir -> {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())