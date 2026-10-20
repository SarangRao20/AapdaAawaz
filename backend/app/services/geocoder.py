"""Best-effort geocoding via Nominatim (OpenStreetMap) for unmapped caller-stated places.

Called only when GEOCODING_ENABLED=true. Results are cached in-process (lru_cache) to avoid
repeated identical requests during a single run. A single HTTP GET with a 3-second timeout; no
retry — this is enrichment, not a critical path.
"""
from __future__ import annotations

import logging
from functools import lru_cache

import httpx

log = logging.getLogger(__name__)

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_USER_AGENT = "AapdaAwaaz/1.0 (disaster triage prototype; contact: see repository)"

# Set in tests to a httpx.MockTransport to avoid real network calls.
_transport: httpx.BaseTransport | None = None


@lru_cache(maxsize=256)
def nominatim_geocode(place_name: str) -> tuple[float, float, str] | None:
    """Return (lat, lon, osm_place_id_str) for a place in India, or None if not found.

    osm_place_id_str is formatted as "OSM:{osm_id}" and satisfies the ExtractedLocation
    model validator that requires a reference place_id when coordinates are provided.
    """
    try:
        with httpx.Client(transport=_transport, timeout=3.0) as client:
            resp = client.get(
                _NOMINATIM_URL,
                params={"q": place_name, "countrycodes": "IN", "format": "json", "limit": 1},
                headers={"User-Agent": _USER_AGENT},
            )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            return None
        hit = results[0]
        return float(hit["lat"]), float(hit["lon"]), f"OSM:{hit['place_id']}"
    except Exception as exc:
        log.debug("nominatim_geocode(%r) failed: %s", place_name, exc)
        return None
