"""Map sources.

``riverbend`` is the synthetic grid city (the default for tests and benchmarks). Any
``*.json`` snapshot in ``app/data/maps`` is a real-geography map produced by
``scripts/build_map.py`` from OpenStreetMap roads/rivers and a Copernicus DEM.
Snapshots are committed so runs stay deterministic and work offline.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "maps"
SYNTHETIC = "riverbend"


class Projection:
    """Local equirectangular projection: x east, y south, both in km (same one the builder uses)."""

    def __init__(self, lat0: float, lon0: float):
        self.lat0, self.lon0 = lat0, lon0
        self.kx = 111.320 * math.cos(math.radians(lat0))
        self.ky = 110.574

    def xy(self, lat: float, lng: float) -> tuple[float, float]:
        return ((lng - self.lon0) * self.kx, (self.lat0 - lat) * self.ky)

    def to_dict(self) -> dict[str, float]:
        return {"lat0": self.lat0, "lon0": self.lon0, "kx": self.kx, "ky": self.ky}


@lru_cache(maxsize=8)
def load_snapshot(map_id: str) -> Optional[dict[str, Any]]:
    if map_id == SYNTHETIC:
        return None
    path = DATA_DIR / f"{map_id}.json"
    if not path.exists():
        raise KeyError(map_id)
    return json.loads(path.read_text(encoding="utf-8"))


def map_ids() -> list[str]:
    return [SYNTHETIC] + sorted(p.stem for p in DATA_DIR.glob("*.json"))


def is_known(map_id: str) -> bool:
    return map_id in map_ids()


def available_maps() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [
        {
            "id": SYNTHETIC,
            "name": "Riverbend (synthetic)",
            "region": "Synthetic city",
            "real": False,
            "note": "Hand-built grid city used for tests and benchmarks.",
        }
    ]
    for mid in map_ids()[1:]:
        snap = load_snapshot(mid) or {}
        kinds: dict[str, int] = {}
        for e in snap.get("edges", []):
            kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
        out.append(
            {
                "id": mid,
                "name": snap.get("name", mid),
                "region": snap.get("region", ""),
                "real": True,
                "note": snap.get("note", ""),
                "center": snap.get("origin"),
                "bbox": snap.get("bbox"),
                "nodes": len(snap.get("nodes", [])),
                "bridges": kinds.get("bridge", 0),
                "shelters": len(snap.get("shelters", [])),
                "population": snap.get("population_total"),
                "source": snap.get("source", {}),
            }
        )
    return out
