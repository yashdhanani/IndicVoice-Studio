"""Text normalisation and streaming sentence splitting for Indian TTS.

The MMS/VITS voices only pronounce what they are given, so before synthesis we
turn text into plain spoken words:

* currency with Indian grouping (``₹1,50,000`` -> ``एक लाख पचास हज़ार रुपये``)
* dates (``16/11/2026`` -> ``सोलह नवंबर दो हज़ार छब्बीस``)
* phone numbers and OTPs, digit by digit with natural pauses
* UPI ids (``ravi.kumar@okhdfc``) and common abbreviations
* any leftover digits, so nothing reaches the model as a bare number

``split_sentences`` / ``SentenceSplitter`` cut text at natural punctuation so
the engine can speak the first sentence while the LLM is still generating.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterator

from .config import resolve_lang

try:  # optional: refines Unicode/script cleanup for Indic text
    from indicnlp.normalize.indic_normalize import IndicNormalizerFactory

    _INDIC_NORMALIZERS = {
        lang: IndicNormalizerFactory().get_normalizer(lang)
        for lang in ("hi", "gu", "mr", "bn", "ta", "te", "kn", "ml", "pa", "or", "as")
    }
except Exception:  # pragma: no cover - optional dependency
    _INDIC_NORMALIZERS = {}


# --------------------------------------------------------------------------- #
# Numeral tables (0-19 units, 20-90 tens, Indian scale words)
# --------------------------------------------------------------------------- #

NUMERALS: dict[str, dict] = {
    "en": {
        "units": ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
                  "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
                  "seventeen", "eighteen", "nineteen"],
        "tens": {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty", 6: "sixty",
                 7: "seventy", 8: "eighty", 9: "ninety"},
        "tens_join": "-",
        "hundred": "hundred", "thousand": "thousand", "lakh": "lakh", "crore": "crore",
        "rupee": "rupees", "paisa": "paise", "and": "and", "decimal": "point",
    },
    "hi": {
        "units": ["शून्य", "एक", "दो", "तीन", "चार", "पाँच", "छह", "सात", "आठ", "नौ",
                  "दस", "ग्यारह", "बारह", "तेरह", "चौदह", "पंद्रह", "सोलह", "सत्रह", "अठारह", "उन्नीस"],
        "tens": {2: "बीस", 3: "तीस", 4: "चालीस", 5: "पचास", 6: "साठ", 7: "सत्तर", 8: "अस्सी", 9: "नब्बे"},
        "irregular": [
            "इक्कीस", "बाईस", "तेईस", "चौबीस", "पच्चीस", "छब्बीस", "सत्ताईस", "अट्ठाईस", "उनतीस",
            "तीस", "इकतीस", "बत्तीस", "तैंतीस", "चौंतीस", "पैंतीस", "छत्तीस", "सैंतीस", "अड़तीस", "उनतालीस",
            "चालीस", "इकतालीस", "बयालीस", "तैंतालीस", "चवालीस", "पैंतालीस", "छियालीस", "सैंतालीस", "अड़तालीस", "उनचास",
            "पचास", "इक्यावन", "बावन", "तिरेपन", "चौवन", "पचपन", "छप्पन", "सत्तावन", "अट्ठावन", "उनसठ",
            "साठ", "इकसठ", "बासठ", "तिरसठ", "चौंसठ", "पैंसठ", "छियासठ", "सड़सठ", "अड़सठ", "उनहत्तर",
            "सत्तर", "इकहत्तर", "बहत्तर", "तिहत्तर", "चौहत्तर", "पचहत्तर", "छिहत्तर", "सतहत्तर", "अठहत्तर", "उन्यासी",
            "अस्सी", "इक्यासी", "बयासी", "तिरासी", "चौरासी", "पचासी", "छियासी", "सत्तासी", "अट्ठासी", "नवासी",
            "नब्बे", "इक्यानवे", "बानवे", "तिरानवे", "चौरानवे", "पंचानवे", "छियानवे", "सत्तानवे", "अट्ठानवे", "निन्यानवे",
        ],
        "one_hundred": "एक सौ", "one_thousand": "एक हज़ार",
        "one_lakh": "एक लाख", "one_crore": "एक करोड़",
        "hundred": "सौ", "thousand": "हज़ार", "lakh": "लाख", "crore": "करोड़",
        "rupee": "रुपये", "paisa": "पैसे", "and": "और", "decimal": "दशमलव",
    },
    "gu": {
        "units": ["શૂન્ય", "એક", "બે", "ત્રણ", "ચાર", "પાંચ", "છ", "સાત", "આઠ", "નવ",
                  "દસ", "અગિયાર", "બાર", "તેર", "ચૌદ", "પંદર", "સોળ", "સત્તર", "અઢાર", "ઓગણીસ"],
        "tens": {2: "વીસ", 3: "ત્રીસ", 4: "ચાલીસ", 5: "પચાસ", 6: "સાઠ", 7: "સિત્તેર", 8: "એંસી", 9: "નેવું"},
        "irregular": [
            "એકવીસ", "બાવીસ", "તેવીસ", "ચોવીસ", "પચ્ચીસ", "છવ્વીસ", "સત્તાવીસ", "અઠ્ઠાવીસ", "ઓગણત્રીસ",
            "ત્રીસ", "એકત્રીસ", "બત્રીસ", "તેત્રીસ", "ચોત્રીસ", "પાંત્રીસ", "છત્રીસ", "સાડત્રીસ", "આડત્રીસ", "ઓગણચાલીસ",
            "ચાલીસ", "એકતાલીસ", "બેતાલીસ", "તેતાલીસ", "ચુમ્માલીસ", "પિસ્તાલીસ", "છેતાલીસ", "સુડતાલીસ", "આડતાલીસ", "ઓગણપચાસ",
            "પચાસ", "એકાવન", "બાવન", "ત્રેપન", "ચોપન", "પંચાવન", "છપ્પન", "સત્તાવન", "અઠ્ઠાવન", "ઓગણસાઠ",
            "સાઠ", "એકસઠ", "બાસઠ", "ત્રેસઠ", "ચોસઠ", "પાંસઠ", "છાસઠ", "સડસઠ", "અડસઠ", "ઓગણોતેર",
            "સિત્તેર", "એકોતેર", "બોતેર", "તોતેર", "ચુમોતેર", "પંચોતેર", "છોતેર", "સિત્યોતેર", "ઈઠોતેર", "ઓગણ્યાસી",
            "એંસી", "એક્યાસી", "બ્યાસી", "ત્યાસી", "ચોર્યાસી", "પંચ્યાસી", "છ્યાસી", "સિત્યાસી", "ઈઠ્યાસી", "નેવ્યાસી",
            "નેવું", "એકાણું", "બાણું", "ત્રાણું", "ચોરાણું", "પંચાણું", "છન્નું", "સત્તાણું", "અઠ્ઠાણું", "નવ્વાણું",
        ],
        "one_hundred": "સો", "one_thousand": "એક હજાર",
        "one_lakh": "એક લાખ", "one_crore": "એક કરોડ",
        "hundred": "સો", "thousand": "હજાર", "lakh": "લાખ", "crore": "કરોડ",
        "rupee": "રૂપિયા", "paisa": "પૈસા", "and": "અને", "decimal": "દશાંશ",
    },
    "mr": {
        "units": ["शून्य", "एक", "दोन", "तीन", "चार", "पाच", "सहा", "सात", "आठ", "नऊ",
                  "दहा", "अकरा", "बारा", "तेरा", "चौदा", "पंधरा", "सोळा", "सतरा", "अठरा", "एकोणीस"],
        "tens": {2: "वीस", 3: "तीस", 4: "चाळीस", 5: "पन्नास", 6: "साठ", 7: "सत्तर", 8: "ऐंशी", 9: "नव्वद"},
        "one_hundred": "शंभर", "one_thousand": "एक हजार",
        "one_lakh": "एक लाख", "one_crore": "एक कोटी",
        "hundred": "शे", "thousand": "हजार", "lakh": "लाख", "crore": "कोटी",
        "rupee": "रुपये", "paisa": "पैसे", "and": "आणि", "decimal": "दशांश",
    },
    "bn": {
        "units": ["শূন্য", "এক", "দুই", "তিন", "চার", "পাঁচ", "ছয়", "সাত", "আট", "নয়",
                  "দশ", "এগারো", "বারো", "তেরো", "চৌদ্দ", "পনেরো", "ষোল", "সতেরো", "আঠারো", "উনিশ"],
        "tens": {2: "বিশ", 3: "ত্রিশ", 4: "চল্লিশ", 5: "পঞ্চাশ", 6: "ষাট", 7: "সত্তর", 8: "আশি", 9: "নব্বই"},
        "one_hundred": "একশ", "one_thousand": "এক হাজার",
        "one_lakh": "এক লাখ", "one_crore": "এক কোটি",
        "hundred": "শো", "thousand": "হাজার", "lakh": "লাখ", "crore": "কোটি",
        "rupee": "টাকা", "paisa": "পয়সা", "and": "এবং", "decimal": "দশমিক",
    },
    "ta": {
        "units": ["பூஜ்யம்", "ஒன்று", "இரண்டு", "மூன்று", "நான்கு", "ஐந்து", "ஆறு", "ஏழு", "எட்டு", "ஒன்பது",
                  "பத்து", "பதினொன்று", "பன்னிரண்டு", "பதின்மூன்று", "பதினான்கு", "பதினைந்து", "பதினாறு",
                  "பதினேழு", "பதினெட்டு", "பத்தொன்பது"],
        "tens": {2: "இருபது", 3: "முப்பது", 4: "நாற்பது", 5: "ஐம்பது", 6: "அறுபது", 7: "எழுபது", 8: "எண்பது", 9: "தொண்ணூறு"},
        "tens_join": " ",
        "one_hundred": "நூறு", "one_thousand": "ஆயிரம்",
        "one_lakh": "ஒரு லட்சம்", "one_crore": "ஒரு கோடி",
        "hundred": "நூறு", "thousand": "ஆயிரம்", "lakh": "லட்சம்", "crore": "கோடி",
        "rupee": "ரூபாய்", "paisa": "பைசா", "and": "மற்றும்", "decimal": "புள்ளி",
    },
    "te": {
        "units": ["సున్నా", "ఒకటి", "రెండు", "మూడు", "నాలుగు", "ఐదు", "ఆరు", "ఏడు", "ఎనిమిది", "తొమ్మిది",
                  "పది", "పదకొండు", "పన్నెండు", "పదమూడు", "పద్నాలుగు", "పదిహేను", "పదహారు", "పదిహేడు",
                  "పద్దెనిమిది", "పంతొమ్మిది"],
        "tens": {2: "ఇరవై", 3: "ముప్పై", 4: "నలభై", 5: "యాభై", 6: "అరవై", 7: "డెబ్బై", 8: "ఎనభై", 9: "తొంభై"},
        "tens_join": " ",
        "one_hundred": "వంద", "one_thousand": "వెయ్యి",
        "one_lakh": "ఒక లక్ష", "one_crore": "ఒక కోటి",
        "hundred": "వంద", "thousand": "వెయ్యి", "lakh": "లక్ష", "crore": "కోటి",
        "rupee": "రూపాయలు", "paisa": "పైసలు", "and": "మరియు", "decimal": "పాయింట్",
    },
    "kn": {
        "units": ["ಸೊನ್ನೆ", "ಒಂದು", "ಎರಡು", "ಮೂರು", "ನಾಲ್ಕು", "ಐದು", "ಆರು", "ಏಳು", "ಎಂಟು", "ಒಂಬತ್ತು",
                  "ಹತ್ತು", "ಹನ್ನೊಂದು", "ಹನ್ನೆರಡು", "ಹದಿಮೂರು", "ಹದಿನಾಲ್ಕು", "ಹದಿನೈದು", "ಹದಿನಾರು",
                  "ಹದಿನೇಳು", "ಹದಿನೆಂಟು", "ಹತ್ತೊಂಬತ್ತು"],
        "tens": {2: "ಇಪ್ಪತ್ತು", 3: "ಮೂವತ್ತು", 4: "ನಲವತ್ತು", 5: "ಐವತ್ತು", 6: "ಅರವತ್ತು", 7: "ಎಪ್ಪತ್ತು", 8: "ಎಂಬತ್ತು", 9: "ತೊಂಬತ್ತು"},
        "tens_join": " ",
        "one_hundred": "ನೂರು", "one_thousand": "ಸಾವಿರ",
        "one_lakh": "ಒಂದು ಲಕ್ಷ", "one_crore": "ಒಂದು ಕೋಟಿ",
        "hundred": "ನೂರು", "thousand": "ಸಾವಿರ", "lakh": "ಲಕ್ಷ", "crore": "ಕೋಟಿ",
        "rupee": "ರೂಪಾಯಿ", "paisa": "ಪೈಸೆ", "and": "ಮತ್ತು", "decimal": "ಪಾಯಿಂಟ್",
    },
    "ml": {
        "units": ["പൂജ്യം", "ഒന്ന്", "രണ്ട്", "മൂന്ന്", "നാല്", "അഞ്ച്", "ആറ്", "ഏഴ്", "എട്ട്", "ഒമ്പത്",
                  "പത്ത്", "പതിനൊന്ന്", "പന്ത്രണ്ട്", "പതിമൂന്ന്", "പതിനാല്", "പതിനഞ്ച്", "പതിനാറ്",
                  "പതിനേഴ്", "പതിനെട്ട്", "പത്തൊമ്പത്"],
        "tens": {2: "ഇരുപത്", 3: "മുപ്പത്", 4: "നാല്പത്", 5: "അമ്പത്", 6: "അറുപത്", 7: "എഴുപത്", 8: "എൺപത്", 9: "തൊണ്ണൂറ്"},
        "tens_join": " ",
        "one_hundred": "നൂറ്", "one_thousand": "ആയിരം",
        "one_lakh": "ഒരു ലക്ഷം", "one_crore": "ഒരു കോടി",
        "hundred": "നൂറ്", "thousand": "ആയിരം", "lakh": "ലക്ഷം", "crore": "കോടി",
        "rupee": "രൂപ", "paisa": "പൈസ", "and": "കൂടാതെ", "decimal": "പോയിന്റ്",
    },
    "pa": {
        "units": ["ਸਿਫ਼ਰ", "ਇੱਕ", "ਦੋ", "ਤਿੰਨ", "ਚਾਰ", "ਪੰਜ", "ਛੇ", "ਸੱਤ", "ਅੱਠ", "ਨੌਂ",
                  "ਦਸ", "ਗਿਆਰਾਂ", "ਬਾਰਾਂ", "ਤੇਰਾਂ", "ਚੌਦਾਂ", "ਪੰਦਰਾਂ", "ਸੋਲਾਂ", "ਸਤਾਰਾਂ", "ਅਠਾਰਾਂ", "ਉੱਨੀ"],
        "tens": {2: "ਵੀਹ", 3: "ਤੀਹ", 4: "ਚਾਲੀ", 5: "ਪੰਜਾਹ", 6: "ਸੱਠ", 7: "ਸੱਤਰ", 8: "ਅੱਸੀ", 9: "ਨੱਬੇ"},
        "tens_join": " ",
        "one_hundred": "ਸੌ", "one_thousand": "ਹਜ਼ਾਰ",
        "one_lakh": "ਇੱਕ ਲੱਖ", "one_crore": "ਇੱਕ ਕਰੋੜ",
        "hundred": "ਸੌ", "thousand": "ਹਜ਼ਾਰ", "lakh": "ਲੱਖ", "crore": "ਕਰੋੜ",
        "rupee": "ਰੁਪਏ", "paisa": "ਪੈਸੇ", "and": "ਅਤੇ", "decimal": "ਦਸ਼ਮਲਵ",
    },
    "or": {
        "units": ["ଶୂନ୍ୟ", "ଏକ", "ଦୁଇ", "ତିନି", "ଚାରି", "ପାଞ୍ଚ", "ଛଅ", "ସାତ", "ଆଠ", "ନଅ",
                  "ଦଶ", "ଏଗାର", "ବାର", "ତେର", "ଚଉଦ", "ପନ୍ଦର", "ଷୋହଳ", "ସତର", "ଅଠର", "ଉଣେଇଶ"],
        "tens": {2: "କୋଡ଼ିଏ", 3: "ତିରିଶ", 4: "ଚାଳିଶ", 5: "ପଚାଶ", 6: "ଷାଠିଏ", 7: "ସତୁରି", 8: "ଅଶୀ", 9: "ନବେ"},
        "tens_join": " ",
        "one_hundred": "ଶହ", "one_thousand": "ହଜାର",
        "one_lakh": "ଏକ ଲକ୍ଷ", "one_crore": "ଏକ କୋଟି",
        "hundred": "ଶହ", "thousand": "ହଜାର", "lakh": "ଲକ୍ଷ", "crore": "କୋଟି",
        "rupee": "ଟଙ୍କା", "paisa": "ପଇସା", "and": "ଏବଂ", "decimal": "ଦଶମିକ",
    },
    "as": {
        "units": ["শূন্য", "এক", "দুই", "তিনি", "চাৰি", "পাঁচ", "ছয়", "সাত", "আঠ", "ন",
                  "দহ", "এঘাৰ", "বাৰ", "তেৰ", "চৈধ্য", "পোন্ধৰ", "ষোল্ল", "সোতৰ", "ওঠৰ", "ঊনৈশ"],
        "tens": {2: "বিশ", 3: "ত্ৰিশ", 4: "চল্লিশ", 5: "পঞ্চাশ", 6: "ষাঠি", 7: "সত্তৰ", 8: "আশী", 9: "নব্বৈ"},
        "tens_join": " ",
        "one_hundred": "শ", "one_thousand": "হাজাৰ",
        "one_lakh": "এক লাখ", "one_crore": "এক কোটি",
        "hundred": "শ", "thousand": "হাজাৰ", "lakh": "লাখ", "crore": "কোটি",
        "rupee": "টকা", "paisa": "পইচা", "and": "আৰু", "decimal": "দশমিক",
    },
}

#: Month names for date normalisation.
MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"],
    "hi": ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर",
           "अक्टूबर", "नवंबर", "दिसंबर"],
    "gu": ["જાન્યુઆરી", "ફેબ્રુઆરી", "માર્ચ", "એપ્રિલ", "મે", "જૂન", "જુલાઈ", "ઓગસ્ટ", "સપ્ટેમ્બર",
           "ઓક્ટોબર", "નવેમ્બર", "ડિસેમ્બર"],
    "mr": ["जानेवारी", "फेब्रुवारी", "मार्च", "एप्रिल", "मे", "जून", "जुलै", "ऑगस्ट", "सप्टेंबर",
           "ऑक्टोबर", "नोव्हेंबर", "डिसेंबर"],
    "bn": ["জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন", "জুলাই", "আগস্ট", "সেপ্টেম্বর",
           "অক্টোবর", "নভেম্বর", "ডিসেম্বর"],
    "ta": ["ஜனவரி", "பிப்ரவரி", "மார்ச்", "ஏப்ரல்", "மே", "ஜூன்", "ஜூலை", "ஆகஸ்ட்", "செப்டம்பர்",
           "அக்டோபர்", "நவம்பர்", "டிசம்பர்"],
    "te": ["జనవరి", "ఫిబ్రవరి", "మార్చి", "ఏప్రిల్", "మే", "జూన్", "జూలై", "ఆగస్టు", "సెప్టెంబర్",
           "అక్టోబర్", "నవంబర్", "డిసెంబర్"],
    "kn": ["ಜನವರಿ", "ಫೆಬ್ರವರಿ", "ಮಾರ್ಚ್", "ಏಪ್ರಿಲ್", "ಮೇ", "ಜೂನ್", "ಜುಲೈ", "ಆಗಸ್ಟ್", "ಸೆಪ್ಟೆಂಬರ್",
           "ಅಕ್ಟೋಬರ್", "ನವೆಂಬರ್", "ಡಿಸೆಂಬರ್"],
    "ml": ["ജനുവരി", "ഫെബ്രുവരി", "മാർച്ച്", "ഏപ്രിൽ", "മേയ്", "ജൂൺ", "ജൂലൈ", "ഓഗസ്റ്റ്", "സെപ്റ്റംബർ",
           "ഒക്ടോബർ", "നവംബർ", "ഡിസംബർ"],
    "pa": ["ਜਨਵਰੀ", "ਫ਼ਰਵਰੀ", "ਮਾਰਚ", "ਅਪ੍ਰੈਲ", "ਮਈ", "ਜੂਨ", "ਜੁਲਾਈ", "ਅਗਸਤ", "ਸਤੰਬਰ",
           "ਅਕਤੂਬਰ", "ਨਵੰਬਰ", "ਦਸੰਬਰ"],
    "or": ["ଜାନୁଆରୀ", "ଫେବ୍ରୁଆରୀ", "ମାର୍ଚ୍ଚ", "ଏପ୍ରିଲ", "ମେ", "ଜୁନ", "ଜୁଲାଇ", "ଅଗଷ୍ଟ", "ସେପ୍ଟେମ୍ବର",
           "ଅକ୍ଟୋବର", "ନଭେମ୍ବର", "ଡିସେମ୍ବର"],
    "as": ["জানুৱাৰী", "ফেব্ৰুৱাৰী", "মাৰ্চ", "এপ্ৰিল", "মে", "জুন", "জুলাই", "আগষ্ট", "ছেপ্তেম্বৰ",
           "অক্টোবৰ", "নৱেম্বৰ", "ডিচেম্বৰ"],
}

#: Abbreviation expansion (kept small and conservative per language).
ABBREVIATIONS = {
    "en": {"dr.": "Doctor", "mr.": "Mister", "mrs.": "Misses", "ms.": "Miss", "prof.": "Professor",
           "sr.": "Senior", "jr.": "Junior", "st.": "Street", "no.": "number", "etc.": "etcetera",
           "vs.": "versus", "e.g.": "for example", "i.e.": "that is", "govt.": "government",
           "approx.": "approximately", "min.": "minutes", "hrs.": "hours"},
    "hi": {"डॉ.": "डॉक्टर", "श्री.": "श्री", "श्रीमती.": "श्रीमती", "कु.": "कुमारी",
           "उदा.": "उदाहरण", "आदि.": "आदि", "प्रो.": "प्रोफेसर", "कि.मी.": "किलोमीटर"},
    "gu": {"ડૉ.": "ડોક્ટર", "શ્રી.": "શ્રી", "શ્રીમતી.": "શ્રીમતી", "કુ.": "કુમારી",
           "દા.": "દાખલા", "પ્રો.": "પ્રોફેસર", "કિ.મી.": "કિલોમીટર"},
    "mr": {"डॉ.": "डॉक्टर", "श्री.": "श्री", "प्रा.": "प्राध्यापक", "क्र.": "क्रमांक"},
    "bn": {"ড.": "ডাক্তার", "শ্রী.": "শ্রী", "নং.": "নম্বর"},
    "ta": {"டாக்டர்.": "டாக்டர்", "எண்.": "எண்"},
    "te": {"డా.": "డాక్టర్", "నం.": "నంబర్"},
    "kn": {"ಡಾ.": "ಡಾಕ್ಟರ್", "ನಂ.": "ನಂಬರ್"},
    "ml": {"ഡോ.": "ഡോക്ടർ", "നം.": "നമ്പർ"},
    "pa": {"ਡਾ.": "ਡਾਕਟਰ", "ਨੰ.": "ਨੰਬਰ"},
    "or": {"ଡା.": "ଡାକ୍ତର"},
    "as": {"ডাঃ": "ডাক্তৰ"},
}

_TERMINATORS = "।.!?"

# --------------------------------------------------------------------------- #
# Regex helpers
# --------------------------------------------------------------------------- #

_CURRENCY_RE = re.compile(r"(?:₹|Rs\.?|INR|रु\.?|રૂ\.?|ରୁ\.?)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", re.I)
_CURRENCY_WORDS = ("rupees", "रुपये", "રૂપિયા", "रुपये", "টাকা", "ரூபாய்", "రూపాయలు",
                   "ರೂಪಾಯಿ", "രൂപ", "ਰੁਪਏ", "ଟଙ୍କା", "টকা")
_AMOUNT_RE = re.compile(
    r"\b([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(" + "|".join(_CURRENCY_WORDS) + r")\b", re.I
)
_DATE_DMY_RE = re.compile(r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b")
_DATE_ISO_RE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_PHONE_RE = re.compile(r"(?:\+91[\s-]?|0)?\b([6-9]\d{9})\b")
_UPI_RE = re.compile(r"\b([A-Za-z0-9][A-Za-z0-9._-]{1,})@([A-Za-z][A-Za-z0-9]{1,})\b")
_OTP_HINT_RE = re.compile(r"\b(?:OTP|otp|ओटीपी|ઓટીપી|ওটিপি|ஓடிபி|ఓటీపీ|ಒಟಿಪಿ|ഒടിപി)\b")
_LEADING_ZERO_RE = re.compile(r"\b0\d{3,7}\b")
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


# --------------------------------------------------------------------------- #
# Number spelling
# --------------------------------------------------------------------------- #


def _units(lang: str, n: int) -> str:
    return NUMERALS[lang]["units"][n]


def _below_hundred(n: int, lang: str) -> str:
    data = NUMERALS[lang]
    if n < 20:
        return data["units"][n]
    tens, rest = divmod(n, 10)
    if lang == "en":
        return data["tens"][tens] + (f"-{data['units'][rest]}" if rest else "")
    irregular = data.get("irregular")
    if irregular and n >= 21:
        return irregular[n - 21]
    if not rest:                       # 20, 30, ... 90
        return data["tens"][tens]
    return f"{data['tens'][tens]} {data['units'][rest]}"


def _below_thousand(n: int, lang: str) -> str:
    data = NUMERALS[lang]
    hundreds, rest = divmod(n, 100)
    parts = []
    if hundreds == 1 and data.get("one_hundred"):
        parts.append(data["one_hundred"])
    elif hundreds:
        parts.append(f"{data['units'][hundreds]} {data['hundred']}")
    if rest:
        parts.append(_below_hundred(rest, lang))
    return " ".join(parts)


def number_to_words(n: int, lang: str) -> str:
    """Spell ``n`` with Indian grouping: crore / lakh / thousand."""
    lang = resolve_lang(lang)
    data = NUMERALS[lang]
    if n == 0:
        return data["units"][0]
    if n < 0:
        return "minus " + number_to_words(-n, lang)

    head = n % 1000
    groups = []
    n //= 1000
    while n:
        groups.append(n % 100)
        n //= 100

    thousand = groups[0] if len(groups) > 0 else 0
    lakh = groups[1] if len(groups) > 1 else 0
    crore = 0
    for i, group in enumerate(groups[2:]):
        crore += group * (100 ** i)

    parts = []
    if crore == 1 and data.get("one_crore"):
        parts.append(data["one_crore"])
    elif crore:
        parts.append(f"{number_to_words(crore, lang)} {data['crore']}")
    if lakh == 1 and data.get("one_lakh"):
        parts.append(data["one_lakh"])
    elif lakh:
        parts.append(f"{_below_hundred(lakh, lang)} {data['lakh']}")
    if thousand == 1 and data.get("one_thousand"):
        parts.append(data["one_thousand"])
    elif thousand:
        parts.append(f"{_below_hundred(thousand, lang)} {data['thousand']}")
    if head:
        parts.append(_below_thousand(head, lang))
    return " ".join(parts)


def _digits_to_words(digits: str, lang: str, paused: bool = False) -> str:
    sep = ", " if paused else " "
    return sep.join(NUMERALS[lang]["units"][int(d)] for d in digits if d.isdigit())


def number_string_to_words(raw: str, lang: str) -> str:
    lang = resolve_lang(lang)
    cleaned = raw.replace(",", "").replace(" ", "")
    if "." in cleaned:
        whole, frac = cleaned.split(".", 1)
        return (
            f"{number_to_words(int(whole or 0), lang)} {NUMERALS[lang]['decimal']} "
            f"{_digits_to_words(frac, lang)}"
        )
    return number_to_words(int(cleaned or 0), lang)


# --------------------------------------------------------------------------- #
# Normaliser
# --------------------------------------------------------------------------- #


class TextNormalizer:
    """Normalise Indian-language text for TTS."""

    def __init__(self, lang: str = "hi"):
        self.lang = resolve_lang(lang)
        if self.lang not in NUMERALS:  # pragma: no cover - guarded by resolve_lang
            raise ValueError(f"No numeral table for {self.lang}")

    # -- individual rules --------------------------------------------------- #

    def _expand_currency(self, text: str) -> str:
        rupee = NUMERALS[self.lang]["rupee"]

        def _fmt(raw: str) -> str:
            return f"{number_string_to_words(raw, self.lang)} {rupee}"

        text = _CURRENCY_RE.sub(lambda m: _fmt(m.group(1)), text)
        return _AMOUNT_RE.sub(lambda m: _fmt(m.group(1)), text)

    def _expand_abbreviations(self, text: str) -> str:
        for abbr, expansion in ABBREVIATIONS.get(self.lang, {}).items():
            pattern = re.escape(abbr) if not abbr.isascii() else r"\b" + re.escape(abbr)
            flags = 0 if not abbr.isascii() else re.IGNORECASE
            text = re.sub(pattern, expansion, text, flags=flags)
        return text

    def _expand_dates(self, text: str) -> str:
        months = MONTHS[self.lang]

        def _fmt(day: int, month: int, year: int) -> str:
            if not (1 <= month <= 12) or not (1 <= day <= 31):
                return ""
            return (
                f"{number_to_words(day, self.lang)} {months[month - 1]} "
                f"{number_to_words(year, self.lang)}"
            )

        def _dmy(m: re.Match) -> str:
            return _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3))) or m.group(0)

        def _iso(m: re.Match) -> str:
            return _fmt(int(m.group(3)), int(m.group(2)), int(m.group(1))) or m.group(0)

        text = _DATE_ISO_RE.sub(_iso, text)
        return _DATE_DMY_RE.sub(_dmy, text)

    def _expand_phones(self, text: str) -> str:
        return _PHONE_RE.sub(lambda m: _digits_to_words(m.group(1), self.lang), text)

    def _expand_upi(self, text: str) -> str:
        """``ravi.kumar@okhdfc`` -> ``ravi kumar at o k h d f c``."""
        at_word = {"en": "at"}.get(self.lang, "at")

        def _fmt(m: re.Match) -> str:
            local, handle = m.group(1), m.group(2)
            spoken_local = " ".join(part for part in re.split(r"[._-]+", local) if part)
            spoken_handle = " ".join(handle)
            return f"{spoken_local} {at_word} {spoken_handle}"

        return _UPI_RE.sub(_fmt, text)

    def _expand_codes(self, text: str) -> str:
        """OTPs and zero-prefixed codes: digit by digit, with pauses."""
        paused = lambda m: _digits_to_words(m.group(0), self.lang, paused=True)  # noqa: E731
        text = _LEADING_ZERO_RE.sub(paused, text)
        if _OTP_HINT_RE.search(text):
            text = re.sub(r"\b\d{4,8}\b", paused, text)
        return text

    def _expand_leftover_numbers(self, text: str) -> str:
        return _NUMBER_RE.sub(lambda m: number_string_to_words(m.group(0), self.lang), text)

    # -- public API --------------------------------------------------------- #

    def normalize(self, text: str) -> str:
        """Return ``text`` rewritten as spoken words for this language."""
        if not text or not text.strip():
            return ""

        text = unicodedata.normalize("NFC", text)
        normalizer = _INDIC_NORMALIZERS.get(self.lang)
        if normalizer is not None:
            try:
                text = normalizer.normalize(text)
            except Exception:
                pass

        text = re.sub(r"[\u200b-\u200f\u202a-\u202e\ufeff]", "", text)
        conj = NUMERALS[self.lang]["and"]
        text = text.replace("&", f" {conj} ")
        text = re.sub(r"[*_`#>|]+", " ", text)          # stray markdown
        text = re.sub(r"\s+", " ", text).strip()

        # currency first: it consumes "Rs." itself, so abbreviations cannot eat it
        text = self._expand_currency(text)
        text = self._expand_abbreviations(text)
        text = self._expand_dates(text)
        text = self._expand_upi(text)
        text = self._expand_phones(text)
        text = self._expand_codes(text)
        text = self._expand_leftover_numbers(text)

        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\s+([।,.!?])", r"\1", text)
        return text.strip()

    def split_sentences(self, text: str) -> list[str]:
        out: list[str] = []
        start = 0
        for end in _sentence_ends(text):
            chunk = text[start:end].strip()
            if chunk:
                out.append(chunk)
            start = end
        tail = text[start:].strip()
        if tail:
            out.append(tail)
        return _merge_short(out)


class SentenceSplitter:
    """Incremental splitter for token streams coming out of an LLM."""

    def __init__(self, lang: str = "hi", min_chars: int = 6):
        self.lang = resolve_lang(lang)
        self.min_chars = min_chars
        self._buffer = ""

    def feed(self, delta: str) -> list[str]:
        self._buffer += delta
        sentences: list[str] = []
        last_end = 0
        for end in _sentence_ends(self._buffer):
            chunk = self._buffer[last_end:end].strip()
            if len(chunk) >= self.min_chars:
                sentences.append(chunk)
                last_end = end
        if last_end:
            self._buffer = self._buffer[last_end:]
        return sentences

    def flush(self) -> list[str]:
        tail = self._buffer.strip()
        self._buffer = ""
        return [tail] if tail else []


# --------------------------------------------------------------------------- #
# Sentence boundary detection
# --------------------------------------------------------------------------- #


def _is_abbreviation(text: str, index: int) -> bool:
    for mapping in ABBREVIATIONS.values():
        for abbr in mapping:
            if not abbr.endswith("."):
                continue
            start = index - len(abbr) + 1
            if start >= 0 and text[start:index + 1].lower() == abbr.lower():
                return True
    return False


def _sentence_ends(text: str) -> Iterator[int]:
    length = len(text)
    for i, ch in enumerate(text):
        if ch not in _TERMINATORS:
            continue
        nxt = text[i + 1] if i + 1 < length else ""
        prev = text[i - 1] if i else ""
        if ch == ".":
            if prev.isdigit() and nxt.isdigit():   # 3.5 must not split
                continue
            if _is_abbreviation(text, i):
                continue
        if nxt and nxt not in " \t\n\u201c\u2018\"'":
            continue
        end = i + 1
        while end < length and text[end] in " \t\n.,!?।":
            if text[end] in _TERMINATORS:
                end += 1
                continue
            break
        yield end


def _merge_short(sentences: list[str], min_chars: int = 3) -> list[str]:
    merged: list[str] = []
    for sentence in sentences:
        if merged and len(sentence) < min_chars:
            merged[-1] = f"{merged[-1]} {sentence}"
        elif merged and len(merged[-1]) < min_chars:
            merged[-1] = f"{merged[-1]} {sentence}"
        else:
            merged.append(sentence)
    return merged
