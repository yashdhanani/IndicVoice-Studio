"""Evaluation harness: recognition accuracy and end-to-end latency per language.

Two independent measurements:

* **accuracy** — transcribes a fixed corpus per language and reports CER/WER
  against the reference text. Without ``--audio-dir`` the corpus is synthesised
  with the local voice, which flatters the recogniser (same domain, clean audio);
  point ``--audio-dir`` at real recordings to get honest numbers.
* **latency** — runs whole turns through a live server and reports P50/P95 for
  recognition, LLM first token, TTS start and perceived (last word -> first audio).

Usage:
    python -m src.evaluate --langs hi,ta,kn
    python -m src.evaluate --langs hi --audio-dir eval/audio --runs 3
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import statistics
import sys
import time
import unicodedata
from pathlib import Path

import numpy as np

from . import config
from .config import resolve_lang

#: Fixed evaluation corpus, written the way a caller actually talks on a call.
CORPUS: dict[str, list[str]] = {
    "hi": [
        "मेरा ऑर्डर नंबर एक दो तीन है।",
        "कल शाम तक डिलीवरी हो जाएगी।",
        "मेरा पता दिल्ली में है।",
    ],
    "gu": [
        "મારો ઓર્ડર નંબર એક બે ત્રણ છે.",
        "કાલે સાંજ સુધીમાં ડિલિવરી થઈ જશે.",
        "મારું સરનામું અમદાવાદમાં છે.",
    ],
    "mr": [
        "माझा ऑर्डर नंबर एक दोन तीन आहे.",
        "उद्या संध्याकाळपर्यंत डिलिव्हरी होईल.",
        "माझा पत्ता पुण्यात आहे.",
    ],
    "bn": [
        "আমার অর্ডার নম্বর এক দুই তিন।",
        "কাল সন্ধ্যার মধ্যে ডেলিভারি হবে।",
        "আমার ঠিকানা কলকাতায়।",
    ],
    "ta": [
        "என் ஆர்டர் எண் ஒன்று இரண்டு மூன்று.",
        "நாளை மாலைக்குள் டெலிவரி ஆகும்.",
        "என் முகவரி சென்னையில் உள்ளது.",
    ],
    "te": [
        "నా ఆర్డర్ నంబర్ ఒకటి రెండు మూడు.",
        "రేపు సాయంత్రం వరకు డెలివరీ అవుతుంది.",
        "నా చిరునామా హైదరాబాద్‌లో ఉంది.",
    ],
    "kn": [
        "ನನ್ನ ಆರ್ಡರ್ ನಂಬರ್ ಒಂದು ಎರಡು ಮೂರು.",
        "ನಾಳೆ ಸಂಜೆಯೊಳಗೆ ಡೆಲಿವರಿ ಆಗುತ್ತದೆ.",
        "ನನ್ನ ವಿಳಾಸ ಬೆಂಗಳೂರಿನಲ್ಲಿದೆ.",
    ],
    "ml": [
        "എന്റെ ഓർഡർ നമ്പർ ഒന്ന് രണ്ട് മൂന്ന്.",
        "നാളെ വൈകുന്നേരത്തിനുള്ളിൽ ഡെലിവറി ആകും.",
        "എന്റെ വിലാസം കൊച്ചിയിലാണ്.",
    ],
    "pa": [
        "ਮੇਰਾ ਆਰਡਰ ਨੰਬਰ ਇੱਕ ਦੋ ਤਿੰਨ ਹੈ।",
        "ਕੱਲ੍ਹ ਸ਼ਾਮ ਤੱਕ ਡਿਲੀਵਰੀ ਹੋ ਜਾਵੇਗੀ।",
        "ਮੇਰਾ ਪਤਾ ਲੁਧਿਆਣਾ ਵਿੱਚ ਹੈ।",
    ],
    "or": [
        "ମୋ ଅର୍ଡର ନମ୍ବର ଏକ ଦୁଇ ତିନି।",
        "କାଲି ସନ୍ଧ୍ୟା ସୁଦ୍ଧା ଡେଲିଭରି ହେବ।",
        "ମୋ ଠିକଣା ଭୁବନେଶ୍ୱରରେ ଅଛି।",
    ],
    "as": [
        "মোৰ অৰ্ডাৰ নম্বৰ এক দুই তিনি।",
        "কাইলৈ সন্ধিয়াৰ ভিতৰত ডেলিভাৰী হ'ব।",
        "মোৰ ঠিকনা গুৱাহাটীত আছে।",
    ],
    "en": [
        "My order number is one two three.",
        "Delivery will happen before tomorrow evening.",
        "My address is in Delhi.",
    ],
}

#: Punctuation is not part of the words being compared.
_KEEP = re.compile(r"[^\w\u0900-\u0DFF\u0980-\u09FF\u0A00-\u0AFF\u0A80-\u0AFF"
                   r"\u0B00-\u0B7F\u0B80-\u0BFF\u0C00-\u0C7F\u0C80-\u0CFF"
                   r"\u0D00-\u0D7F\u0D80-\u0DFF]+", re.UNICODE)


def normalise(text: str) -> str:
    """Lower-case, NFC, strip punctuation and collapse whitespace."""
    text = unicodedata.normalize("NFC", text or "").lower()
    text = _KEEP.sub(" ", text)
    return " ".join(text.split())


def edit_distance(a: list[str], b: list[str]) -> int:
    """Levenshtein distance over token or character lists."""
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, item in enumerate(a, 1):
        current = [i]
        for j, other in enumerate(b, 1):
            current.append(
                min(
                    previous[j] + 1,          # deletion
                    current[j - 1] + 1,       # insertion
                    previous[j - 1] + (item != other),
                )
            )
        previous = current
    return previous[-1]


def cer(ref: str, hyp: str) -> float:
    r, h = normalise(ref).replace(" ", ""), normalise(hyp).replace(" ", "")
    return edit_distance(list(r), list(h)) / max(len(r), 1)


def wer(ref: str, hyp: str) -> float:
    r, h = normalise(ref).split(), normalise(hyp).split()
    return edit_distance(r, h) / max(len(r), 1)


# --------------------------------------------------------------------------- #
# accuracy
# --------------------------------------------------------------------------- #

def read_wav(path: Path) -> np.ndarray:
    """Read a wav file as 16 kHz mono float32."""
    from scipy.io import wavfile

    rate, data = wavfile.read(str(path))
    samples = data.astype(np.float32)
    if samples.ndim > 1:
        samples = samples[:, 0]
    if np.issubdtype(data.dtype, np.integer):
        samples /= float(np.iinfo(data.dtype).max)
    if rate != config.SAMPLE_RATE:
        n = max(1, int(len(samples) * config.SAMPLE_RATE / rate))
        samples = np.interp(
            np.linspace(0, len(samples) - 1, n), np.arange(len(samples)), samples
        )
    return samples


def load_corpus(lang: str, audio_dir: Path | None) -> list[tuple[str, np.ndarray | None]]:
    """Return ``(reference, audio_or_None)`` pairs for one language."""
    if audio_dir is not None:
        folder = Path(audio_dir) / lang
        if not folder.is_dir():
            return []
        pairs = []
        for txt in sorted(folder.glob("*.txt")):
            wav = txt.with_suffix(".wav")
            if wav.exists():
                pairs.append((txt.read_text(encoding="utf-8").strip(), read_wav(wav)))
        return pairs
    return [(text, None) for text in CORPUS.get(lang, [])]


def accuracy(lang: str, audio_dir: Path | None, backend: str = "auto") -> dict:
    from .sts_pipeline import shared_stt
    from .tts_engine import TTSEngine

    pairs = load_corpus(lang, audio_dir)
    if not pairs:
        return {"lang": lang, "n": 0, "error": "no corpus"}

    engine = TTSEngine(lang) if audio_dir is None else None
    stt = shared_stt(backend, lang)
    rows = []
    for reference, audio in pairs:
        if audio is None and engine is not None:
            audio = engine.synthesize(engine.prepare(reference))
        hypothesis = stt.transcribe(audio, config.SAMPLE_RATE)
        rows.append({"ref": reference, "hyp": hypothesis,
                     "cer": round(cer(reference, hypothesis), 3),
                     "wer": round(wer(reference, hypothesis), 3)})

    return {
        "lang": lang,
        "backend": getattr(stt, "backend", backend),
        "n": len(rows),
        "source": "real" if audio_dir else "synthetic",
        "cer": round(statistics.mean(r["cer"] for r in rows), 3),
        "wer": round(statistics.mean(r["wer"] for r in rows), 3),
        "rows": rows,
    }


# --------------------------------------------------------------------------- #
# manifest: a golden dataset of real recordings, run through the real pipeline
# --------------------------------------------------------------------------- #

def evaluate_manifest(
    manifest: Path,
    backend: str = "auto",
    mode: str = "block",
    asr_only: bool = False,
) -> list[dict]:
    """Run every line of ``manifest.json`` through recognition, LLM and TTS.

    Manifest format, one entry per recording::

        [{"audio_file": "hi_01.wav", "language": "hi",
          "reference_text": "नमस्ते, आप कैसे हैं?"}]

    Each stage is timed in-process, so this measures the pipeline rather than the
    network: ``asr`` is decode only, ``ttft`` the wait for the LLM's first token,
    ``ttfa`` the wait for the first clause of reply audio.

    ``mode="streaming"`` feeds the recording at real-time pace into
    :class:`StreamingSTT` (partial decodes while the audio plays, speculative
    final decode during trailing silence) and measures from the simulated
    endpoint — the latency a caller actually perceives. ``asr_only`` skips the
    LLM and TTS stages.
    """
    from .sts_pipeline import DEFAULT_SYSTEM, LLMClient, shared_stt
    from .streaming_stt import StreamingSTT
    from .tts_engine import TTSEngine

    manifest = Path(manifest)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("utterances", [])
    base = manifest.parent

    llm = None if asr_only else LLMClient()
    if llm is not None:
        llm.warm()
    voices: dict[str, TTSEngine] = {}
    streamer = StreamingSTT() if mode == "streaming" else None
    rows: list[dict] = []

    for case in data:
        lang = resolve_lang(case["language"])
        audio = read_wav(base / case["audio_file"])
        reference = case.get("reference_text", "")

        stt = shared_stt(backend, lang)
        asr_info = None
        if streamer is not None:
            frame = int(config.SAMPLE_RATE * 0.02)
            # the server waits ENDPOINT_SILENCE after speech before finalising;
            # feed the same trailing silence and measure from that endpoint
            endpoint = config.endpoint_for(lang)
            streamer.start(stt, endpoint_silence=endpoint)
            padded = np.concatenate([audio, np.zeros(int(endpoint * config.SAMPLE_RATE), np.float32)])
            rms = np.sqrt((audio[: len(audio) // frame * frame].reshape(-1, frame) ** 2).mean(axis=1))
            loud = np.flatnonzero(rms > max(float(rms.max()) * 0.06, 1e-4))
            speech_end_s = ((loud[-1] + 1) * frame / config.SAMPLE_RATE) if loud.size else len(audio) / config.SAMPLE_RATE
            started = time.perf_counter()
            eou = started + speech_end_s + endpoint
            # the server finalises at the endpoint and feeds no audio past it;
            # recordings often carry longer natural trailing silence, which
            # would otherwise look like resumed speech to the staleness guard
            feed_end = min(len(padded), int((speech_end_s + endpoint) * config.SAMPLE_RATE))
            for i in range(0, feed_end, frame):
                streamer.accept(padded[i : i + frame])
                # real-time pace: partial decodes must keep up with the audio
                target = started + (i + frame) / config.SAMPLE_RATE
                delay = target - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
            delay = eou - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            start = time.perf_counter()
            hypothesis, asr_info = streamer.finalize()
            asr_ms = (time.perf_counter() - start) * 1000
        else:
            start = time.perf_counter()
            hypothesis = stt.transcribe(audio, config.SAMPLE_RATE)
            asr_ms = (time.perf_counter() - start) * 1000

        reply, ttft, ttfa_ms, spoken_seconds = "", 0.0, 0.0, 0.0
        if not asr_only:
            started = time.perf_counter()
            for delta in llm.stream_chat(
                [{"role": "system", "content": DEFAULT_SYSTEM},
                 {"role": "user", "content": hypothesis}]
            ):
                if not ttft:
                    ttft = (time.perf_counter() - started) * 1000
                reply += delta

            voice = voices.get(lang)
            if voice is None:
                voice = voices[lang] = TTSEngine(lang)
            head, _ = TTSEngine.split_head(reply or hypothesis)
            started = time.perf_counter()
            spoken = voice.synthesize(head or (reply or "")[:40])
            ttfa_ms = (time.perf_counter() - started) * 1000
            spoken_seconds = len(spoken) / voice.sample_rate

        rows.append({
            "audio_file": case["audio_file"],
            "language": lang,
            "mode": mode,
            "backend": getattr(stt, "backend", backend),
            "reference": reference,
            "hypothesis": hypothesis,
            "reply": reply.strip(),
            "asr_ms": round(asr_ms, 1),
            "asr_strategy": asr_info["strategy"] if asr_info else "block",
            "partials": asr_info["partials"] if asr_info else 0,
            "llm_ttft_ms": round(ttft, 1),
            "tts_ttfa_ms": round(ttfa_ms, 1),
            "e2e_ms": round(asr_ms + ttft + ttfa_ms, 1),
            "audio_seconds": round(spoken_seconds, 2),
            "cer": round(cer(reference, hypothesis), 3) if reference else None,
            "wer": round(wer(reference, hypothesis), 3) if reference else None,
        })
        extra = f" [{asr_info['strategy']}, {asr_info['partials']} partials]" if asr_info else ""
        print(f"{case['audio_file']} [{lang}/{mode}] cer={rows[-1]['cer']} "
              f"asr={asr_ms:.0f} ttft={ttft:.0f} ttfa={ttfa_ms:.0f} ms{extra}")
    if streamer is not None:
        streamer.close()
    return rows


def summarise(rows: list[dict]) -> dict:
    """Per-language (and per-mode) means (accuracy) and P50/P95 (latency)."""
    def stats(values: list[float]) -> dict:
        if not values:
            return {"n": 0}
        ordered = sorted(values)
        index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * 0.95) - 1))
        return {"n": len(values), "p50": round(statistics.median(ordered), 1),
                "p95": round(ordered[index], 1)}

    groups: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        groups.setdefault((row["language"], row.get("mode", "block")), []).append(row)
    multi_mode = len({mode for _, mode in groups}) > 1

    summary = {}
    for (lang, mode), items in groups.items():
        scored = [i for i in items if i["cer"] is not None]
        key = f"{lang}/{mode}" if multi_mode else lang
        summary[key] = {
            "n": len(items),
            "mode": mode,
            "cer": round(statistics.mean(i["cer"] for i in scored), 3) if scored else None,
            "wer": round(statistics.mean(i["wer"] for i in scored), 3) if scored else None,
            "asr_ms": stats([i["asr_ms"] for i in items]),
            "llm_ttft_ms": stats([i["llm_ttft_ms"] for i in items]),
            "tts_ttfa_ms": stats([i["tts_ttfa_ms"] for i in items]),
            "e2e_ms": stats([i["e2e_ms"] for i in items]),
        }
        if mode == "streaming":
            strategies: dict[str, int] = {}
            for item in items:
                name = item.get("asr_strategy", "?")
                strategies[name] = strategies.get(name, 0) + 1
            summary[key]["strategies"] = strategies
    return summary


def render_markdown(summary: dict) -> str:
    """A table you can paste into a report."""
    lines = [
        "# IndicVoice evaluation",
        "",
        "| lang | mode | n | CER | WER | ASR p50 | ASR p95 | LLM TTFT p50 | TTS TTFA p50 | E2E p50 | E2E p95 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for key in sorted(summary):
        item = summary[key]
        lang, _, mode = key.partition("/")
        mode = mode or item.get("mode", "block")

        def cell(key: str, which: str = "p50") -> str:
            block = item.get(key) or {}
            return f"{block[which]:.0f}" if block.get("n") else "-"

        accuracy = ("-" if item["cer"] is None else f"{item['cer']:.3f}",
                    "-" if item["wer"] is None else f"{item['wer']:.3f}")
        lines.append(
            f"| {lang} | {mode} | {item['n']} | {accuracy[0]} | {accuracy[1]} | "
            f"{cell('asr_ms')} | {cell('asr_ms', 'p95')} | {cell('llm_ttft_ms')} | {cell('tts_ttfa_ms')} | "
            f"{cell('e2e_ms')} | {cell('e2e_ms', 'p95')} |"
        )
    return "\n".join(lines) + "\n"


def make_manifest(folder: Path) -> Path:
    """Write a starter manifest from the built-in corpus (synthesised audio).

    Replace the wav files with real recordings, keep the format, and rerun to get
    numbers that mean something in production.
    """
    from scipy.io import wavfile

    from .tts_engine import TTSEngine

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    cases = []
    for lang, sentences in CORPUS.items():
        voice = TTSEngine(lang)
        for index, text in enumerate(sentences, 1):
            audio = voice.synthesize(voice.prepare(text))
            name = f"{lang}_{index:02d}.wav"
            pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
            wavfile.write(str(folder / name), voice.sample_rate, pcm)
            cases.append({"audio_file": name, "language": lang, "reference_text": text})
    manifest = folder / "manifest.json"
    manifest.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(cases)} recordings + {manifest}")
    return manifest


# --------------------------------------------------------------------------- #
# latency
# --------------------------------------------------------------------------- #

async def latency(lang: str, runs: int, server: str, backchannel: bool) -> dict:
    import aiohttp

    from .tts_engine import TTSEngine

    engine = TTSEngine(lang)
    samples: dict[str, list[float]] = {"perceived": [], "asr": [], "llm": [], "tts": []}

    for _ in range(runs):
        text = CORPUS[lang][0]
        audio = engine.synthesize(engine.prepare(text))
        rate = engine.sample_rate
        if rate != config.SAMPLE_RATE:
            n = int(len(audio) * config.SAMPLE_RATE / rate)
            audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio)
        pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
        stream = np.concatenate([pcm, np.zeros(int(config.SAMPLE_RATE * 1.2), np.int16)])
        frame = int(config.SAMPLE_RATE * 0.02)
        chunks = [stream[i : i + frame] for i in range(0, len(stream), frame)]
        speech_end = max(0, len(pcm) // frame)

        url = server.replace("http", "ws", 1).rstrip("/")
        url += f"/ws/voice?lang={lang}" + ("" if backchannel else "&backchannel=0")
        state = {"last_speech": None, "first_audio": None, "latency": None}
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(url, max_msg_size=0) as ws:

                async def send():
                    for i, chunk in enumerate(chunks):
                        if i == speech_end:
                            state["last_speech"] = time.perf_counter()
                        await ws.send_bytes(chunk.tobytes())
                        await asyncio.sleep(0.02)

                sender = asyncio.create_task(send())
                deadline = time.perf_counter() + 60
                quiet = time.perf_counter()
                while time.perf_counter() < deadline:
                    try:
                        msg = await asyncio.wait_for(ws.receive(), timeout=2.0)
                    except asyncio.TimeoutError:
                        if state["first_audio"] and time.perf_counter() - quiet > 2.0:
                            break
                        continue
                    if msg.type == aiohttp.WSMsgType.BINARY:
                        if state["first_audio"] is None:
                            state["first_audio"] = time.perf_counter()
                        quiet = time.perf_counter()
                    elif msg.type == aiohttp.WSMsgType.TEXT:
                        event = json.loads(msg.data)
                        if event.get("type") == "latency":
                            state["latency"] = event
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break
                sender.cancel()

        if state["first_audio"] and state["last_speech"]:
            samples["perceived"].append((state["first_audio"] - state["last_speech"]) * 1000)
        event = state["latency"] or {}
        if event.get("asr_ms"):
            samples["asr"].append(event["asr_ms"])
        if event.get("llm_ms"):
            samples["llm"].append(event["llm_ms"] - event.get("asr_ms", 0))
        if event.get("tts_ms"):
            samples["tts"].append(event["tts_ms"])

    def stats(values: list[float]) -> dict:
        if not values:
            return {"n": 0}
        ordered = sorted(values)
        index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * 0.95) - 1))
        return {
            "n": len(values),
            "p50": round(statistics.median(ordered), 1),
            "p95": round(ordered[index], 1),
            "min": round(ordered[0], 1),
            "max": round(ordered[-1], 1),
            "samples": [round(v, 1) for v in values],
        }

    return {"lang": lang, "perceived_ms": stats(samples["perceived"]),
            "asr_ms": stats(samples["asr"]), "llm_ms": stats(samples["llm"]),
            "tts_ms": stats(samples["tts"])}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate recognition accuracy and latency")
    parser.add_argument("--langs", default="hi,en", help="comma separated language codes")
    parser.add_argument("--audio-dir", default=None,
                        help="folder of <lang>/*.wav + *.txt real recordings (honest ASR score)")
    parser.add_argument("--runs", type=int, default=1, help="turns per language for latency")
    parser.add_argument("--server", default="http://127.0.0.1:8000", help="live server for latency")
    parser.add_argument("--no-latency", action="store_true", help="accuracy only")
    parser.add_argument("--no-accuracy", action="store_true", help="latency only")
    parser.add_argument("--manifest", default=None,
                        help="manifest.json of real recordings: full pipeline per turn, in-process")
    parser.add_argument("--make-manifest", default=None, metavar="DIR",
                        help="write a starter manifest + synthesised wavs into DIR")
    parser.add_argument("--backchannel", action="store_true", help="include the filler sound")
    parser.add_argument("--backend", default="auto",
                        choices=("auto", "indic", "groq", "whisper", "ctc"),
                        help="force one recogniser, to compare accuracy per language")
    parser.add_argument("--mode", default="block", choices=("block", "streaming", "ab"),
                        help="manifest ASR mode: block decode, pseudo-streaming, or both side by side")
    parser.add_argument("--asr-only", action="store_true",
                        help="manifest: skip LLM and TTS, measure recognition only")
    parser.add_argument("--out", default="eval/report.json")
    args = parser.parse_args(argv)

    if args.make_manifest:
        make_manifest(Path(args.make_manifest))
        return 0

    if args.manifest:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        manifest_path = Path(args.manifest)
        rows: list[dict] = []
        if args.mode == "ab":
            # counterbalance mode order across the corpus: first half runs
            # block->streaming, second half streaming->block, so thermal /
            # cache order effects do not systematically favor one mode
            entries = json.loads(manifest_path.read_text(encoding="utf-8"))
            mid = len(entries) // 2
            for group, subset, modes in (
                ("A", entries[:mid], ["block", "streaming"]),
                ("B", entries[mid:], ["streaming", "block"]),
            ):
                sub = out.with_name(out.stem + f"_order{group}.json")
                sub.write_text(json.dumps(subset, ensure_ascii=False), encoding="utf-8")
                for mode in modes:
                    group_rows = evaluate_manifest(sub, args.backend,
                                                   mode=mode, asr_only=args.asr_only)
                    for row in group_rows:
                        row["order_group"] = group
                    rows += group_rows
        else:
            rows = evaluate_manifest(manifest_path, args.backend,
                                     mode=args.mode, asr_only=args.asr_only)
        summary = summarise(rows)
        report = render_markdown(summary)
        out.write_text(json.dumps({"turns": rows, "summary": summary},
                                  ensure_ascii=False, indent=2), encoding="utf-8")
        markdown = out.with_suffix(".md")
        markdown.write_text(report, encoding="utf-8")
        print("\n" + report)
        print(f"report -> {markdown} and {out}")
        return 0

    langs = [resolve_lang(l.strip()) for l in args.langs.split(",") if l.strip()]
    audio_dir = Path(args.audio_dir) if args.audio_dir else None
    report: dict = {"generated": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "source": "real" if audio_dir else "synthetic", "languages": {}}

    if not args.no_accuracy:
        print(f"{'lang':>4} | {'CER':>6} | {'WER':>6} | corpus")
        for lang in langs:
            result = accuracy(lang, audio_dir, args.backend)
            report["languages"].setdefault(lang, {})["accuracy"] = result
            if result.get("n"):
                print(f"{lang:>4} | {result['cer']:>6.3f} | {result['wer']:>6.3f} | "
                      f"{result['n']} {result['source']} [{result['backend']}]")
            else:
                print(f"{lang:>4} | no corpus ({result.get('error')})")

    if not args.no_latency:
        print(f"\n{'lang':>4} | {'perceived p50/p95':>18} | {'asr':>10} | {'llm':>10} | {'tts':>8}")
        for lang in langs:
            result = asyncio.run(latency(lang, args.runs, args.server, args.backchannel))
            report["languages"].setdefault(lang, {})["latency"] = result
            per = result["perceived_ms"]
            if per.get("n"):
                def mid(key: str) -> str:
                    block = result[key]
                    return f"{block.get('p50', 0):.0f}/{block.get('p95', 0):.0f}" if block.get("n") else "-"
                print(f"{lang:>4} | {per['p50']:>8.0f}/{per['p95']:<7.0f} | {mid('asr_ms'):>10} | "
                      f"{mid('llm_ms'):>10} | {mid('tts_ms'):>8}")
            else:
                print(f"{lang:>4} | no audio back from {args.server}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nreport -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
