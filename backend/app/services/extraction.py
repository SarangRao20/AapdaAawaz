"""Deterministic rule-based structured extraction (used because Gnani Evon has no public API).

Design rules
------------
* Unknown stays unknown: ``None`` is never turned into 0 / False / "safe".
* Every extracted value records the transcript text that produced it (``evidence``).
* Coordinates are only copied from the SIMULATED reference gazetteer when exactly one
  reference place is named. Generic landmarks ("the big bridge"), unknown village names,
  or several places never produce coordinates.
* ``confidence`` values are *rule-evidence levels* from the lookup tables below — a
  documented ordinal scale, not calibrated probabilities.
"""
from __future__ import annotations

import re

from ..schemas import (
    Evidence,
    ExtractedLocation,
    ExtractionResult,
    PeopleAffected,
    VulnerableMention,
    VulnerablePeople,
)
from . import lexicon as lx
from .gazetteer import load_gazetteer
from .text_utils import Match, Token, compile_keyword, find_any, is_devanagari, is_negated, normalize, tokenize

PROVIDER_NAME = "rule-based-v1"
PROVIDER_MODE = "rule_based"

# Rule-evidence levels (ordinal, documented in docs/EVALUATION.md).
LOCATION_EVIDENCE = {
    "place_and_landmark": 0.9,
    "place_only": 0.8,
    "landmark_only": 0.5,
    "unmapped": 0.4,
    "possible_match": 0.3,
    "ambiguous": 0.2,
    "conflicting": 0.2,
    "missing": 0.0,
}
PEOPLE_EVIDENCE = {"exact": 0.85, "approximate": 0.7, "range": 0.6, "multiple_counts": 0.6}
LOW_QUALITY_LOCATION_CAP = 0.6
LOW_QUALITY_PEOPLE_CAP = 0.4

LABELS = {
    "rescue_evacuation": "rescue / evacuation", "medical": "medical help", "food": "food",
    "drinking_water": "drinking water", "shelter": "shelter", "fire_services": "fire services",
    "trapped": "people trapped", "surrounded_by_water": "surrounded by water", "on_roof": "people on a roof",
    "water_rising": "water rising", "flooding_inside_home": "water inside homes", "swept_away": "swept away",
    "drowning": "drowning", "structure_collapse": "structure collapse", "under_debris": "person under debris",
    "injured": "injuries", "unconscious": "unconscious / drowsy person", "active_fire": "active fire",
    "missing_person": "missing person", "road_blocked": "road blocked",
    "elderly": "elderly", "children": "children", "infants": "infants", "pregnant_people": "pregnant person",
    "people_with_disabilities": "person with disability / bedridden",
}


def _norm_set(words) -> set[str]:
    return {normalize(w) for w in words}


_NUMBER_WORDS = {normalize(k): v for k, v in lx.NUMBER_WORDS.items()}
_APPROX = _norm_set(lx.APPROXIMATORS)
_VAGUE = _norm_set(lx.VAGUE_QUANTIFIERS)
_RANGE = _norm_set(lx.RANGE_CONNECTORS)
_AGE_UNITS = _norm_set(lx.AGE_UNITS)
_VILLAGE = _norm_set(lx.VILLAGE_WORDS)
_NOT_A_PLACE = _norm_set(lx.NOT_A_PLACE)
_MARKERS = {
    "mr": _norm_set(lx.LANG_MARKERS_MR),
    "hi": _norm_set(lx.LANG_MARKERS_HI),
    "hinglish": _norm_set(lx.LANG_MARKERS_HINGLISH),
    "en": _norm_set(lx.LANG_MARKERS_EN),
}


def _single_token_matcher(keywords: list[str]):
    parts = [compile_keyword(k).parts[0] for k in keywords if len(compile_keyword(k).parts) == 1]

    def match(tok: Token) -> bool:
        return any(tok.norm.startswith(stem) if prefix else tok.norm == stem for stem, prefix in parts)
    return match


_is_people_noun = _single_token_matcher(lx.PEOPLE_NOUNS)
_is_family_noun = _single_token_matcher(lx.FAMILY_NOUNS)
_is_vulnerable_word = _single_token_matcher([k for kws in lx.VULNERABLE_KEYWORDS.values() for k in kws])


def _num(tok: Token) -> int | None:
    if tok.norm.isdigit():
        return int(tok.norm)
    return _NUMBER_WORDS.get(tok.norm)


_EN_TENS = {"twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"}
_EN_UNITS = {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine"}
_HUNDREDS = _norm_set({"hundred", "sau", "सौ"})
_AND = _norm_set({"and", "aur", "और"})


def _under_hundred_at(tokens: list[Token], i: int) -> tuple[int | None, int]:
    """(value, tokens used) for a number below 100; English writes these as two words ("twenty five")."""
    value = _num(tokens[i])
    if value is None or value >= 100:
        return None, 0
    if (tokens[i].norm in _EN_TENS and i + 1 < len(tokens) and tokens[i + 1].clause == tokens[i].clause
            and tokens[i + 1].norm in _EN_UNITS):
        return value + _NUMBER_WORDS[tokens[i + 1].norm], 2
    return value, 1


def _num_at(tokens: list[Token], i: int) -> tuple[int | None, int]:
    """(value, tokens used) for the number starting at token i, including compound forms.

    Parts must share a clause, so "twenty, five people" stays two separate numbers.
    """
    value, used = _under_hundred_at(tokens, i)
    clause = tokens[i].clause

    def in_clause(j: int) -> bool:
        return j < len(tokens) and tokens[j].clause == clause

    if value is not None and in_clause(i + used) and tokens[i + used].norm in _HUNDREDS:
        value, used = value * 100, used + 1
    elif value is None:
        value = _num(tokens[i])
        if value is None:
            return None, 0
        used = 1
    if value >= 100 and value % 100 == 0:
        j = i + used
        if in_clause(j) and tokens[j].norm in _AND:
            j += 1
        # Only words combine: "100 20" is two numbers, "one hundred twenty" is one.
        if in_clause(j) and not tokens[j].norm.isdigit() and not tokens[i + used - 1].norm.isdigit():
            rest, rest_used = _under_hundred_at(tokens, j)
            if rest is not None:
                return value + rest, j + rest_used - i
    return value, used


def _split_hits(tokens: list[Token], keywords: list[str], negatable: bool = True) -> tuple[list[Match], list[Match]]:
    pos, neg = [], []
    for m in find_any(tokens, keywords):
        (neg if negatable and is_negated(tokens, m) else pos).append(m)
    return pos, neg


# ---------------------------------------------------------------------------
# individual extractors
# ---------------------------------------------------------------------------
def assess_quality(transcript: str, tokens: list[Token]) -> tuple[str, str]:
    markers = len(re.findall(lx.QUALITY_MARKER_RE, transcript, flags=re.IGNORECASE))
    ellipses = transcript.count("...") + transcript.count("…")
    reasons = []
    if markers:
        reasons.append(f"{markers} inaudible/noise marker(s) in transcript")
    if ellipses >= 3:
        reasons.append(f"{ellipses} gaps ('...') in transcript")
    if len(tokens) < 5:
        reasons.append(f"very short transcript ({len(tokens)} words)")
    if reasons:
        return "low", "; ".join(reasons)
    return "ok", "no inaudible markers or gaps; transcript has complete sentences"


def detect_language(tokens: list[Token], hint: str | None) -> tuple[str, str]:
    dev = [t for t in tokens if any(is_devanagari(c) for c in t.orig)]
    lat = [t for t in tokens if t.orig[:1].isascii() and t.orig[:1].isalpha()]
    total = len(dev) + len(lat)
    if total == 0:
        return (hint or "unknown"), "no words to analyse; used language hint" if hint else "no words to analyse"
    if dev and lat and min(len(dev), len(lat)) / total >= 0.25:
        return "mixed", f"{len(dev)} Devanagari and {len(lat)} Latin-script words"
    if len(dev) >= len(lat):
        mr = sum(t.norm in _MARKERS["mr"] for t in dev)
        hi = sum(t.norm in _MARKERS["hi"] for t in dev)
        if mr > hi:
            return "mr", f"Devanagari script; {mr} Marathi vs {hi} Hindi function words"
        if hi > mr:
            return "hi", f"Devanagari script; {hi} Hindi vs {mr} Marathi function words"
        if hint in ("mr", "hi"):
            return hint, "Devanagari script; Marathi/Hindi markers tied, used language hint"
        if mr == 0 and hi == 0 and hint:
            return hint, f"Devanagari script; no language markers found (possibly transliterated {hint}), used language hint"
        return "unknown", "Devanagari script; could not tell Marathi from Hindi"
    hinglish = sum(t.norm in _MARKERS["hinglish"] for t in lat)
    en = sum(t.norm in _MARKERS["en"] for t in lat)
    if hinglish > en:
        return "mixed", f"Latin script; {hinglish} romanised Hindi vs {en} English function words (Hinglish)"
    if en > hinglish:
        return "en", f"Latin script; {en} English vs {hinglish} romanised Hindi function words"
    if hint in ("en", "mixed"):
        return hint, "Latin script; markers tied, used language hint"
    return "unknown", "Latin script; could not tell English from Hinglish"


def _disaster(tokens: list[Token], ev: list[Evidence], unc: list[str]) -> tuple[str, list[str], str]:
    found: dict[str, list[Match]] = {}
    for dtype, kws in lx.DISASTER_KEYWORDS.items():
        pos, _ = _split_hits(tokens, kws)
        if pos:
            found[dtype] = pos
    if not found:
        return "unknown", [], "no hazard keyword found"
    for dtype, ms in found.items():
        ev.extend(Evidence(field="disaster_type", text=m.text) for m in ms[:2])
    order = [d for d in lx.DISASTER_TIEBREAK if d in found]
    chosen = order[0]
    if len(order) > 1:
        unc.append(f"Several hazards mentioned ({', '.join(order)}); using '{chosen}'")
    return chosen, order, f"hazard keyword(s): {', '.join(m.text for m in found[chosen][:3])}"


def _dangers(tokens: list[Token], ev: list[Evidence]) -> list[str]:
    out = []
    for dtype, kws in lx.DANGER_KEYWORDS.items():
        pos, neg = _split_hits(tokens, kws)
        if pos:
            out.append(dtype)
            ev.extend(Evidence(field=f"danger.{dtype}", text=m.text) for m in pos[:2])
        for m in neg[:1]:
            ev.append(Evidence(field=f"danger.{dtype}", text=m.text, negated=True))
    return out


def _numbers_near(tokens: list[Token], idx: int) -> int | None:
    """A number directly before a word (e.g. 'do buzurg', 'two elderly')."""
    if idx > 0 and tokens[idx - 1].clause == tokens[idx].clause:
        for back in range(min(idx, 4), 1, -1):  # longest compound first: "two hundred fifty", "twenty five"
            start = idx - back
            if tokens[start].clause == tokens[idx].clause:
                value, used = _num_at(tokens, start)
                if value is not None and used == back:
                    return value
        return _num(tokens[idx - 1])
    return None


def _people_and_ages(tokens: list[Token], ev: list[Evidence], unc: list[str], quality: str
                     ) -> tuple[PeopleAffected, list[tuple[int, str]]]:
    counts: list[dict] = []
    ages: list[tuple[int, str]] = []
    families: int | None = None
    vague_text: str | None = None
    n = len(tokens)
    i = 0
    while i < n:
        tok = tokens[i]
        if tok.norm in _VAGUE:
            for k in range(i + 1, min(i + 3, n)):
                if tokens[k].clause != tok.clause:
                    break
                if _is_people_noun(tokens[k]):
                    vague_text = " ".join(t.orig for t in tokens[i:k + 1])
                    break
        value, used = _num_at(tokens, i)
        if value is None:
            i += 1
            continue
        start, low = i, None
        i += used - 1  # now on the last token of the number
        upper, upper_used = (_num_at(tokens, i + 2) if i + 2 < n and tokens[i + 2].clause == tok.clause
                             else (None, 0))
        if i + 2 < n and tokens[i + 1].norm in _RANGE and upper is not None:
            low, value = value, upper
            i += 1 + upper_used
        # "N से ज्यादा / more than N" → treat as approximate count equal to N
        elif (i + 2 < n and tokens[i + 1].norm in _RANGE and tokens[i + 2].clause == tok.clause
              and tokens[i + 2].norm in _APPROX):
            # skip the "से ज्यादा / se zyada / more than" token — value stays at N, mark approx
            i += 2
        via_vulnerable = False
        for k in range(i + 1, min(i + 4, n)):
            t = tokens[k]
            if t.clause != tok.clause:
                break
            if t.norm in _AGE_UNITS:
                ages.append((value, " ".join(x.orig for x in tokens[start:k + 1])))
                break
            if _is_family_noun(t):
                families = value
                ev.append(Evidence(field="people_affected.families", text=" ".join(x.orig for x in tokens[start:k + 1])))
                break
            if _is_people_noun(t):
                text = " ".join(x.orig for x in tokens[max(start - 1, 0):k + 1])
                approx = (start > 0 and tokens[start - 1].norm in _APPROX) or any(
                    tokens[j].norm in _APPROX for j in range(k + 1, min(k + 3, n)) if tokens[j].clause == tok.clause)
                if not via_vulnerable:
                    counts.append({"value": value, "low": low, "approx": approx, "text": text})
                break
            if _is_vulnerable_word(t):
                via_vulnerable = True  # "two elderly people" counts a sub-group, not everyone
            elif k > i + 1:
                break
        i += 1

    people = PeopleAffected(families=families)
    if counts:
        distinct = sorted({c["value"] for c in counts})
        best = max(counts, key=lambda c: c["value"])
        people.count = best["value"]
        people.all_counts_mentioned = distinct
        people.approximate = best["approx"] or best["low"] is not None
        if best["low"] is not None:
            people.range = [best["low"], best["value"]]
        for c in counts:
            ev.append(Evidence(field="people_affected.count", text=c["text"]))
        if len(distinct) > 1:
            kind = "multiple_counts"
            people.confidence_basis = (f"several counts stated ({', '.join(map(str, distinct))}); "
                                       f"using the largest ({best['value']})")
            unc.append(people.confidence_basis)
        elif best["low"] is not None:
            kind = "range"
            people.confidence_basis = f"range stated ('{best['text']}'); using the upper bound"
        elif best["approx"]:
            kind = "approximate"
            people.confidence_basis = f"approximate count stated ('{best['text']}')"
        else:
            kind = "exact"
            people.confidence_basis = f"explicit count stated ('{best['text']}')"
        people.confidence = PEOPLE_EVIDENCE[kind]
        if quality == "low":
            people.confidence = min(people.confidence, LOW_QUALITY_PEOPLE_CAP)
            people.confidence_basis += "; capped because the transcript is low quality"
    else:
        if families is not None:
            people.confidence_basis = f"{families} families stated; number of people not stated"
            unc.append(f"{families} families mentioned — number of people is unknown (families are not converted)")
        elif vague_text:
            people.confidence_basis = f"only a vague quantity stated ('{vague_text}')"
            unc.append(f"Vague quantity '{vague_text}' — number of people is unknown")
        else:
            unc.append("Number of people affected was not stated")
    return people, ages


def _vulnerable(tokens: list[Token], ev: list[Evidence], ages: list[tuple[int, str]]) -> VulnerablePeople:
    vp = VulnerablePeople()
    for group, kws in lx.VULNERABLE_KEYWORDS.items():
        pos, neg = _split_hits(tokens, kws)
        for m in neg[:1]:
            ev.append(Evidence(field=f"vulnerable.{group}", text=m.text, negated=True))
        if not pos:
            continue
        count = None
        for m in pos:
            c = _numbers_near(tokens, m.start)
            if c is not None and c < 1000:
                count = max(count or 0, c)
        setattr(vp, group, VulnerableMention(count=count, evidence=pos[0].text))
        ev.extend(Evidence(field=f"vulnerable.{group}", text=m.text) for m in pos[:2])
    for age, text in ages:
        group = "elderly" if age >= 60 else "children" if age <= 12 else None
        if group and getattr(vp, group) is None:
            setattr(vp, group, VulnerableMention(count=None, evidence=f"age stated: {text}"))
            ev.append(Evidence(field=f"vulnerable.{group}", text=text))
    return vp


def _needs(tokens: list[Token], ev: list[Evidence]) -> list[str]:
    # No negation here: "दवाई नहीं मिली" (didn't get medicine) still expresses a need.
    out = []
    for need, kws in lx.NEED_KEYWORDS.items():
        pos, _ = _split_hits(tokens, kws, negatable=False)
        if pos:
            out.append(need)
            ev.extend(Evidence(field=f"need.{need}", text=m.text) for m in pos[:2])
    return out


def _urgency(tokens: list[Token], ev: list[Evidence]) -> tuple[str, str]:
    for level in ("critical", "high", "low", "medium"):
        pos, _ = _split_hits(tokens, lx.URGENCY_KEYWORDS[level])
        if pos:
            ev.append(Evidence(field="urgency", text=pos[0].text))
            return level, f"caller said '{pos[0].text}'"
    return "unknown", "caller did not express urgency explicitly"


def _status(tokens: list[Token], ev: list[Evidence]) -> list[str]:
    out = []
    for status, kws in lx.STATUS_KEYWORDS.items():
        pos, _ = _split_hits(tokens, kws)
        if pos:
            out.append(status)
            ev.append(Evidence(field=f"status.{status}", text=pos[0].text))
    return out


def _location(tokens: list[Token], ev: list[Evidence], unc: list[str], quality: str) -> ExtractedLocation:
    gz = load_gazetteer()
    place_hits: dict[str, list[Match]] = {}
    for p in gz.places.values():
        ms = find_any(tokens, list(p.aliases))
        if ms:
            place_hits[p.id] = ms
    type_hits: dict[str, list[Match]] = {}
    for ltype, kws in gz.landmark_types.items():
        ms = find_any(tokens, list(kws))
        if ms:
            type_hits[ltype] = ms
    specific_hits: dict[str, list[Match]] = {}
    for lm in gz.landmarks.values():
        if lm.specific_aliases:
            ms = find_any(tokens, list(lm.specific_aliases))
            if ms:
                specific_hits[lm.id] = ms

    stated = [m.text for ms in place_hits.values() for m in ms[:1]]
    stated += [m.text for ms in specific_hits.values() for m in ms[:1]]
    stated += [m.text for ms in type_hits.values() for m in ms[:1]]
    for t in stated:
        ev.append(Evidence(field="location", text=t))
    landmark_text = next((ms[0].text for ms in type_hits.values()), None)
    ltypes = sorted(set(type_hits) | {gz.landmarks[lid].type for lid in specific_hits})
    loc = ExtractedLocation(stated_text=stated, landmark_types=ltypes)

    # When a state and a city/place in that state are both mentioned, drop the state entry
    # so a specific city takes precedence (e.g. "Ahmedabad Gujarat" → Ahmedabad).
    if len(place_hits) > 1:
        non_state = {pid: ms for pid, ms in place_hits.items() if gz.places[pid].type != "state"}
        if non_state:
            place_hits = non_state

    if len(place_hits) == 1:
        pid = next(iter(place_hits))
        place = gz.places[pid]
        lm = next((gz.landmarks[lid] for lid in specific_hits if gz.landmarks[lid].place_id == pid), None)
        if lm is None:
            lm = next((x for x in gz.landmarks.values() if x.place_id == pid and x.type in type_hits), None)
        loc.place_name, loc.place_id = place.name, pid
        loc.district, loc.state = gz.district, gz.state
        loc.latitude, loc.longitude = place.latitude, place.longitude
        loc.source, loc.status = "simulated", "grounded"
        basis = f"place '{place_hits[pid][0].text}' matched simulated reference {pid} ({place.name})"
        if lm is not None:
            loc.landmark, loc.landmark_id = lm.name, lm.id
            loc.confidence = LOCATION_EVIDENCE["place_and_landmark"]
            basis += f"; landmark matched reference {lm.id} ({lm.name})"
        else:
            loc.confidence = LOCATION_EVIDENCE["place_only"]
            if landmark_text:
                loc.landmark = landmark_text
                unc.append(f"Landmark '{landmark_text}' is not in the reference list for {place.name}")
        loc.confidence_basis = basis + "; coordinates are the SIMULATED village reference point, not the exact spot"
        if quality == "low":
            loc.confidence = min(loc.confidence, LOW_QUALITY_LOCATION_CAP)
            loc.confidence_basis += "; capped because the transcript is low quality"
        return loc

    if len(place_hits) > 1:
        names = [gz.places[p].name for p in place_hits]
        loc.status, loc.source = "conflicting", "caller_stated"
        loc.candidates = list(place_hits)
        loc.landmark = landmark_text
        loc.confidence = LOCATION_EVIDENCE["conflicting"]
        loc.confidence_basis = f"several reference places mentioned ({', '.join(names)})"
        unc.append(f"Several places mentioned ({', '.join(names)}); the incident location is unclear")
        return loc

    if specific_hits:
        lid = next(iter(specific_hits))
        lm = gz.landmarks[lid]
        loc.status, loc.source = "landmark_only", "caller_stated"
        loc.landmark, loc.candidates = lm.name, [lm.place_id]
        loc.confidence = LOCATION_EVIDENCE["landmark_only"]
        loc.confidence_basis = f"only a landmark was named ('{specific_hits[lid][0].text}'); village not stated"
        unc.append(f"Only a landmark was named ('{specific_hits[lid][0].text}'); village not confirmed")
        return loc

    possible = _possible_village(tokens)
    if possible:
        pid, heard = possible
        # A guess must not drop a pin or pass as verified: stay ambiguous so a person confirms it.
        loc.status, loc.source = "ambiguous", "caller_stated"
        loc.place_name, loc.landmark, loc.candidates = heard, landmark_text, [pid]
        loc.confidence = LOCATION_EVIDENCE["possible_match"]
        loc.confidence_basis = (f"heard '{heard}', which may be a misheard '{gz.places[pid].name}'; "
                                "not confirmed, so no coordinates assigned")
        unc.append(f"'{heard}' may be a misheard '{gz.places[pid].name}'; confirm the place with the caller")
        ev.append(Evidence(field="location", text=heard))
        return loc

    unmapped = _unmapped_place(tokens)
    if unmapped:
        from ..config import settings
        if settings.geocoding_enabled:
            from .geocoder import nominatim_geocode
            hit = nominatim_geocode(unmapped)
            if hit is not None:
                lat, lon, osm_id = hit
                loc.place_name, loc.landmark = unmapped, landmark_text
                loc.latitude, loc.longitude = lat, lon
                loc.place_id = osm_id
                loc.source, loc.status = "verified_reference", "grounded"
                loc.confidence = LOCATION_EVIDENCE["unmapped"] + 0.25
                loc.confidence_basis = (
                    f"caller named '{unmapped}'; geocoded via Nominatim/OSM (India) — "
                    "coordinates are the OSM centroid, not the exact incident site"
                )
                ev.append(Evidence(field="location", text=unmapped))
                return loc
        loc.status, loc.source = "unmapped", "caller_stated"
        loc.place_name, loc.landmark = unmapped, landmark_text
        loc.confidence = LOCATION_EVIDENCE["unmapped"]
        loc.confidence_basis = f"caller named '{unmapped}', which is not in the simulated reference dataset"
        unc.append(f"Place '{unmapped}' is not in the reference dataset; no coordinates assigned")
        ev.append(Evidence(field="location", text=unmapped))
        return loc

    if type_hits:
        cands = sorted({lm.place_id for lm in gz.landmarks.values() if lm.type in type_hits})
        loc.status, loc.source = "ambiguous", "caller_stated"
        loc.landmark, loc.candidates = landmark_text, cands
        loc.confidence = LOCATION_EVIDENCE["ambiguous"]
        loc.confidence_basis = (f"only a generic landmark was named ('{landmark_text}'); "
                                f"{len(cands)} reference places have one")
        unc.append(f"Location ambiguous: generic landmark '{landmark_text}' without a village name "
                   f"({len(cands)} possible reference places)")
        return loc

    loc.confidence_basis = "no place or landmark found in the transcript"
    unc.append("No location was stated")
    return loc


def _within_one_edit(a: str, b: str) -> bool:
    """True when a and b differ by at most one inserted, removed or replaced character."""
    if abs(len(a) - len(b)) > 1:
        return False
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    if len(a) == len(b):
        return a[i + 1:] == b[i + 1:]
    return (a[i + 1:] == b[i:]) if len(a) > len(b) else (a[i:] == b[i + 1:])


def _possible_village(tokens: list[Token]) -> tuple[str, str] | None:
    """(place id, heard word) when one word is a single character away from exactly one reference village.

    Limited to the villages (the places that have landmarks) and to names of 6+ characters: speech
    recognition garbles unfamiliar village names, while loosening matches on city aliases causes real
    errors, e.g. "madrasa" (a school) is one letter from "Madras". The first character must match.
    """
    gz = load_gazetteer()
    village_ids = {lm.place_id for lm in gz.landmarks.values()}
    found: dict[str, str] = {}
    for tok in tokens:
        if len(tok.norm) < 6 or tok.norm in _VILLAGE or tok.norm in _NOT_A_PLACE:
            continue
        for pid in village_ids:
            for alias in gz.places[pid].aliases:
                parts = compile_keyword(alias).parts
                if len(parts) != 1 or len(parts[0][0]) < 6 or parts[0][0][0] != tok.norm[0]:
                    continue
                stem, prefix = parts[0]
                # Prefix aliases allow case suffixes (-त, -मध्ये), so compare only the start of the word.
                variants = ([tok.norm[:len(stem) + d] for d in (-1, 0, 1)] if prefix else [tok.norm])
                if any(_within_one_edit(v, stem) for v in variants):
                    found.setdefault(pid, tok.orig)
    return next(iter(found.items())) if len(found) == 1 else None


def _unmapped_place(tokens: list[Token]) -> str | None:
    """'Kesarwadi gaon' -> 'Kesarwadi': a word directly before a 'village' word."""
    for i, tok in enumerate(tokens):
        if tok.norm in _VILLAGE and i > 0:
            prev = tokens[i - 1]
            if (prev.clause == tok.clause and prev.norm not in _NOT_A_PLACE and _num(prev) is None
                    and len(prev.norm) >= 3 and prev.norm not in _VILLAGE):
                return prev.orig
    return None


def _summary(r: ExtractionResult) -> str:
    loc = r.location
    if loc.status == "grounded":
        where = loc.place_name + (f", near {loc.landmark}" if loc.landmark else "")
    elif loc.status == "unmapped":
        where = f"'{loc.place_name}' (not in reference data)"
    elif loc.status in ("ambiguous", "landmark_only") and loc.landmark:
        where = f"near '{loc.landmark}' (village unclear)"
    elif loc.status == "conflicting":
        where = "an unclear location (several places named)"
    else:
        where = "an unstated location"
    if r.disaster_type != "unknown":
        parts = [f"{r.disaster_type.capitalize()} reported at {where}."]
    else:
        parts = [f"Report from {where} (hazard type not stated)."]
    pa = r.people_affected
    if pa.count is not None:
        parts.append(f"{'About ' if pa.approximate else ''}{pa.count} people reported.")
    elif pa.families is not None:
        parts.append(f"{pa.families} families reported (number of people not stated).")
    else:
        parts.append("Number of people not stated.")
    vul = r.vulnerable_people.mentioned()
    if vul:
        parts.append("Vulnerable: " + ", ".join(LABELS[v] for v in vul) + ".")
    if r.reported_danger:
        parts.append("Dangers: " + ", ".join(LABELS[d] for d in r.reported_danger) + ".")
    if r.medical_emergency:
        parts.append("Medical emergency described.")
    if r.immediate_needs:
        parts.append("Needs: " + ", ".join(LABELS[n] for n in r.immediate_needs) + ".")
    if "reported_safe" in r.status_claims or "reported_evacuated" in r.status_claims:
        parts.append("Caller says people are currently safe/evacuated.")
    return " ".join(parts)


def extract(transcript: str, language_hint: str | None = None) -> ExtractionResult:
    tokens = tokenize(transcript)
    ev: list[Evidence] = []
    unc: list[str] = []

    quality, quality_basis = assess_quality(transcript, tokens)
    if quality == "low":
        unc.append(f"Low-quality transcript: {quality_basis}")
    language, _lang_basis = detect_language(tokens, language_hint)
    disaster, mentioned, disaster_basis = _disaster(tokens, ev, unc)
    dangers = _dangers(tokens, ev)
    people, ages = _people_and_ages(tokens, ev, unc, quality)
    vulnerable = _vulnerable(tokens, ev, ages)
    needs = _needs(tokens, ev)

    med_pos, _ = _split_hits(tokens, lx.MEDICAL_EMERGENCY_KEYWORDS)
    med_emergency = True if med_pos else None
    ev.extend(Evidence(field="medical_emergency", text=m.text) for m in med_pos[:2])
    crit_pos, _ = _split_hits(tokens, lx.CRITICAL_MEDICATION_KEYWORDS, negatable=False)
    critical_medication = True if crit_pos else None
    medical_need = True if "medical" in needs else None

    urgency, urgency_basis = _urgency(tokens, ev)
    status = _status(tokens, ev)
    location = _location(tokens, ev, unc, quality)

    # Precautionary: a fragmentary low-quality transcript that still contains a disaster
    # keyword warrants a minimum "medium" urgency — the call may be worse than it sounds.
    # Post-processing: if evacuation is confirmed, remove dangers/needs triggered by
    # past-tense rescue verbs (e.g. "छतावरून बाहेर काढले" = "rescued from roof").
    POSITIONAL_RESOLVED = {"on_roof", "trapped", "surrounded_by_water"}
    if "reported_evacuated" in status:
        dangers = [d for d in dangers if d not in POSITIONAL_RESOLVED]
        needs = [n for n in needs if n != "rescue_evacuation"]

    if urgency == "unknown" and quality == "low" and disaster != "unknown":
        urgency = "medium"
        urgency_basis = "precautionary: low-quality transcript with disaster signal — assume medium urgency"
        unc.append("Urgency assumed medium: fragmentary transcript with disaster keyword (precautionary)")

    if urgency == "unknown":
        unc.append("Caller did not express urgency explicitly")
    if status and set(dangers) & lx.LIFE_THREAT_DANGERS:
        unc.append("Report says people are safe but also describes a threat to life")

    result = ExtractionResult(
        disaster_type=disaster,
        disaster_types_mentioned=mentioned,
        disaster_basis=disaster_basis,
        location=location,
        people_affected=people,
        vulnerable_people=vulnerable,
        immediate_needs=needs,
        reported_danger=dangers,
        medical_emergency=med_emergency,
        medical_need=medical_need,
        critical_medication=critical_medication,
        urgency=urgency,
        urgency_basis=urgency_basis,
        status_claims=status,
        language=language,
        transcript_quality=quality,
        transcript_quality_basis=quality_basis,
        uncertainties=unc,
        requires_human_review=bool(unc),
        evidence=ev,
        provider=PROVIDER_NAME,
        provider_mode=PROVIDER_MODE,
    )
    result.summary = _summary(result)
    # Round-trip through the model so every field is validated before it is stored.
    return ExtractionResult.model_validate(result.model_dump())
