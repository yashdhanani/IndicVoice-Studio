"""Stage-level benchmark: VAD onset/endpoint, TTS RTF, ASR decode, CER, RSS.

Fully offline: synthesises speech locally, decodes it locally, and runs it
through the same Silero VAD configuration the server uses. No network, no paid
API, no microphone. Synthetic round-trip CER measures *engineering* health of
the cascade (TTS is intelligible to the ASR), not real human accuracy -- real
speech needs the human dataset, which is NOT TESTED.

    .venv313\\Scripts\\python.exe -m benchmarks.run_stage_bench --langs hi en gu ta
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from src import config
from src.config import SAMPLE_RATE
from src.sts_pipeline import shared_stt
from src.tts_engine import TTSEngine

VAD_WINDOW = 512

PHRASES = {
    "hi": "मेरा ऑर्डर नंबर एक दो तीन है, कल तक पहुँच जाएगा।",
    "en": "My order number is one two three and it should arrive tomorrow.",
    "gu": "મારો ઓર્ડર નંબર એક બે ત્રણ છે, કાલ સુધીમાં પહોંચી જશે.",
    "ta": "என் ஆர்டர் எண் ஒன்று இரண்டு மூன்று, நாளைக்குள் வந்துவிடும்.",
    "mr": "माझा ऑर्डर नंबर एक दो तीन आहे, उद्या पर्यंत पोहोचेल.",
    "bn": "আমার অর্ডার নম্বর এক দুই তিন, কাল পৌঁছে যাবে।",
}


def cer(reference: str, hypothesis: str) -> float:
    """Character error rate after whitespace/punctuation normalisation."""
    ref = "".join(ch for ch in reference if ch.isalnum())
    hyp = "".join(ch for ch in hypothesis if ch.isalnum())
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, rc in enumerate(ref, 1):
        cur = [i]
        for j, hc in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rc != hc)))
        prev = cur
    return min(1.0, prev[-1] / len(ref))


def build_vad(endpoint: float, threshold: float = 0.5):
    import sherpa_onnx

    cfg = sherpa_onnx.VadModelConfig(
        silero_vad=sherpa_onnx.SileroVadModelConfig(
            model=str(config.VAD_PATH),
            threshold=threshold,
            min_silence_duration=endpoint,
            min_speech_duration=0.25,
            window_size=VAD_WINDOW,
        ),
        sample_rate=SAMPLE_RATE,
        num_threads=1,
        provider="cpu",
    )
    return sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=30)


def vad_run(vad, audio: np.ndarray) -> dict:
    """Feed audio frame by frame, recording onset and endpoint timing."""
    onset_frames = None
    endpoint_frames = None
    segments: list[int] = []
    total = len(audio) // VAD_WINDOW
    for i in range(total):
        frame = audio[i * VAD_WINDOW:(i + 1) * VAD_WINDOW]
        vad.accept_waveform(frame)
        if onset_frames is None and vad.is_speech_detected():
            onset_frames = i
        while not vad.empty():
            seg = vad.front
            size = len(seg.samples)
            vad.pop()
            segments.append(size)
            if endpoint_frames is None:
                endpoint_frames = i
    while not vad.empty():
        segments.append(len(vad.front.samples))
        vad.pop()
    return {
        "onset_frame": onset_frames,
        "endpoint_frame": endpoint_frames,
        "segment_samples": segments,
        "captured_samples": sum(segments),
        "frames": total,
    }


def main(argv: list[str] | None = None) -> int:
    try:                       # Windows consoles default to cp1252
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser()
    parser.add_argument("--langs", nargs="*", default=["hi", "en", "gu", "ta"])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--out-dir", default="benchmarks/results/final_sts")
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "host": {"machine": "i7-8565U 4c/8t", "sample_rate": SAMPLE_RATE,
                 "repeats": args.repeats},
        "note": ("Synthetic round-trip: local TTS -> local ASR. Measures cascade "
                 "engineering cost and intelligibility, NOT human speech accuracy "
                 "or naturalness (those are NOT TESTED)."),
        "languages": {},
    }

    for lang in args.langs:
        phrase = PHRASES.get(lang)
        if not phrase:
            results["languages"][lang] = {"status": "skipped", "reason": "no test phrase"}
            continue
        try:
            engine = TTSEngine(lang)
            stt = shared_stt("auto", lang)
        except Exception as exc:                                   # noqa: BLE001
            results["languages"][lang] = {"status": "unavailable", "reason": str(exc)[:200]}
            continue

        tts_times, audio_s, asr_times, cers = [], [], [], []
        audio = None
        for _ in range(args.repeats):
            t0 = time.perf_counter()
            audio = engine.render_sentence(phrase, cancel_event=None)
            tts_times.append((time.perf_counter() - t0) * 1000.0)
            audio_s.append(audio.size / engine.sample_rate)
            t1 = time.perf_counter()
            text = stt.transcribe(audio, engine.sample_rate)
            asr_times.append((time.perf_counter() - t1) * 1000.0)
            cers.append(cer(phrase, text))

        # ---- VAD: onset latency, endpoint delay, truncation ----------------
        endpoint = config.endpoint_for(lang)
        speech16k = audio
        if engine.sample_rate != SAMPLE_RATE:
            from src.call_server import resample
            speech16k = resample(audio, engine.sample_rate, SAMPLE_RATE)
        trailing = int(1.2 * SAMPLE_RATE)
        feed = np.concatenate([np.zeros(int(0.3 * SAMPLE_RATE), np.float32),
                               speech16k, np.zeros(trailing, np.float32)])
        vad = build_vad(endpoint)
        v = vad_run(vad, feed)
        onset_ms = (v["onset_frame"] or 0) * VAD_WINDOW / SAMPLE_RATE * 1000.0
        speech_end_frame = int((0.3 * SAMPLE_RATE + speech16k.size) / VAD_WINDOW)
        endpoint_ms = ((v["endpoint_frame"] or v["frames"]) - speech_end_frame) * \
            VAD_WINDOW / SAMPLE_RATE * 1000.0
        captured_s = v["captured_samples"] / SAMPLE_RATE
        # every popped segment is a separate turn for the server: a pause that
        # outlives the endpoint silence makes the agent answer half a question
        turn_splits = max(0, len(v["segment_samples"]) - 1)

        # ---- VAD false positives on pure digital silence -------------------
        silence_vad = build_vad(endpoint)
        s = vad_run(silence_vad, np.zeros(int(5 * SAMPLE_RATE), np.float32))
        false_positives = len(s["segment_samples"])

        results["languages"][lang] = {
            "status": "measured",
            "tts_backend": engine.backend,
            "tts_ms_p50": round(statistics.median(tts_times), 1),
            "tts_rtf": round(statistics.median(tts_times) /
                            (statistics.median(audio_s) * 1000.0), 2),
            "audio_seconds": round(statistics.median(audio_s), 2),
            "asr_ms_p50": round(statistics.median(asr_times), 1),
            "asr_format": getattr(stt, "backend", "?"),
            "roundtrip_cer_p50": round(statistics.median(cers), 3),
            "asr_text_sample": text[:120],
            "endpoint_setting_s": endpoint,
            "vad_onset_ms": round(onset_ms, 1),
            "vad_endpoint_delay_ms": round(endpoint_ms, 1),
            "vad_captured_s": round(captured_s, 2),
            "vad_speech_s": round(speech16k.size / SAMPLE_RATE, 2),
            "vad_unsegmented_s_note": "speech minus captured is mostly silence the VAD trims at segment edges, not lost words",
            "vad_turn_splits": turn_splits,
            "vad_false_positive_segments_on_5s_silence": false_positives,
        }
        print(f"[{lang}] {results['languages'][lang]}", flush=True)

    try:
        from src.call_server import _process_rss_mb
        results["rss_mb_end"] = _process_rss_mb()
    except Exception:                                              # noqa: BLE001
        results["rss_mb_end"] = None

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = out_dir / f"stage_bench_{stamp}.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    latest = out_dir / "stage_bench_latest.json"
    latest.write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
