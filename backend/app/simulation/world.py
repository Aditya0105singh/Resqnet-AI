"""Riverbend — the synthetic city, plus seeded incident and report generation.

The city geometry is fixed (stable IDs across every run); the scenario seed only
changes incidents, reports and their noise. Nothing here is real-world data.
"""
from __future__ import annotations

import dataclasses
import json
import math
import os
import random
import re

from .scenarios import ScenarioConfig
from .state import (
    EdgeKind,
    GraphEdge,
    GraphNode,
    IncidentReport,
    Neighbourhood,
    RescueResource,
    ResourceKind,
    Shelter,
    WorldState,
)

ROWS, COLS = 6, 8
DX, DY = 1.4, 1.25
RIVER_GAP = 0.9

NEIGHBOURHOODS = [
    Neighbourhood("NB", "Northbank", 0.95),
    Neighbourhood("HC", "Hillcrest", 0.80),
    Neighbourhood("OQ", "Old Quarter", 1.00),
    Neighbourhood("RS", "Riverside", 1.15),
    Neighbourhood("EM", "Eastmere", 1.05),
]

BASE_ELEV = {0: 6.0, 1: 4.4, 2: 2.9, 3: 2.5, 4: 3.6, 5: 5.2}
SHELTER_NODES = {"S1": ("N22", "Northbank Community School"), "S2": ("N34", "Riverside Civic Arena"), "S3": ("N26", "Hillcrest Sports Hall")}
BRIDGES = {1: ("BR1", "Mill Bridge", 3.3), 4: ("BR2", "Central Bridge", 4.2), 6: ("BR3", "Eastgate Bridge", 3.0)}
NORTH_JETTIES = (0, 2, 4, 6)
SOUTH_JETTIES = (1, 3, 4, 6)
REMOVED_ROADS = {("N01", "N02"), ("N15", "N16"), ("N40", "N50"), ("N13", "N23"), ("N44", "N45"), ("N06", "N16")}
DIAGONALS = [("N11", "N02"), ("N15", "N24"), ("N43", "N52"), ("N46", "N55"), ("N31", "N42"), ("N17", "N26")]

BOAT_SPECS = [("Boat Alpha", 6, "R1"), ("Boat Bravo", 8, "R3"), ("Boat Charlie", 6, "R5"), ("Boat Delta", 4, "R6"), ("Boat Echo", 6, "R2"), ("Boat Foxtrot", 6, "R4"), ("Boat Golf", 8, "R0")]
GROUND_SPECS = [("Team Granite", 8, "N11"), ("Team Harbor", 10, "N14"), ("Team Ironwood", 6, "N41"), ("Team Juniper", 8, "N46"), ("Team Kestrel", 8, "N52"), ("Team Linden", 6, "N05")]

SOURCES = {"resident": 0.6, "sensor": 0.75, "responder": 0.9}
DEADLINE_BY_URGENCY = {5: 30, 4: 45, 3: 70, 2: 100, 1: 140}


def nbhd_of(r: int, c: int) -> str:
    if r <= 2:
        return "NB" if c <= 3 else "HC"
    if c <= 2:
        return "OQ"
    if c <= 5:
        return "RS"
    return "EM"


def _land_id(r: int, c: int) -> str:
    return f"N{r}{c}"


def build_city() -> tuple[dict[str, GraphNode], dict[str, GraphEdge]]:
    geo = random.Random(2026)  # fixed geometry seed: Riverbend never changes
    nodes: dict[str, GraphNode] = {}
    for r in range(ROWS):
        for c in range(COLS):
            nid = _land_id(r, c)
            x = c * DX + geo.uniform(-0.18, 0.18)
            y = r * DY + (RIVER_GAP if r >= 3 else 0) + geo.uniform(-0.15, 0.15)
            nb = nbhd_of(r, c)
            elev = BASE_ELEV[r] + geo.uniform(-0.35, 0.35)
            if nb == "RS" and r <= 4:
                elev -= 0.9
            if nb == "EM" and r <= 4:
                elev -= 0.4
            if nb == "NB" and r == 2 and c in (0, 1):
                elev -= 0.3
            nodes[nid] = GraphNode(nid, round(x, 3), round(y, 3), round(elev, 2), nb, "land")
    for sid, (nid, name) in SHELTER_NODES.items():
        n = nodes[nid]
        n.kind = "shelter"
        n.label = name
        n.elevation = round(n.elevation + 2.4, 2)  # raised ground / levee
    for c in range(COLS):
        rid = f"R{c}"
        x = c * DX + 0.25 * math.sin(c * 1.3)
        y = 2 * DY + (RIVER_GAP + DY) / 2 + 0.28 * math.sin(c * 0.9 + 0.4)
        nb = nbhd_of(3 if c % 2 else 2, c)
        nodes[rid] = GraphNode(rid, round(x, 3), round(y, 3), 0.0, nb, "river", label="Riverbend Channel")

    edges: dict[str, GraphEdge] = {}

    def dist(a: str, b: str) -> float:
        na, nb_ = nodes[a], nodes[b]
        return round(math.hypot(na.x - nb_.x, na.y - nb_.y), 3)

    def add(u: str, v: str, kind: str, eid: str | None = None, name: str = "", clearance: float = 99.0) -> None:
        a, b = sorted((u, v))
        eid = eid or f"E-{a}-{b}"
        edges[eid] = GraphEdge(eid, a, b, kind, dist(a, b), name=name, clearance=clearance, ground_ok=kind in (EdgeKind.ROAD, EdgeKind.BRIDGE), boat_ok=kind in (EdgeKind.RIVER, EdgeKind.JETTY))

    for r in range(ROWS):
        for c in range(COLS):
            a = _land_id(r, c)
            if c + 1 < COLS:
                b = _land_id(r, c + 1)
                if (a, b) not in REMOVED_ROADS:
                    add(a, b, EdgeKind.ROAD)
            if r + 1 < ROWS and r != 2:
                b = _land_id(r + 1, c)
                if (a, b) not in REMOVED_ROADS:
                    add(a, b, EdgeKind.ROAD)
    for a, b in DIAGONALS:
        add(a, b, EdgeKind.ROAD)
    for c, (bid, name, clr) in BRIDGES.items():
        add(_land_id(2, c), _land_id(3, c), EdgeKind.BRIDGE, eid=bid, name=name, clearance=clr)
    for c in range(COLS - 1):
        add(f"R{c}", f"R{c + 1}", EdgeKind.RIVER)
    for c in NORTH_JETTIES:
        add(f"R{c}", _land_id(2, c), EdgeKind.JETTY)
    for c in SOUTH_JETTIES:
        add(f"R{c}", _land_id(3, c), EdgeKind.JETTY)
    return nodes, edges


def nearest_land_nbhd(world: WorldState, node_id: str) -> str:
    n = world.nodes[node_id]
    if n.kind != "river":
        return n.neighbourhood
    best = min((m for m in world.nodes.values() if m.kind != "river"), key=lambda m: (math.hypot(m.x - n.x, m.y - n.y), m.id))
    return best.neighbourhood


GEO_DIR = os.environ.get("RESQNET_GEO_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "geographic"))
RIVERBEND_META = {
    "name": "Riverbend (synthetic)",
    "synthetic": True,
    "disclaimer": "Synthetic city for research and education. Not real geography or live flood data.",
    "attribution": "",
}


def available_geographies() -> list[dict]:
    out = [{"id": "riverbend", "name": RIVERBEND_META["name"], "synthetic": True}]
    if os.path.isdir(GEO_DIR):
        for f in sorted(os.listdir(GEO_DIR)):
            if f.endswith(".city.json"):
                try:
                    c = load_city_file(f[: -len(".city.json")])
                    out.append({"id": f[: -len(".city.json")], "name": c["name"], "synthetic": c.get("synthetic", False), "attribution": c["source"].get("attribution", "")})
                except (OSError, ValueError, KeyError):
                    continue
    return out


def load_city_file(stem: str) -> dict:
    if not re.fullmatch(r"[a-z0-9_-]{1,64}", stem or ""):
        raise ValueError(f"bad geography id {stem!r}")
    path = os.path.join(GEO_DIR, f"{stem}.city.json")
    with open(path, encoding="utf-8") as f:
        city = json.load(f)
    if city.get("format") != "resqnet-city/1":
        raise ValueError(f"{path} is not a resqnet-city/1 file")
    return city


def _from_city(city: dict) -> tuple[dict[str, GraphNode], dict[str, GraphEdge], dict[str, Neighbourhood]]:
    nodes = {n["id"]: GraphNode(n["id"], n["x"], n["y"], n["elevation"], n["neighbourhood"], n["kind"], n.get("label", ""), lat=n.get("lat"), lon=n.get("lon"), provenance=n.get("provenance", "")) for n in city["nodes"]}
    edges = {}
    for e in city["edges"]:
        k = e["kind"]
        edges[e["id"]] = GraphEdge(e["id"], e["u"], e["v"], k, e["length_km"], name=e.get("name", ""), clearance=e.get("clearance", 99.0),
                                   ground_ok=k in (EdgeKind.ROAD, EdgeKind.BRIDGE), boat_ok=k in (EdgeKind.RIVER, EdgeKind.JETTY))
    nbs = {z["id"]: Neighbourhood(z["id"], z["name"], z["flood_factor"]) for z in city["neighbourhoods"]}
    return nodes, edges, nbs


def build_world(cfg: ScenarioConfig, strategy: str) -> WorldState:
    if cfg.geography and cfg.geography != "riverbend":
        return _build_from_city(cfg, strategy, load_city_file(cfg.geography))
    nodes, edges = build_city()
    resources: dict[str, RescueResource] = {}
    for i, (name, cap, home) in enumerate(BOAT_SPECS[: max(0, min(cfg.boats, len(BOAT_SPECS)))]):
        rid = f"B{i + 1}"
        resources[rid] = RescueResource(rid, name, ResourceKind.BOAT, cap, 16.0, home, home)
    for i, (name, cap, home) in enumerate(GROUND_SPECS[: max(0, min(cfg.ground_units, len(GROUND_SPECS)))]):
        if cfg.key == "bridge_dependency":
            home = ("N41", "N44", "N46", "N52", "N53", "N55")[i]
        rid = f"G{i + 1}"
        resources[rid] = RescueResource(rid, name, ResourceKind.GROUND, cap, 28.0, home, home)
    shelters: dict[str, Shelter] = {}
    for i, (sid, (nid, name)) in enumerate(SHELTER_NODES.items()):
        cap = cfg.shelter_capacity[i] if i < len(cfg.shelter_capacity) else 40
        occ = cfg.shelter_occupancy[i] if i < len(cfg.shelter_occupancy) else 0
        shelters[sid] = Shelter(sid, name, nid, int(cap), min(int(occ), int(cap)))
    return WorldState(
        tick=0,
        seed=cfg.seed,
        scenario=cfg.key,
        strategy=strategy,
        nodes=nodes,
        edges=edges,
        neighbourhoods={n.id: Neighbourhood(n.id, n.name, n.flood_factor) for n in NEIGHBOURHOODS},
        resources=resources,
        shelters=shelters,
        meta=dict(RIVERBEND_META),
    )


def _build_from_city(cfg: ScenarioConfig, strategy: str, city: dict) -> WorldState:
    nodes, edges, nbs = _from_city(city)
    resources: dict[str, RescueResource] = {}
    boat_homes = [h for h in city.get("boat_homes", []) if h in nodes]
    ground_homes = [h for h in city.get("ground_homes", []) if h in nodes]
    if boat_homes:
        for i, (name, cap, _home) in enumerate(BOAT_SPECS[: max(0, min(cfg.boats, len(BOAT_SPECS)))]):
            home = boat_homes[i % len(boat_homes)]
            resources[f"B{i + 1}"] = RescueResource(f"B{i + 1}", name, ResourceKind.BOAT, cap, 16.0, home, home)
    if ground_homes:
        for i, (name, cap, _home) in enumerate(GROUND_SPECS[: max(0, min(cfg.ground_units, len(GROUND_SPECS)))]):
            home = ground_homes[i % len(ground_homes)]
            resources[f"G{i + 1}"] = RescueResource(f"G{i + 1}", name, ResourceKind.GROUND, cap, 28.0, home, home)
    shelters: dict[str, Shelter] = {}
    for i, s in enumerate(city["shelters"]):
        cap = cfg.shelter_capacity[i] if i < len(cfg.shelter_capacity) else 40
        occ = cfg.shelter_occupancy[i] if i < len(cfg.shelter_occupancy) else 0
        shelters[s["id"]] = Shelter(s["id"], s["name"], s["node"], int(cap), min(int(occ), int(cap)))
    src = city.get("source", {})
    meta = {
        "name": city["name"],
        "synthetic": bool(city.get("synthetic")),
        "disclaimer": ("Synthetic test geography." if city.get("synthetic") else "Real road and river geometry from OpenStreetMap; incidents, floods, shelters and units are simulated.")
        + " Elevation, jetties and bridge clearances are scenario-assumed.",
        "attribution": src.get("attribution", ""),
        "license": src.get("license", ""),
        "assumptions": city.get("assumptions", []),
        "landmarks": city.get("landmarks", []),
        "geography": cfg.geography,
    }
    return WorldState(tick=0, seed=cfg.seed, scenario=cfg.key, strategy=strategy, nodes=nodes, edges=edges, neighbourhoods=nbs, resources=resources, shelters=shelters, meta=meta)


def generate_reports(world: WorldState, cfg: ScenarioConfig) -> list[IncidentReport]:
    """Create hidden ground-truth incidents and the (noisy) reports that describe them.

    Each truth incident is represented only through reports; agents never read
    `truth_*` fields — they are revealed physically when a unit arrives.
    """
    rng = random.Random(cfg.seed * 7919 + 17)
    land = [n for n in world.nodes.values() if n.kind == "land"]
    if cfg.key == "bridge_dependency" and world.meta.get("name") == RIVERBEND_META["name"]:
        land = [n for n in land if int(n.id[1]) >= 3]
    peak = 1.2 + cfg.flood_severity * 2.2
    weights = []
    for n in land:
        exposure = max(0.0, peak * world.neighbourhoods[n.neighbourhood].flood_factor - n.elevation)
        weights.append(1.0 + 3.0 * min(exposure, 2.0))

    truths: list[dict] = []
    total = cfg.initial_incidents + cfg.arrival_incidents
    used: dict[str, int] = {}
    for i in range(total):
        tick = 0 if i < cfg.initial_incidents else rng.randint(3, max(4, cfg.arrival_window))
        for _ in range(20):
            node = rng.choices(land, weights=weights)[0]
            if abs(used.get(node.id, -999) - tick) > 60:
                break
        used[node.id] = tick
        people = rng.choices([1, 2, 3, 4, 5, 6, 7, 8, 10], weights=[6, 12, 14, 14, 12, 9, 6, 4, 2])[0]
        urgency = rng.choices([1, 2, 3, 4, 5], weights=[8, 18, 30, 26, 18])[0]
        truths.append({"id": f"T{i + 1:03d}", "tick": tick, "node": node.id, "people": people, "urgency": urgency, "exists": True})
    n_false = int(round(cfg.false_alarm_rate * total))
    for j in range(n_false):
        node = rng.choices(land, weights=weights)[0]
        truths.append({"id": f"F{j + 1:03d}", "tick": rng.randint(2, max(3, cfg.arrival_window)), "node": node.id, "people": 0, "urgency": rng.choice([3, 4, 5]), "exists": False})

    def neighbour_of(nid: str) -> str:
        nbrs = [e.v if e.u == nid else e.u for e in world.edges.values() if (e.u == nid or e.v == nid) and e.kind == EdgeKind.ROAD]
        return rng.choice(sorted(nbrs)) if nbrs else nid

    reports: list[IncidentReport] = []
    forwards: list[tuple[IncidentReport, IncidentReport]] = []  # (copy, original)

    def mk(t: dict, tick: int, source: str, claim: str = "PRESENT", note: str = "") -> IncidentReport:
        noise = cfg.report_noise
        people: int | None = t["people"] if t["exists"] else rng.randint(2, 6)
        urgency: int | None = t["urgency"]
        node = t["node"]
        unc = 0.0 if source != "resident" else 0.3
        if claim == "PRESENT":
            if rng.random() < noise:
                people = None if rng.random() < 0.3 else max(1, (people or 3) + rng.choice([-3, -2, -1, 1, 2, 3]))
            if rng.random() < noise:
                urgency = None if rng.random() < 0.3 else min(5, max(1, (urgency or 3) + rng.choice([-2, -1, 1])))
            if source == "resident" and rng.random() < noise * 0.6:
                node = neighbour_of(node)
                unc = 1.6
        else:
            people, urgency = 0, None
        rep = IncidentReport(
            id="",
            tick=tick,
            source=source,
            reliability=SOURCES[source],
            node=node,
            people=people,
            urgency=urgency,
            claim=claim,
            location_uncertainty_km=unc,
            truth_id=t["id"],
            note=note,
        )
        return rep

    for t in truths:
        src = rng.choices(["resident", "sensor", "responder"], weights=[55, 20, 25])[0] if t["exists"] else "resident"
        tick = t["tick"]
        if rng.random() < cfg.delayed_report_rate:
            tick += rng.randint(8, 22)
        first = mk(t, tick, src, note="initial SOS" if tick == t["tick"] else "delayed SOS")
        reports.append(first)
        # verbatim forwards (only drawn when enabled, so other scenarios' random streams are unchanged)
        if cfg.forward_rate > 0 and src == "resident" and rng.random() < cfg.forward_rate:
            first.fingerprint = f"FP-{t['id']}"
            for _ in range(rng.randint(2, 5)):
                copy = dataclasses.replace(first, tick=tick + rng.randint(1, 15), note="forwarded copy of an earlier SOS")
                reports.append(copy)
                forwards.append((copy, first))
        if rng.random() < cfg.duplicate_rate:
            reports.append(mk(t, tick + rng.randint(2, 12), rng.choice(["resident", "sensor", "responder"]), note="duplicate report"))
        if not t["exists"] and rng.random() < 0.75:
            reports.append(mk(t, tick + rng.randint(6, 18), "responder", claim="NO_VICTIMS", note="responder found no victims"))
        if t["exists"] and rng.random() < cfg.contradiction_rate:
            reports.append(mk(t, tick + rng.randint(3, 14), "resident", claim="NO_VICTIMS", note="contradictory resident report"))

    reports.sort(key=lambda r: (r.tick, r.truth_id, r.source, r.claim))
    for i, r in enumerate(reports):
        r.id = f"RPT-{i + 1:03d}"
    for copy, original in forwards:
        copy.derived_from = original.id
    world.counters["RPT"] = len(reports)
    world.truth = {t["id"]: dict(t, remaining=t["people"] if t["exists"] else 0) for t in truths}
    return reports
