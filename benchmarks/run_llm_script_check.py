"""LLM reply script-consistency spot check (Production Hardening V1, Phase E).

Sends one fixed native-script question per language through the SAME system
prompt the voice agent uses (sts_pipeline.system_prompt) and measures what
fraction of the reply's letters are in the expected Unicode script. This is
a script-consistency check, NOT a quality/MOS evaluation -- no human
judgement is implied or fabricated.

Uses the configured cloud LLM (Groq free tier by default): 12 short calls.
Run only with authorization for live cloud inference; never in CI.

Usage:
    python benchmarks/run_llm_script_check.py
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.sts_pipeline import LLMClient, system_prompt  # noqa: E402

SCRIPTS = {
    "hi": ("Devanagari", 0x0900, 0x097F),
    "mr": ("Devanagari", 0x0900, 0x097F),
    "bn": ("Bengali", 0x0980, 0x09FF),
    "as": ("Bengali", 0x0980, 0x09FF),
    "pa": ("Gurmukhi", 0x0A00, 0x0A7F),
    "gu": ("Gujarati", 0x0A80, 0x0AFF),
    "or": ("Odia", 0x0B00, 0x0B7F),
    "ta": ("Tamil", 0x0B80, 0x0BFF),
    "te": ("Telugu", 0x0C00, 0x0C7F),
    "kn": ("Kannada", 0x0C80, 0x0CFF),
    "ml": ("Malayalam", 0x0D00, 0x0D7F),
    "en": ("Latin", None, None),
}
QUESTIONS = {
    "hi": "भारत की राजधानी क्या है? एक वाक्य में बताइए।",
    "mr": "भारताची राजधानी काय आहे? एका वाक्यात सांगा.",
    "bn": "ভারতের রাজধানী কী? এক বাক্যে বলুন।",
    "as": "ভাৰতৰ ৰাজধানী কি? এটা বাক্যত কওক।",
    "pa": "ਭਾਰਤ ਦੀ ਰਾਜਧਾਨੀ ਕੀ ਹੈ? ਇੱਕ ਵਾਕ ਵਿੱਚ ਦੱਸੋ।",
    "gu": "ભારતની રાજધાની શું છે? એક વાક્યમાં કહો.",
    "or": "ଭାରତର ରାଜଧାନୀ କ'ଣ? ଗୋଟିଏ ବାକ୍ୟରେ କୁହନ୍ତୁ।",
    "ta": "இந்தியாவின் தலைநகரம் எது? ஒரு வாக்கியத்தில் சொல்லுங்கள்.",
    "te": "భారతదేశ రాజధాని ఏమిటి? ఒక వాక్యంలో చెప్పండి.",
    "kn": "ಭಾರತದ ರಾಜಧಾನಿ ಯಾವುದು? ಒಂದು ವಾಕ್ಯದಲ್ಲಿ ಹೇಳಿ.",
    "ml": "ഇന്ത്യയുടെ തലസ്ഥാനം ഏതാണ്? ഒരു വാക്യത്തിൽ പറയൂ.",
    "en": "What is the capital of India? Answer in one sentence.",
}


def script_fraction(text: str, lang: str) -> tuple[float, int]:
    name, lo, hi = SCRIPTS[lang]
    letters = [c for c in text if unicodedata.category(c).startswith("L")]
    if not letters:
        return 0.0, 0
    if lang == "en":
        ok = sum(1 for c in letters if c.isascii())
    else:
        ok = sum(1 for c in letters if lo <= ord(c) <= hi)
    return ok / len(letters), len(letters)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(ROOT / "benchmarks" / "results" / "production_v1" / "llm_script_check_v1.json"))
    parser.add_argument("--threshold", type=float, default=0.6,
                        help="min expected-script letter fraction to count as consistent")
    args = parser.parse_args(argv)

    try:
        llm = LLMClient()
    except Exception as exc:                              # noqa: BLE001
        print(f"LLM not configured: {exc} -- NOT TESTED")
        return 1

    results = {}
    for lang, question in QUESTIONS.items():
        messages = [
            {"role": "system", "content": system_prompt(lang)},
            {"role": "user", "content": question},
        ]
        t0 = time.perf_counter()
        try:
            reply = llm.reply(messages)
            frac, n_letters = script_fraction(reply, lang)
            results[lang] = {
                "expected_script": SCRIPTS[lang][0],
                "reply": reply,
                "letters": n_letters,
                "script_fraction": round(frac, 3),
                "consistent": frac >= args.threshold,
                "reply_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            }
            print(f"[{lang}] script={SCRIPTS[lang][0]} fraction={frac:.2f} "
                  f"consistent={frac >= args.threshold} ({results[lang]['reply_ms']}ms)")
        except Exception as exc:                          # noqa: BLE001
            results[lang] = {"error": str(exc)[:200]}
            print(f"[{lang}] ERROR: {exc}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "benchmark": "llm_script_check_v1",
        "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "llm": {"backend": llm.backend, "model": llm.model},
        "note": "script-consistency spot check only; not a quality or MOS evaluation",
        "threshold": args.threshold,
        "per_lang": results,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())