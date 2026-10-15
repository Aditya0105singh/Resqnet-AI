#!/usr/bin/env python3
"""Named places for a real-geography map snapshot, so citizen SOS messages can be placed.

The map snapshots in backend/app/data/maps/ are coarse junction graphs. This script takes the
named places (stations, markets, temples, hospitals ...) from an OpenStreetMap extract, adds the
project's Hindi/Malayalam aliases, and attaches each place to the nearest junction of the snapshot.
The result is a sidecar file the engine loads next to the snapshot:

    python scripts/build_landmarks.py \\
        --osm-file data/geographic/sources/aluva.osm \\
        --map kerala_aluva \\
        --town Aluva \\
        --aliases data/geographic/sources/aluva.aliases.json

A place is attached only when a junction lies within --max-km of it; the dispatcher always
confirms the location before any unit is sent, so a junction near a named place is a proposal,
not an order.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.geography.osm_city import ALIAS_TAGS, LANDMARK_KEYS, PLACE_TYPES, _drop_town_name, parse_osm  # noqa: E402

MAPS = os.path.join(ROOT, "backend", "app", "data", "maps")
OUT = os.path.join(ROOT, "backend", "app", "data", "landmarks")


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    dy = (a[0] - b[0]) * 110.574
    dx = (a[1] - b[1]) * 111.320 * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot(dx, dy)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--osm-file", required=True)
    ap.add_argument("--map", required=True, help="snapshot id in backend/app/data/maps")
    ap.add_argument("--town", default="", help="the town's own name: not a location inside the town")
    ap.add_argument("--aliases", help="JSON file: landmark name -> extra names")
    ap.add_argument("--max-km", type=float, default=0.6)
    a = ap.parse_args()

    with open(os.path.join(MAPS, f"{a.map}.json"), encoding="utf-8") as f:
        snap = json.load(f)
    land = {n["id"]: (n["lat"], n["lng"]) for n in snap["nodes"] if n["kind"] == "land"}
    nodes, ways, _meta = parse_osm(open(a.osm_file, encoding="utf-8").read())

    feats: list[tuple[tuple[float, float], dict]] = []
    for _id, (lat, lon, tags) in nodes.items():
        if tags.get("name"):
            feats.append(((lat, lon), tags))
    for _wid, refs, tags in ways:
        if tags.get("name") and not tags.get("highway") and not tags.get("waterway"):
            pts = [nodes[r] for r in refs if r in nodes]
            if pts:
                feats.append(((sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)), tags))

    extra = {}
    if a.aliases:
        with open(a.aliases, encoding="utf-8") as f:
            extra = {k: v for k, v in json.load(f).items() if not k.startswith("_")}

    landmarks: list[dict] = []
    for p, t in feats:
        if not any(t.get(k) for k in LANDMARK_KEYS) and t.get("place") not in PLACE_TYPES:
            continue
        near = min(land, key=lambda n: (km(land[n], p), n))
        if km(land[near], p) > a.max_km:
            continue
        aliases = sorted({t[k].strip() for k in ALIAS_TAGS if t.get(k)})
        landmarks.append({"id": f"L{len(landmarks) + 1}", "name": t["name"], "node": near, "aliases": aliases, "type": next((t[k] for k in LANDMARK_KEYS if t.get(k)), t.get("place", "")), "provenance": "osm"})
    landmarks = _drop_town_name(landmarks, a.town)
    for lm in landmarks:
        add = extra.get(lm["name"], [])
        if add:
            lm["aliases"] = sorted(set(lm["aliases"]) | set(add))
            lm["added_aliases"] = sorted(add)  # project-added, not from OSM

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{a.map}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"map": a.map, "source": "OpenStreetMap contributors (ODbL); aliases marked added_aliases are project-added", "landmarks": landmarks}, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(landmarks)} places attached to {len({l['node'] for l in landmarks})} junctions -> {path}")


if __name__ == "__main__":
    main()
