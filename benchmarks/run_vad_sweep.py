"""VAD parameter sweep: threshold x min_silence, synthetic speech, offline.

Measures turn_splits (F4-relevant), onset/endpoint delay, captured speech,
and false-positive segments on 5 s of silence. No network, no paid calls.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from src import config
from src.config import SAMPLE_RATE
from src.sts_pipeline import VAD_WINDOW, shared_stt
from src.tts_engine import TTSEngine

PHRASES = {
    "hi": "मेरा ऑर्डर नंबर एक दो तीन है, कल तक पहुँच जाएगा।",
    "gu": "મારો ઓર્ડર નંબર એક બે ત્રણ છે, કાલ સુધીમાં પહોંચી જશે.",
    "mr": "माझा ऑर्डर नंबर एक दो तीन आहे, उद्या पर्यंत पोहोचेल.",
    "bn": "আমার অর্ডার নম্বর এক দুই তিন, কাল পৌঁছে যাবে।",
    "ta": "என் ஆர்டர் எண் ஒன்று இரண்டு மூன்று, நாளைக்குள் வந்துவிடும்.",
    "en": "My order number is one two three and it should arrive tomorrow.",
}


def build_vad(endpoint, threshold):
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


def vad_run(vad, audio):
    onset_frames = None
    endpoint_frames = None
    segments = []
    total = len(audio) // VAD_WINDOW
    for i in range(total):
        frame = audio[i * VAD_WINDOW:(i + 1) * VAD_WINDOW]
        vad.accept_waveform(frame)
        if onset_frames is None and vad.is_speech_detected():
            onset_frames = i
        while not vad.empty():
            seg = vad.front
            segments.append(len(seg.samples))
            vad.pop()
            if endpoint_frames is None:
                endpoint_frames = i
    while not vad.empty():
        segments.append(len(vad.front.samples))
        vad.pop()
    return onset_frames, endpoint_frames, segments, total


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", nargs="*", default=["hi", "gu", "mr", "bn", "ta"])
    ap.add_argument("--thresholds", nargs="*", type=float, default=[0.3, 0.4, 0.5, 0.6])
    ap.add_argument("--endpoints", nargs="*", type=float, default=[0.15, 0.20, 0.26, 0.35, 0.45])
    ap.add_argument("--out-dir", default="benchmarks/results/cpu_sts_optimization/runs")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {"generated_at": datetime.now().isoformat(timespec="seconds"), "langs": {}}

    for lang in args.langs:
        phrase = PHRASES.get(lang)
        if not phrase:
            results["langs"][lang] = {"status": "skipped", "reason": "no phrase"}
            continue
        engine = TTSEngine(lang)
        audio = engine.render_sentence(phrase, cancel_event=None)
        speech16k = audio
        if engine.sample_rate != SAMPLE_RATE:
            from src.call_server import resample
            speech16k = resample(audio, engine.sample_rate, SAMPLE_RATE)
        feed = np.concatenate([
            np.zeros(int(0.3 * SAMPLE_RATE), np.float32),
            speech16k,
            np.zeros(int(1.2 * SAMPLE_RATE), np.float32),
        ])
        speech_end_frame = int((0.3 * SAMPLE_RATE + speech16k.size) / VAD_WINDOW)
        speech_s = speech16k.size / SAMPLE_RATE

        combos = []
        for thr in args.thresholds:
            for ep in args.endpoints:
                vad = build_vad(ep, thr)
                onset, endp, segs, total = vad_run(vad, feed)
                onset_ms = (onset or 0) * VAD_WINDOW / SAMPLE_RATE * 1000.0
                endpoint_ms = ((endp or total) - speech_end_frame) * VAD_WINDOW / SAMPLE_RATE * 1000.0
                captured_s = sum(segs) / SAMPLE_RATE
                splits = max(0, len(segs) - 1)
                # false positives on 5s silence
                vad2 = build_vad(ep, thr)
                _, _, segs2, _ = vad_run(vad2, np.zeros(int(5 * SAMPLE_RATE), np.float32))
                fp = len(segs2)
                combos.append({
                    "threshold": thr,
                    "min_silence_s": ep,
                    "turn_splits": splits,
                    "onset_ms": round(onset_ms, 1),
                    "endpoint_delay_ms": round(endpoint_ms, 1),
                    "captured_s": round(captured_s, 2),
                    "speech_s": round(speech_s, 2),
                    "false_pos_on_5s_silence": fp,
                })
        results["langs"][lang] = {"status": "measured", "combos": combos}
        print(f"[{lang}] {len(combos)} combos", flush=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = out_dir / f"vad_sweep_{stamp}.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())