"""Geocoder — Nominatim HTTP calls intercepted via module-level _transport."""
from __future__ import annotations

import httpx
import pytest

import app.services.geocoder as geocoder_mod
from app.services.geocoder import nominatim_geocode


def _mock_hit(place_id: int = 12345, lat: str = "18.5", lon: str = "73.8") -> list[dict]:
    return [{"place_id": place_id, "lat": lat, "lon": lon,
             "display_name": "Test Village, Pune District, Maharashtra, India"}]


@pytest.fixture(autouse=True)
def _clear_cache():
    """Ensure lru_cache is empty before each test."""
    nominatim_geocode.cache_clear()
    yield
    nominatim_geocode.cache_clear()
    geocoder_mod._transport = None


def test_geocoder_returns_coords_on_hit():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.params["countrycodes"] == "IN"
        assert req.url.params["format"] == "json"
        return httpx.Response(200, json=_mock_hit())

    geocoder_mod._transport = httpx.MockTransport(handler)
    result = nominatim_geocode("Nashik")
    assert result is not None
    lat, lon, osm_id = result
    assert abs(lat - 18.5) < 0.001
    assert abs(lon - 73.8) < 0.001
    assert osm_id == "OSM:12345"


def test_geocoder_returns_none_on_empty_result():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    geocoder_mod._transport = httpx.MockTransport(handler)
    assert nominatim_geocode("XyzUnknownPlace123") is None


def test_geocoder_returns_none_on_network_error():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable")

    geocoder_mod._transport = httpx.MockTransport(handler)
    assert nominatim_geocode("SomePlace") is None


def test_geocoder_caches_results():
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_mock_hit())

    geocoder_mod._transport = httpx.MockTransport(handler)
    nominatim_geocode("Pune")
    nominatim_geocode("Pune")
    assert calls["n"] == 1
