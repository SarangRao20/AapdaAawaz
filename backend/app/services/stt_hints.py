"""Words Prisma v3 should expect in a disaster call, sent as `keyterms`.

Prisma v3 accepts up to 200 terms. Village names are what a caller most needs heard correctly, and they
are the words a general speech model is least likely to know, so they come first.
"""
from __future__ import annotations

from functools import lru_cache

from .gazetteer import load_gazetteer

MAX_KEYTERMS = 200

DISASTER_TERMS = [
    "baadh", "बाढ़", "पूर", "भूकंप", "bhukamp", "भूस्खलन", "दरड", "aag", "आग",
    "flood", "landslide", "earthquake", "fire", "cyclone", "तूफान",
    "phanse", "फंसे", "अडकले", "madad", "मदद", "मदत", "बचाओ", "वाचवा",
    "ambulance", "rescue", "zilla parishad", "जिल्हा परिषद",
]


@lru_cache(maxsize=1)
def disaster_keyterms() -> tuple[str, ...]:
    terms: list[str] = []
    for place in load_gazetteer().places.values():
        terms += [place.name, place.name_local]
    terms += DISASTER_TERMS
    # dict.fromkeys drops repeats and keeps the order, so village names survive the limit.
    return tuple(t for t in dict.fromkeys(terms) if t)[:MAX_KEYTERMS]
