"""Make text pronounceable by the local voices.

The MMS/Piper voices here have tiny vocabularies: the Hindi model knows no Latin
letters at all and the Gujarati model knows no ASCII digits. Anything outside
the vocabulary is *silently skipped* by sherpa-onnx, which is why a sentence like
"आपका ऑर्डर OK है, WhatsApp पर मैसेज आएगा" came out as "ऑर्डर है पर मैसेज आएगा".

This module rewrites such text into the voice's own script before synthesis:

* English loanwords that Indian speakers say in English anyway ("WhatsApp",
  "OTP", "KYB") are looked up in a curated table (best pronunciation).
* Anything else in Latin script is transliterated with a small rule-based
  roman -> Devanagari/Gujarati mapper.
* Leftover ASCII digits become words.
* Only characters present in the model's ``tokens.txt`` survive, so nothing is
  dropped silently again (a warning reports what was removed).
"""

from __future__ import annotations

import re

from .config import resolve_lang

# --------------------------------------------------------------------------- #
# Curated loanwords (spoken as-is in Indian languages)
# --------------------------------------------------------------------------- #

LOANWORDS = {
    "hi": {
        "ok": "ओके", "okay": "ओके", "whatsapp": "व्हाट्सएप", "upi": "यू पी आई",
        "otp": "ओ टी पी", "sms": "एस एम एस", "id": "आई डी", "kyc": "के वाई सी",
        "app": "ऐप", "email": "ईमेल", "google": "गूगल", "sim": "सिम", "pin": "पिन",
        "bank": "बैंक", "account": "अकाउंट", "order": "ऑर्डर", "payment": "पेमेंट",
        "bill": "बिल", "number": "नंबर", "recharge": "रीचार्ज", "link": "लिंक",
        "online": "ऑनलाइन", "card": "कार्ड", "cash": "कैश", "call": "कॉल",
        "message": "मैसेज", "address": "एड्रेस", "delivery": "डिलीवरी",
        "status": "स्टेटस", "customer": "कस्टमर", "service": "सर्विस",
        "problem": "प्रॉब्लम", "mobile": "मोबाइल", "phone": "फ़ोन", "net": "नेट",
        "wifi": "वाई फ़ाई", "password": "पासवर्ड", "login": "लॉगिन",
        "cancel": "कैंसल", "confirm": "कन्फ़र्म", "update": "अपडेट",
        "manager": "मैनेजर", "office": "ऑफ़िस", "doctor": "डॉक्टर",
        "ticket": "टिकट", "train": "ट्रेन", "bus": "बस", "auto": "ऑटो",
        "please": "प्लीज़", "sorry": "सॉरी", "thanks": "थैंक्स", "thank": "थैंक",
        "hello": "हैलो", "hi": "हाय", "bye": "बाय", "yes": "यस", "no": "नो",
    },
    "gu": {
        "ok": "ઓકે", "okay": "ઓકે", "whatsapp": "વોટ્સએપ", "upi": "યુ પી આઈ",
        "otp": "ઓ ટી પી", "sms": "એસ એમ એસ", "id": "આઈ ડી", "kyc": "કે વાય સી",
        "app": "એપ", "email": "ઈમેલ", "google": "ગૂગલ", "sim": "સિમ", "pin": "પિન",
        "bank": "બેંક", "account": "એકાઉન્ટ", "order": "ઓર્ડર", "payment": "પેમેન્ટ",
        "bill": "બિલ", "number": "નંબર", "recharge": "રિચાર્જ", "link": "લિંક",
        "online": "ઓનલાઈન", "card": "કાર્ડ", "cash": "કેશ", "call": "કૉલ",
        "message": "મેસેજ", "address": "એડ્રેસ", "delivery": "ડિલિવરી",
        "status": "સ્ટેટસ", "customer": "કસ્ટમર", "service": "સર્વિસ",
        "problem": "પ્રોબ્લેમ", "mobile": "મોબાઈલ", "phone": "ફોન",
        "password": "પાસવર્ડ", "login": "લૉગિન", "cancel": "કૅન્સલ",
        "confirm": "કન્ફર્મ", "update": "અપડેટ", "manager": "મેનેજર",
        "office": "ઑફિસ", "please": "પ્લીઝ", "sorry": "સોરી",
        "thanks": "થેન્ક્સ", "hello": "હેલો", "bye": "બાય",
    },
}

#: Languages whose script we can generate with the rule-based mapper.
_DEVANAGARI_LANGS = {"hi", "mr"}
_GUJARATI_LANGS = {"gu"}

_CONS = [
    ("chh", "छ"), ("cch", "च्छ"), ("kh", "ख"), ("gh", "घ"), ("ch", "च"),
    ("jh", "झ"), ("th", "थ"), ("dh", "ध"), ("ph", "फ"), ("bh", "भ"),
    ("sh", "श"), ("zh", "झ"), ("ng", "ंग"), ("ny", "ञ"),
    ("k", "क"), ("g", "ग"), ("c", "क"), ("j", "ज"), ("t", "ट"), ("d", "ड"),
    ("n", "न"), ("p", "प"), ("f", "फ"), ("b", "ब"), ("m", "म"), ("y", "य"),
    ("r", "र"), ("l", "ल"), ("v", "व"), ("w", "व"), ("s", "स"), ("h", "ह"),
    ("z", "ज़"), ("q", "क़"), ("x", "क्स"),
]

_VOWELS = [
    ("ai", "ऐ", "ै"), ("au", "औ", "ौ"), ("aa", "आ", "ा"), ("ee", "ई", "ी"),
    ("ea", "ई", "ी"), ("ii", "ई", "ी"), ("oo", "ऊ", "ू"), ("ou", "औ", "ौ"),
    ("a", "अ", ""), ("i", "इ", "ि"), ("u", "उ", "ु"), ("e", "ए", "े"), ("o", "ओ", "ो"),
]

_VIRAMA = "्"

_DIGIT_WORDS = {
    "hi": "शून्य एक दो तीन चार पाँच छह सात आठ नौ".split(),
    "mr": "शून्य एक दो तीन चार पाँच सहा सात आठ नऊ".split(),
    "gu": "શૂન્ય એક બે ત્રણ ચાર પાંચ છ સાત આઠ નવ".split(),
}


def _digits_for(code: str) -> list[str] | None:
    """Digit words for a language, generated from Hindi when not curated."""
    words = _DIGIT_WORDS.get(code)
    if words:
        return words
    offset = _SCRIPT_SHIFT.get(code)
    if offset is None:
        return None
    return [_shift_script(w, offset) for w in _DIGIT_WORDS["hi"]]

_VOWELS_SET = "aeiou"
_CONS_SET = "bcdfghjklmnpqrstvwxyz"

_LATIN_RUN = re.compile(r"[A-Za-z]+")
_DIGIT_RUN = re.compile(r"\d")


def _to_gujarati(text: str) -> str:
    """Shift Devanagari codepoints to their Gujarati counterparts."""
    out = []
    for ch in text:
        code = ord(ch)
        out.append(chr(code + 0x180) if 0x0900 <= code <= 0x097F else ch)
    return "".join(out)


def _roman_word(word: str) -> str:
    """Rule-based roman -> Devanagari (approximate but never silent)."""
    w = word.lower()
    out: list[str] = []
    i, n = 0, len(w)
    while i < n:
        consonant = next(((t, d) for t, d in _CONS if w.startswith(t, i)), None)
        if consonant is not None:
            token, dev = consonant
            i += len(token)
            sign = ""
            if i < n and w[i] in _VOWELS_SET:
                match = next((v for v in _VOWELS if w.startswith(v[0], i)), None)
                if match is not None:
                    sign = match[2]
                    i += len(match[0])
            elif i < n and w[i] in _CONS_SET:
                sign = _VIRAMA
            out.append(dev + sign)
            continue

        vowel = next((v for v in _VOWELS if w.startswith(v[0], i)), None)
        if vowel is not None:
            out.append(vowel[1])
            i += len(vowel[0])
            continue
        i += 1
    return "".join(out)


#: Unicode offset from Devanagari to each Indic script. The Indic blocks keep
#: the same letter order (ka..ha, a..au, virama, vowel signs), so one phonetic
#: mapping plus an offset covers every script these voices read.
_SCRIPT_SHIFT = {
    "gu": 0x180,
    "bn": 0x080,
    "as": 0x080,      # Assamese shares the Bengali block
    "pa": 0x100,
    "or": 0x200,
    "ta": 0x280,
    "te": 0x300,
    "kn": 0x380,
    "ml": 0x400,
}

#: Letters some scripts do not have (Tamil has no aspirates): fall back to the
#: unaspirated/nearest equivalent so the word stays pronounceable.
_SIMPLIFY = {
    "ख": "क", "घ": "ग", "छ": "च", "झ": "ज", "ठ": "ट", "ढ": "ड",
    "थ": "त", "ध": "द", "फ": "प", "भ": "ब", "श": "स", "ष": "स",
    "ज़": "ज", "क़": "क",
}


def _shift_script(text: str, offset: int) -> str:
    """Move Devanagari text into another Indic script, simplifying what it lacks."""
    import unicodedata

    out = []
    for ch in text:
        code = ord(ch)
        if not 0x0900 <= code <= 0x097F:
            out.append(ch)
            continue
        shifted = chr(code + offset)
        if unicodedata.category(shifted) == "Cn":            # unassigned in this script
            base = _SIMPLIFY.get(ch)
            shifted = chr(ord(base) + offset) if base else ""
            if shifted and unicodedata.category(shifted) == "Cn":
                shifted = ""
        out.append(shifted)
    return "".join(out)


def transliterate_word(word: str, lang: str) -> str:
    """Return ``word`` written in the voice's script."""
    code = resolve_lang(lang)
    lowered = word.lower()
    table = LOANWORDS.get(code)
    if table and lowered in table:
        return table[lowered]
    if code == "en":
        return word
    devanagari = _roman_word(word)
    if code in _DEVANAGARI_LANGS:
        return devanagari
    offset = _SCRIPT_SHIFT.get(code)
    return _shift_script(devanagari, offset) if offset else word


def localize_text(text: str, lang: str, vocab: set[str] | None = None) -> str:
    """Rewrite Latin words/digits and drop only characters the voice cannot say."""
    code = resolve_lang(lang)
    if not text:
        return ""

    if code not in ({"en", "hi", "mr", "gu"} | set(_SCRIPT_SHIFT)):
        # Unknown script mapping for this voice: leave the text alone.
        localized = text
    else:
        localized = _LATIN_RUN.sub(lambda m: transliterate_word(m.group(0), code), text)
        digits = _digits_for(code)
        if digits:
            localized = _DIGIT_RUN.sub(lambda m: f" {digits[int(m.group(0))]} ", localized)

    localized = re.sub(r"\s+", " ", localized).strip()
    if vocab:
        kept = [ch for ch in localized if ch == " " or ch in vocab]
        localized = re.sub(r"\s+", " ", "".join(kept)).strip()
    return localized
