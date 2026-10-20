"""Loader for the SIMULATED reference gazetteer (fictional places, simulated coordinates)."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from functools import lru_cache

from ..config import DATA_DIR


@dataclass(frozen=True)
class Place:
    id: str
    name: str
    name_local: str
    aliases: tuple[str, ...]
    latitude: float
    longitude: float
    type: str = "place"  # "place", "city", "state"


@dataclass(frozen=True)
class Landmark:
    id: str
    place_id: str
    type: str
    name: str
    specific_aliases: tuple[str, ...]


@dataclass(frozen=True)
class Gazetteer:
    notice: str
    district: str
    state: str
    places: dict[str, Place]
    landmarks: dict[str, Landmark]
    landmark_types: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def landmarks_of_type(self, ltype: str) -> list[Landmark]:
        return [lm for lm in self.landmarks.values() if lm.type == ltype]

    def to_public(self) -> dict:
        return {
            "notice": self.notice,
            "district": self.district,
            "state": self.state,
            "is_simulated": True,
            "places": [
                {"id": p.id, "name": p.name, "name_local": p.name_local,
                 "latitude": p.latitude, "longitude": p.longitude, "coordinate_source": "simulated"}
                for p in self.places.values()
            ],
            "landmarks": [
                {"id": lm.id, "place_id": lm.place_id, "type": lm.type, "name": lm.name}
                for lm in self.landmarks.values()
            ],
        }


@lru_cache(maxsize=1)
def load_gazetteer() -> Gazetteer:
    raw = json.loads((DATA_DIR / "simulated_gazetteer.json").read_text(encoding="utf-8"))
    places = {
        p["id"]: Place(p["id"], p["name"], p["name_local"], tuple(p["aliases"]), p["latitude"], p["longitude"],
                       p.get("type", "place"))
        for p in raw["places"]
    }
    landmarks = {
        lm["id"]: Landmark(lm["id"], lm["place_id"], lm["type"], lm["name"], tuple(lm.get("specific_aliases", [])))
        for lm in raw["landmarks"]
    }
    types = {k: tuple(v) for k, v in raw["landmark_types"].items()}
    return Gazetteer(raw["_notice"], raw["district"], raw["state"], places, landmarks, types)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
