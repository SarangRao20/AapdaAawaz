"""Text normalisation, clause-aware tokenisation and keyword matching.

Keyword syntax (shared by the lexicon and the simulated gazetteer):
  * ``word``   – the token must equal ``word`` exactly (after normalisation)
  * ``word*``  – the token must start with ``word`` (allows Marathi/Hindi case suffixes)
  * multi-word keywords must match consecutive tokens inside one clause.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

_DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_CLAUSE_SPLIT = re.compile(r"[।॥.!?;:,\n]+|…")
_TOKEN_RE = re.compile(r"[^\s\-–—/()\[\]{}\"'“”‘’…|]+")
_RANGE_RE = re.compile(r"(\d+)\s*[-–]\s*(\d+)")
_EDGE_PUNCT = "।॥.,!?;:\"'“”‘’()[]{}"


def normalize(text: str) -> str:
    """Normalise for matching: NFC, digits to ASCII, lower-case, nukta/chandrabindu folded."""
    t = unicodedata.normalize("NFC", text)
    t = unicodedata.normalize("NFD", t)  # split precomposed nukta letters (U+0958..U+095F)
    t = t.replace("़", "")          # drop nukta: ड़ -> ड, ढ़ -> ढ
    t = unicodedata.normalize("NFC", t)
    t = t.replace("ँ", "ं")    # chandrabindu -> anusvara
    t = t.translate(_DEV_DIGITS)
    return t.lower()


@dataclass(frozen=True)
class Token:
    norm: str
    orig: str
    clause: int
    idx: int


def tokenize(text: str) -> list[Token]:
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\[[^\]]*\]", " ", text)          # drop [noise] style markers
    text = _RANGE_RE.sub(r"\1 to \2", text)          # "20-25" -> "20 to 25"
    tokens: list[Token] = []
    for c_idx, clause in enumerate(_CLAUSE_SPLIT.split(text)):
        for m in _TOKEN_RE.finditer(clause):
            orig = m.group(0).strip(_EDGE_PUNCT)
            if not orig:
                continue
            tokens.append(Token(norm=normalize(orig), orig=orig, clause=c_idx, idx=len(tokens)))
    return tokens


def is_devanagari(ch: str) -> bool:
    return "ऀ" <= ch <= "ॿ"


@dataclass(frozen=True)
class Keyword:
    raw: str
    parts: tuple[tuple[str, bool], ...]  # (stem, is_prefix)


@lru_cache(maxsize=4096)
def compile_keyword(raw: str) -> Keyword:
    parts = []
    for piece in raw.split():
        prefix = piece.endswith("*")
        stem = normalize(piece.rstrip("*"))
        parts.append((stem, prefix))
    return Keyword(raw=raw, parts=tuple(parts))


def _token_matches(tok: str, stem: str, prefix: bool) -> bool:
    return tok.startswith(stem) if prefix else tok == stem


@dataclass(frozen=True)
class Match:
    keyword: str
    start: int
    end: int  # exclusive
    text: str


def find_keyword(tokens: list[Token], raw: str) -> list[Match]:
    kw = compile_keyword(raw)
    n = len(kw.parts)
    out: list[Match] = []
    for i in range(len(tokens) - n + 1):
        clause = tokens[i].clause
        ok = True
        for j, (stem, prefix) in enumerate(kw.parts):
            t = tokens[i + j]
            if t.clause != clause or not _token_matches(t.norm, stem, prefix):
                ok = False
                break
        if ok:
            out.append(Match(raw, i, i + n, " ".join(t.orig for t in tokens[i:i + n])))
    return out


def find_any(tokens: list[Token], keywords: list[str]) -> list[Match]:
    seen: set[tuple[int, int]] = set()
    out: list[Match] = []
    for raw in keywords:
        for m in find_keyword(tokens, raw):
            if (m.start, m.end) not in seen:
                seen.add((m.start, m.end))
                out.append(m)
    out.sort(key=lambda m: m.start)
    return out


NEGATORS_AFTER = {normalize(w) for w in ("नाही", "नाहीत", "नहीं", "नही", "nahi", "nahin", "nahee", "not")}
NEGATORS_BEFORE = {normalize(w) for w in ("no", "not", "nobody", "none", "without", "never", "कोणीही")}


def is_negated(tokens: list[Token], m: Match) -> bool:
    clause = tokens[m.start].clause
    for k in range(m.end, min(m.end + 2, len(tokens))):
        if tokens[k].clause != clause:
            break
        if tokens[k].norm in NEGATORS_AFTER:
            return True
    for k in range(m.start - 1, max(m.start - 4, -1), -1):
        if tokens[k].clause != clause:
            break
        if tokens[k].norm in NEGATORS_BEFORE:
            return True
    return False


def char_ngrams(text: str, n: int = 3) -> set[str]:
    t = re.sub(r"\s+", " ", normalize(re.sub(r"\[[^\]]*\]", " ", text))).strip()
    t = re.sub(r"[^\wऀ-ॿ ]", "", t)
    return {t[i:i + n] for i in range(max(len(t) - n + 1, 0))}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
