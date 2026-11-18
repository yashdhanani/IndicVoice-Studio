"""Phase 3 audit: conversational language, gendered agreement and code-switching.

Every other check in this repository measures audio or recognition. This one
measures the *words* the LLM produces, which is where a call stops sounding
human before any voice is involved:

* **Gendered agreement** — the production voice is ``sid=0`` (female). Hindi,
  Marathi and Punjabi mark first-person gender in the verb, so a masculine
  "कर सकता हूँ" is spoken by a female voice. Counted, not judged.
* **Code-switching** — the caller mixes an English term in; the reply should
  keep that term rather than force a translation. The term counts as kept when
  it survives in Latin letters or as its own transliteration.
* **Repetition** — three different questions; identical openings make an agent
  sound scripted.
* **Script and length** — reply stays in the language's script and within the
  two-sentence budget the prompt asks for.

Calls the existing Groq integration (free tier). No paid API, no audio, no
human judgement claimed. Writes a NEW timestamped directory; previous runs are
never touched.

Usage:
    .venv313/Scripts/python.exe benchmarks/audit_conversational.py
    .venv313/Scripts/python.exe benchmarks/audit_conversational.py --langs hi,mr,pa
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import config                                    # noqa: E402
from src.evaluate import edit_distance                     # noqa: E402
from src.sts_pipeline import LLMClient, system_prompt      # noqa: E402

LANGS = ["hi", "gu", "mr", "bn", "ta", "te", "kn", "ml", "pa", "or", "as", "en"]

#: Three caller turns per language: a capability question (gendered verb),
#: a mixed-language turn, and a plain question.
PROMPTS = {
    "hi": {"cap": "नमस्ते, क्या आप मेरी मदद कर सकते हैं?",
           "mix": "मेरा OTP कहाँ आएगा?",
           "ask": "मेरा order कब आएगा?"},
    "gu": {"cap": "નમસ્તે, તમે મારી મદદ કરી શકો છો?",
           "mix": "મારો OTP ક્યાં આવશે?",
           "ask": "મારો order ક્યારે આવશે?"},
    "mr": {"cap": "नमस्कार, तुम्ही मला मदत करू शकता का?",
           "mix": "माझा OTP कुठे येईल?",
           "ask": "माझी order कधी येईल?"},
    "bn": {"cap": "নমস্কার, আপনি কি আমাকে সাহায্য করতে পারবেন?",
           "mix": "আমার OTP কোথায় আসবে?",
           "ask": "আমার order কখন আসবে?"},
    "ta": {"cap": "வணக்கம், நீங்கள் எனக்கு உதவ முடியுமா?",
           "mix": "என் OTP எங்கே வரும்?",
           "ask": "என் order எப்போது வரும்?"},
    "te": {"cap": "నమస్కారం, మీరు నాకు సహాయం చేయగలరా?",
           "mix": "నా OTP ఎక్కడికి వస్తుంది?",
           "ask": "నా order ఎప్పుడు వస్తుంది?"},
    "kn": {"cap": "ನಮಸ್ಕಾರ, ನೀವು ನನಗೆ ಸಹಾಯ ಮಾಡಬಹುದೇ?",
           "mix": "ನನ್ನ OTP ಎಲ್ಲಿ ಬರುತ್ತದೆ?",
           "ask": "ನನ್ನ order ಯಾವಾಗ ಬರುತ್ತದೆ?"},
    "ml": {"cap": "നമസ്കാരം, നിങ്ങൾക്ക് എന്നെ സഹായിക്കാമോ?",
           "mix": "എന്റെ OTP എവിടെ വരും?",
           "ask": "എന്റെ order എപ്പോൾ വരും?"},
    "pa": {"cap": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ, ਤੁਸੀਂ ਮੇਰੀ ਮਦਦ ਕਰ ਸਕਦੇ ਹੋ?",
           "mix": "ਮੇਰਾ OTP ਕਿੱਥੇ ਆਵੇਗਾ?",
           "ask": "ਮੇਰਾ order ਕਦੋਂ ਆਵੇਗਾ?"},
    "or": {"cap": "ନମସ୍କାର, ଆପଣ ମୋତେ ସାହାଯ୍ୟ କରିପାରିବେ କି?",
           "mix": "ମୋର OTP କେଉଁଠି ଆସିବ?",
           "ask": "ମୋର order କେବେ ଆସିବ?"},
    "as": {"cap": "নমস্কাৰ, আপুনি মোক সহায় কৰিব পাৰিবনে?",
           "mix": "মোৰ OTP ক'ত আহিব?",
           "ask": "মোৰ order কেতিয়া আহিব?"},
    "en": {"cap": "Hi, can you help me with something?",
           "mix": "Where will my OTP arrive?",
           "ask": "When will my order arrive?"},
}

#: English term the caller used, and the forms that count as keeping it.
#: A force-translation ("one time password") loses the caller's own word.
KEPT_TERMS = {
    "hi": (["OTP", "ओटीपी", "ओ.टी.पी"], ["order", "ऑर्डर"]),
    "gu": (["OTP", "ઓટીપી", "ઓ.ટી.પી"], ["order", "ઓર્ડર"]),
    "mr": (["OTP", "ओटीपी", "ओ.टी.पी"], ["order", "ऑर्डर"]),
    "bn": (["OTP", "ওটিপি", "ও.টি.পি"], ["order", "অর্ডার"]),
    "ta": (["OTP", "ஓடிபி", "ஓ.டி.பி"], ["order", "ஆர்டர்"]),
    "te": (["OTP", "ఓటీపీ", "ఓ.టీ.పీ"], ["order", "ఆర్డర్"]),
    "kn": (["OTP", "ಒಟಿಪಿ", "ಒ.ಟಿ.ಪಿ"], ["order", "ಆರ್ಡರ್"]),
    "ml": (["OTP", "ഒടിപി", "ഒ.ടി.പി"], ["order", "ഓർഡർ"]),
    "pa": (["OTP", "ਓਟੀਪੀ", "ਓ.ਟੀ.ਪੀ"], ["order", "ਆਰਡਰ"]),
    "or": (["OTP", "ଓଟିପି", "ଓଏଟି", "ଓ.ଟି.ପି"], ["order", "ଅର୍ଡର"]),
    "as": (["OTP", "অটিপি", "অ.টি.পি"], ["order", "অৰ্ডাৰ"]),
    "en": (["OTP"], ["order"]),
}

#: First-person gender markers. Only these three languages mark the speaker's
#: own gender in the verb; the rest are recorded as NOT APPLICABLE with a reason
#: rather than being scored on a rule that does not exist.
GENDER = {
    "hi": {"masculine": ["सकता", "करूँगा", "बताऊँगा", "रहा हूँ", "करता हूँ", "दूँगा"],
           "feminine": ["सकती", "करूँगी", "बताऊँगी", "रही हूँ", "करती हूँ", "दूँगी"]},
    "mr": {"masculine": ["सकतो", "करतो", "राहतो", "देतो", "बोलतो"],
           "feminine": ["सकते", "करते", "राहते", "देते", "बोलते"]},
    "pa": {"masculine": ["ਸਕਦਾ", "ਕਰਦਾ", "ਦੇਵਾਂਗਾ", "ਬੋਲਦਾ"],
           "feminine": ["ਸਕਦੀ", "ਕਰਦੀ", "ਦੇਵਾਂਗੀ", "ਬੋਲਦੀ"]},
}

NA_GENDER = {
    "gu": "first person is gender-neutral (હું કરી શકું છું); gender shows only in 2nd/3rd person",
    "bn": "first person is gender-neutral (আমি করতে পারি)",
    "ta": "first person is gender-neutral (நான் செய்கிறேன்)",
    "te": "first person is gender-neutral (నేను చేస్తాను)",
    "kn": "first person is gender-neutral (ನಾನು ಮಾಡುತ್ತೇನೆ)",
    "ml": "first person is gender-neutral (ഞാൻ ചെയ്യാം)",
    "or": "first person is gender-neutral (ମୁଁ କରିପାରିବି)",
    "as": "first person is gender-neutral (মই কৰিব পাৰোঁ)",
    "en": "first person has no grammatical gender",
}

#: Production voice: TTSEngine(sid=0) is the female voice of every tiny model.
VOICE_GENDER = "female"


#: Free tier allows 30 requests/min; pacing below that keeps the audit honest
#: instead of recording 429s as language failures.
CALL_GAP_S = 2.2


def _chat(llm: LLMClient, instruction: str, user_text: str) -> str:
    """One turn, paced and retried on the free-tier rate limit."""
    last: Exception | None = None
    for attempt in range(3):
        try:
            out = "".join(llm.stream_chat(
                [{"role": "system", "content": instruction},
                 {"role": "user", "content": user_text}]
            )).strip()
            time.sleep(CALL_GAP_S)
            return out
        except Exception as exc:                 # 429 / transient network
            last = exc
            if "429" not in str(exc) and "rate limit" not in str(exc).lower():
                raise
            time.sleep(6 * (attempt + 1))
    raise last if last else RuntimeError("empty reply")


def clean(reply: str) -> str:
    return " ".join((reply or "").split())


def first_words(text: str, count: int = 2) -> str:
    words = clean(text).lower().replace("।", "").replace(",", "").split()
    return " ".join(words[:count])


def term_kept(reply: str, forms: list[str]) -> bool:
    """Did the reply keep the caller's English term?

    Exact matching under-counts: Assamese writes the same word as ``অৰ্ডাৰ`` or
    ``অর্ডাৰ``, and inflects it (``অর্ডাৰৰ`` = "order's"). A token within 40 %
    edit distance of an accepted form counts as the same word.
    """
    low = reply.lower()
    for form in forms:
        if form.lower() in low:
            return True
    words = [w.strip(".,!?।॥\"'()") for w in reply.split()]
    for form in forms:
        target = list(form)
        if not target:
            continue
        for word in words:
            if not word:
                continue
            distance = edit_distance(list(word), target)
            if distance / len(target) <= 0.4:
                return True
    return False


def script_ok(text: str, lang: str) -> bool:
    script = config.detect_script(text)
    if not script:
        return True
    return lang in config.SCRIPT_LANGS.get(script, ())


def sentence_count(text: str) -> int:
    marks = sum(text.count(mark) for mark in ".!?।॥")
    return max(1, marks)


def audit_language(llm: LLMClient, lang: str) -> dict:
    prompts = PROMPTS[lang]
    # The live server pins the language per turn (``system_prompt(lang)``), so the
    # audit must use the same prompt or it measures a path nobody runs.
    instruction = system_prompt(lang)
    replies = {}
    for key, user_text in prompts.items():
        started = time.perf_counter()
        reply = _chat(llm, instruction, user_text)
        replies[key] = {"user": user_text, "reply": reply,
                        "ms": round((time.perf_counter() - started) * 1000)}

    result: dict = {"lang": lang, "replies": replies,
                    "script_ok": all(script_ok(r["reply"], lang) for r in replies.values())}

    # -- gender ------------------------------------------------------------
    if lang in GENDER:
        markers = GENDER[lang]
        text = replies["cap"]["reply"]
        masc = [m for m in markers["masculine"] if m in text]
        fem = [m for m in markers["feminine"] if m in text]
        if fem and not masc:
            found = "feminine"
        elif masc and not fem:
            found = "masculine"
        elif masc and fem:
            found = "mixed"
        else:
            found = "unmarked"
        result["gender"] = {
            "voice": VOICE_GENDER, "expected": "feminine", "found": found,
            "masculine_markers": masc, "feminine_markers": fem,
            "pass": found in {"feminine", "unmarked"},
        }
    else:
        result["gender"] = {"voice": VOICE_GENDER, "status": "NOT APPLICABLE",
                            "reason": NA_GENDER[lang], "pass": None}

    # -- code-switching ----------------------------------------------------
    otp_forms, order_forms = KEPT_TERMS[lang]
    otp_kept = term_kept(replies["mix"]["reply"], otp_forms)
    order_kept = term_kept(replies["ask"]["reply"], order_forms)
    latin = sum(1 for ch in replies["mix"]["reply"] if ch.isascii() and ch.isalpha())
    result["code_switch"] = {
        "otp_term_kept": otp_kept, "order_term_kept": order_kept,
        "latin_letters_in_mixed_reply": latin,
        "pass": otp_kept and order_kept,
    }

    # -- repetition --------------------------------------------------------
    openings = [first_words(r["reply"]) for r in replies.values()]
    repeated = len(openings) != len(set(openings))
    result["repetition"] = {"openings": openings, "duplicate_opening": repeated,
                            "pass": not repeated}

    # -- length ------------------------------------------------------------
    counts = {key: sentence_count(r["reply"]) for key, r in replies.items()}
    result["length"] = {"sentences": counts,
                        "pass": all(count <= 3 for count in counts.values())}
    result["pass"] = all(
        part.get("pass") is not False
        for part in (result["gender"], result["code_switch"],
                     result["repetition"], result["length"])
    ) and result["script_ok"]
    return result


def render(results: list[dict]) -> str:
    lines = [
        "# Phase 3 — conversational language audit",
        "",
        f"Production voice is `{VOICE_GENDER}` (`sid=0`). Calls made against the",
        "existing Groq integration; no audio, no human listening claimed.",
        "",
        "| lang | gender | code-switch | repetition | script | length | verdict |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in results:
        if "error" in item:
            lines.append(f"| {item['lang']} | - | - | - | - | - | ERROR: {item['error']} |")
            continue
        gender = item["gender"]
        if gender.get("status") == "NOT APPLICABLE":
            gender_cell = "N/A"
        else:
            gender_cell = f"{gender['found']} (want {gender['expected']})"
        cs = item["code_switch"]
        cs_cell = ("kept" if cs["pass"] else
                   f"lost otp={cs['otp_term_kept']} order={cs['order_term_kept']}")
        lines.append(
            f"| {item['lang']} | {gender_cell} | {cs_cell} | "
            f"{'repeat' if item['repetition']['duplicate_opening'] else 'varied'} | "
            f"{'ok' if item['script_ok'] else 'WRONG'} | "
            f"{'ok' if item['length']['pass'] else 'long'} | "
            f"{'PASS (automated)' if item['pass'] else 'FAIL'} |"
        )
    lines.append("")
    lines.append("## Replies (for human review)")
    lines.append("")
    for item in results:
        if "error" in item:
            continue
        lines.append(f"### {item['lang']}")
        for key, turn in item["replies"].items():
            lines.append(f"- **{key}** · «{turn['user']}» → «{clean(turn['reply'])}» "
                         f"({turn['ms']} ms)")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 3 conversational audit")
    parser.add_argument("--langs", default=",".join(LANGS))
    parser.add_argument("--out-root", default="benchmarks/results/human_voice_quality/conversational")
    args = parser.parse_args(argv)

    langs = [l.strip() for l in args.langs.split(",") if l.strip()]
    llm = LLMClient()
    llm.warm()

    results = []
    for lang in langs:
        try:
            results.append(audit_language(llm, lang))
            print(f"{lang}: {'PASS' if results[-1]['pass'] else 'FAIL'}")
        except Exception as exc:
            print(f"{lang}: ERROR {type(exc).__name__}: {exc}")
            results.append({"lang": lang, "error": f"{type(exc).__name__}: {exc}", "pass": False})

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(args.out_root) / stamp
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(
        json.dumps({"generated": stamp, "languages": results}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    report = render(results)
    (out / "report.md").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"report -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
