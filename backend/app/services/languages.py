"""The languages Aapda Awaaz speaks and understands.

Four core languages (hi, mr, en, and Hinglish "mixed") have hand-built fact extraction. Seven more
(bn, gu, kn, ml, pa, ta, te) are served end to end by Gnani Prisma (speech-to-text) and Timbre
(text-to-speech): their prompts, questions and safety alerts are fixed text written in advance, and
facts are read from a machine translation of the transcript, which always asks for human review.
"""
from __future__ import annotations

CORE = ("hi", "mr", "en", "mixed")
EXTRA = ("bn", "gu", "kn", "ml", "pa", "ta", "te")
ALL = CORE + EXTRA

LABELS = {
    "hi": "Hindi", "mr": "Marathi", "en": "English", "mixed": "Hinglish",
    "bn": "Bengali", "gu": "Gujarati", "kn": "Kannada", "ml": "Malayalam",
    "pa": "Punjabi", "ta": "Tamil", "te": "Telugu",
}
NATIVE = {
    "hi": "हिंदी", "mr": "मराठी", "en": "English", "mixed": "Hinglish",
    "bn": "বাংলা", "gu": "ગુજરાતી", "kn": "ಕನ್ನಡ", "ml": "മലയാളം",
    "pa": "ਪੰਜਾਬੀ", "ta": "தமிழ்", "te": "తెలుగు",
}

# Prisma and Timbre both name these "<code>-IN". Hinglish has no code of its own on either side.
PRISMA_CODES = {"mr": "mr-IN", "hi": "hi-IN", "en": "en-IN", "mixed": "hi-IN", **{c: f"{c}-IN" for c in EXTRA}}
TIMBRE_CODES = {"mr": "mr-IN", "hi": "hi-IN", "en": "en-IN", "mixed": "hi-en", **{c: f"{c}-IN" for c in EXTRA}}


def is_extra(language: str | None) -> bool:
    return language in EXTRA
