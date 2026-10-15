"""OpenStreetMap extract → RESQNET city file (`*.city.json`).

Dependency-free: reads OSM XML (as exported by Overpass or JOSM) with the standard
library, so it runs offline and in CI. `scripts/build_geo.py` adds an optional Overpass
download for a bounding box.

Pipeline
1. Roads: ways with an allowed `highway` tag, split into segments, simplified to
   junctions (degree ≠ 2), then merged on a grid (`merge_km`) to a simulation-sized
   graph; the largest connected component is kept. `bridge=yes` survives merging.
2. River: the longest `waterway=river|canal` line is resampled every `river_step_km`
   into boat nodes; each river node within `jetty_max_km` of a road node gets a jetty.
   Jetties are **scenario-assumed** (OSM does not say where boats can land).
3. Neighbourhoods: k-means on node positions (deterministic farthest-point start),
   named after the nearest OSM `place` node when there is one.
4. Elevation: **scenario-assumed** proxy from distance to the river (no DEM is used),
   flagged as such in the file. Bridge clearances are scenario-assumed too.
5. Shelters: the most spread-out named schools / community halls / town halls, marked
   **hypothetical** (not verified relief camps). Fallback: high, spread-out nodes.
6. Landmarks: named OSM features with `name`, `name:en`, `name:hi`, `name:ml`,
   `alt_name` aliases, for the SOS gazetteer.

Every node and edge carries `provenance`: "osm", "osm-derived" or "scenario-assumed".
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

ROAD_TYPES = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street", "service"}
ROAD_TYPES |= {f"{t}_link" for t in ("motorway", "trunk", "primary", "secondary", "tertiary")}
SHELTER_AMENITIES = ("school", "college", "community_centre", "townhall", "social_facility", "university")
LANDMARK_KEYS = ("amenity", "shop", "tourism", "historic", "railway", "public_transport", "leisure", "building")
ALIAS_TAGS = ("name", "name:en", "name:hi", "name:ml", "alt_name", "short_name")
PLACE_TYPES = {"suburb", "neighbourhood", "quarter", "village", "hamlet", "locality"}


@dataclass
class Options:
    merge_km: float = 0.15
    river_step_km: float = 0.4
    jetty_max_km: float = 0.4
    neighbourhoods: int = 5
    road_types: set[str] = field(default_factory=lambda: set(ROAD_TYPES))
    name: str = "OSM city"
    synthetic: bool = False
    clip: bool = True  # trim to the extract's <bounds>, when present
    aliases: dict[str, list[str]] = field(default_factory=dict)  # extra names per landmark name, e.g. translations


# ---------------------------------------------------------------- parsing


def parse_osm(xml_text: str) -> tuple[dict[str, tuple[float, float, dict]], list[tuple[str, list[str], dict]], dict[str, Any]]:
    root = ET.fromstring(xml_text)
    nodes: dict[str, tuple[float, float, dict]] = {}
    ways: list[tuple[str, list[str], dict]] = []
    for el in root:
        if el.tag == "node":
            tags = {t.get("k"): t.get("v") for t in el.findall("tag")}
            nodes[el.get("id")] = (float(el.get("lat")), float(el.get("lon")), tags)
        elif el.tag == "way":
            tags = {t.get("k"): t.get("v") for t in el.findall("tag")}
            refs = [nd.get("ref") for nd in el.findall("nd")]
            ways.append((el.get("id"), refs, tags))
    meta = {"generator": root.get("generator", ""), "timestamp": (root.find("meta").get("osm_base") if root.find("meta") is not None else "")}
    b = root.find("bounds")
    if b is not None:
        meta["bounds"] = tuple(float(b.get(k)) for k in ("minlat", "minlon", "maxlat", "maxlon"))
    return nodes, ways, meta


def clip_to_bounds(nodes: dict, ways: list, bounds: tuple[float, float, float, float], margin: float = 0.05) -> tuple[dict, list]:
    """Drop nodes outside the extract's bounding box (plus a small margin) and split ways at the cut.

    Exports include every node of every way that touches the box, so a river or highway can run
    tens of kilometres past it. Each way becomes its contiguous runs of inside nodes.
    """
    s, w, n, e = bounds
    dlat, dlon = (n - s) * margin, (e - w) * margin
    inside = {k: v for k, v in nodes.items() if s - dlat <= v[0] <= n + dlat and w - dlon <= v[1] <= e + dlon}
    out: list[tuple[str, list[str], dict]] = []
    for wid, refs, tags in ways:
        run: list[str] = []
        part = 0
        for r in refs + [None]:
            if r is not None and r in inside:
                run.append(r)
                continue
            if r is not None and r not in nodes:
                continue  # missing from the extract altogether: not a cut
            if len(run) >= 2 or (run and len(refs) == 1):
                out.append((wid if part == 0 else f"{wid}.{part}", run, tags))
                part += 1
            run = []
    return inside, out


class Projection:
    """Local equirectangular projection in km around the data centroid; north is up (−y)."""

    def __init__(self, lat0: float, lon0: float):
        self.lat0, self.lon0 = lat0, lon0
        self.kx = 111.320 * math.cos(math.radians(lat0))
        self.ky = 110.574

    def xy(self, lat: float, lon: float) -> tuple[float, float]:
        return ((lon - self.lon0) * self.kx, -(lat - self.lat0) * self.ky)

    def latlon(self, x: float, y: float) -> tuple[float, float]:
        return (self.lat0 - y / self.ky, self.lon0 + x / self.kx)


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


# ---------------------------------------------------------------- roads


def _road_graph(nodes: dict, ways: list, proj: Projection, opt: Options) -> tuple[dict[str, tuple[float, float]], dict[tuple[str, str], dict]]:
    """Segment graph (OSM node ids), then simplified to junctions."""
    pos: dict[str, tuple[float, float]] = {}
    adj: dict[str, dict[str, dict]] = {}
    for _wid, refs, tags in ways:
        if tags.get("highway") not in opt.road_types or tags.get("area") == "yes":
            continue
        refs = [r for r in refs if r in nodes]
        bridge = tags.get("bridge") not in (None, "no")
        name = tags.get("name", "")
        for a, b in zip(refs, refs[1:]):
            for r in (a, b):
                if r not in pos:
                    pos[r] = proj.xy(nodes[r][0], nodes[r][1])
            if a == b:
                continue
            seg = {"len": _dist(pos[a], pos[b]), "bridge": bridge, "name": name}
            adj.setdefault(a, {})[b] = seg
            adj.setdefault(b, {})[a] = seg
    keep = {n for n, nb in adj.items() if len(nb) != 2}
    edges: dict[tuple[str, str], dict] = {}
    seen: set[tuple[str, str]] = set()
    for start in sorted(keep):
        for nxt in sorted(adj[start]):
            if (start, nxt) in seen:
                continue
            length, bridge, names, prev, cur = 0.0, False, [], start, nxt
            pts = [pos[start]]
            while True:
                seen.add((prev, cur))
                seen.add((cur, prev))
                seg = adj[prev][cur]
                length += seg["len"]
                bridge |= seg["bridge"]
                if seg["name"]:
                    names.append(seg["name"])
                pts.append(pos[cur])
                if cur in keep:
                    break
                prev, cur = cur, next(x for x in adj[cur] if x != prev)
                if cur == start:
                    break
            if cur != start:
                key = tuple(sorted((start, cur)))
                cand = {"len": length, "bridge": bridge, "name": max(set(names), key=names.count) if names else "", "pts": pts if key[0] == start else pts[::-1]}
                if key not in edges or edges[key]["len"] > length:
                    edges[key] = cand
    return {n: pos[n] for n in keep}, edges


def _merge(pos: dict[str, tuple[float, float]], edges: dict, merge_km: float) -> tuple[dict[str, tuple[float, float]], dict]:
    cell = lambda p: (math.floor(p[0] / merge_km), math.floor(p[1] / merge_km))  # noqa: E731
    groups: dict[tuple[int, int], list[str]] = {}
    for n, p in pos.items():
        groups.setdefault(cell(p), []).append(n)
    rep: dict[str, str] = {}
    mpos: dict[str, tuple[float, float]] = {}
    for c, members in groups.items():
        rid = min(members)
        for m in members:
            rep[m] = rid
        mpos[rid] = (sum(pos[m][0] for m in members) / len(members), sum(pos[m][1] for m in members) / len(members))
    medges: dict[tuple[str, str], dict] = {}
    for (a, b), e in edges.items():
        ra, rb = rep[a], rep[b]
        if ra == rb:
            continue
        key = tuple(sorted((ra, rb)))
        cur = medges.get(key)
        if cur is None or e["len"] < cur["len"]:
            pts = list(e.get("pts") or [pos[a], pos[b]])
            if ra != key[0]:
                pts = pts[::-1]
            pts = [mpos[key[0]], *pts[1:-1], mpos[key[1]]]
            medges[key] = {**e, "pts": pts, "bridge": e["bridge"] or bool(cur and cur["bridge"])}
        elif e["bridge"]:
            cur["bridge"] = True
    return mpos, medges


def _largest_component(pos: dict, edges: dict) -> tuple[dict, dict]:
    adj: dict[str, set[str]] = {n: set() for n in pos}
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    best: set[str] = set()
    seen: set[str] = set()
    for n in sorted(pos):
        if n in seen:
            continue
        comp, stack = set(), [n]
        while stack:
            x = stack.pop()
            if x in comp:
                continue
            comp.add(x)
            stack.extend(adj[x] - comp)
        seen |= comp
        if len(comp) > len(best):
            best = comp
    return {n: pos[n] for n in best}, {k: v for k, v in edges.items() if k[0] in best and k[1] in best}


# ---------------------------------------------------------------- river, zones, elevation


def _river_line(nodes: dict, ways: list, proj: Projection) -> list[tuple[float, float]]:
    """The longest river: OSM splits rivers into many ways, so ways that meet end to end are chained first."""
    segs = [[r for r in refs if r in nodes] for _wid, refs, tags in ways if tags.get("waterway") in ("river", "canal")]
    segs = [sg for sg in segs if len(sg) >= 2]
    chains: list[list[str]] = []
    for sg in segs:
        chains.append(list(sg))
        merged = True
        while merged:
            merged = False
            cur = chains[-1]
            for i, other in enumerate(chains[:-1]):
                if other[-1] == cur[0]:
                    joined = other + cur[1:]
                elif cur[-1] == other[0]:
                    joined = cur + other[1:]
                elif other[0] == cur[0]:
                    joined = other[::-1] + cur[1:]
                elif other[-1] == cur[-1]:
                    joined = other + cur[::-1][1:]
                else:
                    continue
                chains.pop(i)
                chains[-1] = joined
                merged = True
                break
    best: list[tuple[float, float]] = []
    best_len = 0.0
    for ch in chains:
        pts = [proj.xy(nodes[r][0], nodes[r][1]) for r in ch]
        length = sum(_dist(a, b) for a, b in zip(pts, pts[1:]))
        if length > best_len:
            best, best_len = pts, length
    return best


def _resample(line: list[tuple[float, float]], step: float) -> list[tuple[float, float]]:
    if len(line) < 2:
        return list(line)
    out = [line[0]]
    carry = 0.0
    for a, b in zip(line, line[1:]):
        seg = _dist(a, b)
        t = step - carry
        while t <= seg:
            out.append((a[0] + (b[0] - a[0]) * t / seg, a[1] + (b[1] - a[1]) * t / seg))
            t += step
        carry = (carry + seg) % step
    if _dist(out[-1], line[-1]) > step * 0.4:
        out.append(line[-1])
    return out


def _dist_to_line(p: tuple[float, float], line: list[tuple[float, float]]) -> float:
    if not line:
        return 2.0
    best = math.inf
    for a, b in zip(line, line[1:] or line):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = dx * dx + dy * dy
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
        best = min(best, _dist(p, (a[0] + t * dx, a[1] + t * dy)))
    return best


def _farthest_points(items: list[str], pos: dict, k: int, first: Optional[str] = None) -> list[str]:
    if not items:
        return []
    chosen = [first or min(items)]
    while len(chosen) < min(k, len(items)):
        nxt = max((x for x in items if x not in chosen), key=lambda x: (min(_dist(pos[x], pos[c]) for c in chosen), x))
        chosen.append(nxt)
    return chosen


def _kmeans(pos: dict[str, tuple[float, float]], k: int) -> dict[str, int]:
    ids = sorted(pos)
    cents = [pos[c] for c in _farthest_points(ids, pos, k)]
    assign: dict[str, int] = {}
    for _ in range(30):
        new = {n: min(range(len(cents)), key=lambda i: (_dist(pos[n], cents[i]), i)) for n in ids}
        if new == assign:
            break
        assign = new
        for i in range(len(cents)):
            members = [pos[n] for n in ids if assign[n] == i]
            if members:
                cents[i] = (sum(p[0] for p in members) / len(members), sum(p[1] for p in members) / len(members))
    return assign


def _feature_points(nodes: dict, ways: list, proj: Projection) -> list[tuple[tuple[float, float], dict]]:
    """Named point features: tagged nodes, and tagged ways (polygons) at their centroid."""
    out = []
    for _nid, (lat, lon, tags) in nodes.items():
        if tags.get("name"):
            out.append((proj.xy(lat, lon), tags))
    for _wid, refs, tags in ways:
        if tags.get("name") and not tags.get("highway") and not tags.get("waterway"):
            pts = [nodes[r] for r in refs if r in nodes]
            if pts:
                out.append((proj.xy(sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)), tags))
    return out


def _simplify(pts: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    """Douglas-Peucker: drop shape points closer than tol km to the line between their neighbours."""
    if len(pts) <= 2:
        return list(pts)
    a, b = pts[0], pts[-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1e-9
    i, d = max(((i, abs(dy * (p[0] - a[0]) - dx * (p[1] - a[1])) / L) for i, p in enumerate(pts[1:-1], 1)), key=lambda t: t[1])
    if d <= tol:
        return [a, b]
    return _simplify(pts[: i + 1], tol)[:-1] + _simplify(pts[i:], tol)


GREEN = {("leisure", "park"), ("leisure", "pitch"), ("leisure", "garden"), ("leisure", "festival_grounds"), ("landuse", "grass"), ("landuse", "recreation_ground"), ("landuse", "meadow"), ("natural", "grassland"), ("natural", "wood"), ("landuse", "forest")}


def _basemap(nodes: dict, ways: list, proj: Projection) -> dict[str, list]:
    """Background map layers drawn under the simulation: building footprints, green areas, ponds,
    railway lines and minor streams. Display only; the engine never reads them."""
    out: dict[str, list] = {"buildings": [], "green": [], "water": [], "rail": [], "streams": []}
    for _wid, refs, tags in ways:
        pts = [proj.xy(nodes[r][0], nodes[r][1]) for r in refs if r in nodes]
        if len(pts) < 2:
            continue
        closed = refs[0] == refs[-1] and len(pts) >= 4
        if tags.get("building") and closed:
            layer = "buildings"
        elif closed and any((k, tags.get(k)) in GREEN for k in ("leisure", "landuse", "natural")):
            layer = "green"
        elif closed and (tags.get("natural") == "water" or tags.get("water")):
            layer = "water"
        elif tags.get("railway") == "rail":
            layer = "rail"
        elif tags.get("waterway") in ("stream", "drain", "ditch", "canal"):
            layer = "streams"
        else:
            continue
        if closed:
            # split a ring at its far point so the simplifier never sees a zero-length baseline
            far = max(range(len(pts)), key=lambda i: _dist(pts[0], pts[i]))
            pts = _simplify(pts[: far + 1], 0.002)[:-1] + _simplify(pts[far:], 0.002)
        else:
            pts = _simplify(pts, 0.002)
        out[layer].append([[round(x, 4), round(y, 4)] for x, y in pts])
    return out


def _drop_town_name(landmarks: list[dict], town: str) -> list[dict]:
    """The town's own name is not a location inside the town.

    Stops and stations are often tagged just "Aluva" (with name:ml "ആലുവ"), so a message saying
    "Aluva railway station" would match the bus stop instead. Single-word aliases of landmarks
    named after the town are removed everywhere; such a landmark keeps a longer alias as its name
    ("Aluva Private Bus Stand") or is dropped.
    """
    if not town:
        return landmarks
    tl = town.lower()
    town_words = {a for lm in landmarks if lm["name"].lower() == tl for a in lm["aliases"] if " " not in a.strip()}
    town_words.add(town)
    out = []
    for lm in landmarks:
        aliases = [a for a in lm["aliases"] if a not in town_words]
        if not aliases:
            continue
        name = lm["name"] if lm["name"] not in town_words else max(aliases, key=len)
        out.append({**lm, "name": name, "aliases": sorted(set(aliases) | {name})})
    for i, lm in enumerate(out, 1):
        lm["id"] = f"L{i}"
    return out


# ---------------------------------------------------------------- build


def build_city(xml_text: str, opt: Optional[Options] = None, source: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    opt = opt or Options()
    nodes, ways, meta = parse_osm(xml_text)
    if opt.clip and meta.get("bounds"):
        nodes, ways = clip_to_bounds(nodes, ways, meta["bounds"])
    if not nodes:
        raise ValueError("no nodes in the OSM extract")
    lats = [v[0] for v in nodes.values()]
    lons = [v[1] for v in nodes.values()]
    proj = Projection((min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2)
    pos, edges = _road_graph(nodes, ways, proj, opt)
    pos, edges = _merge(pos, edges, opt.merge_km)
    pos, edges = _largest_component(pos, edges)
    if len(pos) < 6:
        raise ValueError(f"road network too small after simplification ({len(pos)} nodes); widen the area or lower --merge-km")

    # stable ids, west→east then north→south
    order = sorted(pos, key=lambda n: (round(pos[n][1], 2), pos[n][0]))
    nid = {osm: f"N{i + 1:03d}" for i, osm in enumerate(order)}
    land = {nid[o]: pos[o] for o in order}
    river = _resample(_river_line(nodes, ways, proj), opt.river_step_km)
    rpos = {f"R{i}": p for i, p in enumerate(river)}

    zones = _kmeans(land, max(1, min(opt.neighbourhoods, len(land))))
    places = [(p, t) for p, t in _feature_points(nodes, ways, proj) if t.get("place") in PLACE_TYPES]
    nb_list = []
    rline = list(river)
    zone_ids = sorted(set(zones.values()))
    dmax = max((_dist_to_line(p, rline) for p in land.values()), default=1.0) or 1.0
    cent = {}
    for z in zone_ids:
        members = [land[n] for n in land if zones[n] == z]
        cent[z] = (sum(p[0] for p in members) / len(members), sum(p[1] for p in members) / len(members))
    # each OSM place names only the one cluster it lies closest to; the rest are named by direction
    named: dict[int, str] = {}
    for pt, tags in sorted(places, key=lambda pt: pt[1]["name"]):
        z = min(cent, key=lambda k: _dist(pt, cent[k]))
        if z not in named and tags["name"] not in named.values() and _dist(pt, cent[z]) < 2.0:
            named[z] = tags["name"]
    town = opt.name.split(",")[0].strip()
    mx = sum(c[0] for c in cent.values()) / len(cent)
    my = sum(c[1] for c in cent.values()) / len(cent)
    for z in zone_ids:
        cx, cy = cent[z]
        name = named.get(z)
        if not name:
            dx, dy = cx - mx, cy - my
            if abs(dx) < 0.2 and abs(dy) < 0.2:
                d = "Central"
            else:
                d = "-".join(x for x in ("North" if dy < -0.2 else "South" if dy > 0.2 else "", "West" if dx < -0.2 else "East" if dx > 0.2 else "") if x)
            name = f"{town} {d}"
        if any(x["name"] == name for x in nb_list):
            name = f"{name} ({chr(65 + z)})"
        mem = [land[n] for n in land if zones[n] == z]
        mean_d = sum(_dist_to_line(p, rline) for p in mem) / len(mem)
        nb_list.append({"id": f"Z{z + 1}", "name": name, "flood_factor": round(0.8 + 0.4 * (1 - min(1.0, mean_d / dmax)), 3), "name_source": "osm place" if z in named else "generated"})

    def elevation(p: tuple[float, float]) -> float:
        return round(2.4 + 2.0 * min(_dist_to_line(p, rline), 2.0), 2) if rline else 3.5

    out_nodes = []
    for n, p in land.items():
        lat, lon = proj.latlon(*p)
        out_nodes.append({"id": n, "x": round(p[0], 4), "y": round(p[1], 4), "lat": round(lat, 6), "lon": round(lon, 6), "elevation": elevation(p),
                          "neighbourhood": f"Z{zones[n] + 1}", "kind": "land", "label": "", "provenance": "osm-derived"})
    for n, p in rpos.items():
        lat, lon = proj.latlon(*p)
        near = min(land, key=lambda m: _dist(land[m], p))
        out_nodes.append({"id": n, "x": round(p[0], 4), "y": round(p[1], 4), "lat": round(lat, 6), "lon": round(lon, 6), "elevation": 0.0,
                          "neighbourhood": f"Z{zones[near] + 1}", "kind": "river", "label": "river", "provenance": "osm-derived"})

    out_edges = []
    nbr = 0
    for (a, b), e in sorted(edges.items(), key=lambda kv: (nid[kv[0][0]], nid[kv[0][1]])):
        u, v = sorted((nid[a], nid[b]))
        pts = e.get("pts") or [land[nid[a]], land[nid[b]]]
        if nid[a] != u:
            pts = pts[::-1]
        geom = [[round(x, 4), round(y, 4)] for x, y in _simplify(pts, 0.004)] if len(pts) > 2 else None
        if e["bridge"]:
            nbr += 1
            out_edges.append({"id": f"BR{nbr}", "u": u, "v": v, "kind": "bridge", "length_km": round(e["len"], 3), "name": e["name"] or f"Bridge {nbr}", "clearance": round(3.0 + 0.4 * (nbr % 3), 2), "provenance": "osm (clearance scenario-assumed)", **({"geometry": geom} if geom else {})})
        else:
            out_edges.append({"id": f"E-{u}-{v}", "u": u, "v": v, "kind": "road", "length_km": round(e["len"], 3), "name": e["name"], "provenance": "osm-derived", **({"geometry": geom} if geom else {})})
    for i in range(len(river) - 1):
        out_edges.append({"id": f"E-R{i}-R{i + 1}", "u": f"R{i}", "v": f"R{i + 1}", "kind": "river", "length_km": round(_dist(river[i], river[i + 1]), 3), "name": "", "provenance": "osm-derived"})
    jetties = 0
    for r, p in rpos.items():
        near = min(land, key=lambda m: (_dist(land[m], p), m))
        if _dist(land[near], p) <= opt.jetty_max_km:
            jetties += 1
            out_edges.append({"id": f"E-{r}-{near}", "u": r, "v": near, "kind": "jetty", "length_km": round(_dist(land[near], p), 3), "name": "", "provenance": "scenario-assumed"})
    if rpos and jetties == 0:
        r, near = min(((r, m) for r in rpos for m in land), key=lambda rm: _dist(rpos[rm[0]], land[rm[1]]))
        out_edges.append({"id": f"E-{r}-{near}", "u": r, "v": near, "kind": "jetty", "length_km": round(_dist(land[near], rpos[r]), 3), "name": "", "provenance": "scenario-assumed"})
        jetties = 1

    feats = _feature_points(nodes, ways, proj)
    candidates: dict[str, str] = {}
    for p, t in feats:
        if t.get("amenity") in SHELTER_AMENITIES or t.get("building") in ("school", "civic"):
            near = min(land, key=lambda m: (_dist(land[m], p), m))
            if _dist(land[near], p) <= 0.4 and near not in candidates:
                candidates[near] = t["name"]
    if len(candidates) >= 3:
        picks = _farthest_points(sorted(candidates), land, 3, first=max(sorted(candidates), key=lambda n: elevation(land[n])))
        shelters = [{"id": f"S{i + 1}", "name": f"{candidates[n]} (hypothetical shelter)", "node": n, "provenance": "hypothetical: named OSM building, not a verified relief camp"} for i, n in enumerate(picks)]
    else:
        high = sorted(land, key=lambda n: (-elevation(land[n]), n))[: max(3, len(land) // 4)]
        picks = _farthest_points(high, land, 3, first=high[0])
        shelters = [{"id": f"S{i + 1}", "name": f"Hypothetical shelter {i + 1}", "node": n, "provenance": "hypothetical: chosen on high ground, no OSM building"} for i, n in enumerate(picks)]
    for s in shelters:
        nd = next(x for x in out_nodes if x["id"] == s["node"])
        nd["kind"], nd["label"] = "shelter", s["name"]

    landmarks = []
    for p, t in feats:
        if not any(t.get(k) for k in LANDMARK_KEYS) and t.get("place") not in PLACE_TYPES:
            continue
        near = min(land, key=lambda m: (_dist(land[m], p), m))
        if _dist(land[near], p) > 0.5:
            continue
        aliases = sorted({t[k].strip() for k in ALIAS_TAGS if t.get(k)})
        landmarks.append({"id": f"L{len(landmarks) + 1}", "name": t["name"], "node": near, "aliases": aliases, "type": next((t[k] for k in LANDMARK_KEYS if t.get(k)), t.get("place", "")), "provenance": "osm"})
    landmarks = _drop_town_name(landmarks, opt.name.split(",")[0].strip())
    for lm in landmarks:
        extra = opt.aliases.get(lm["name"], [])
        if extra:
            lm["aliases"] = sorted(set(lm["aliases"]) | set(extra))
            lm["added_aliases"] = sorted(extra)  # project-added, not from OSM

    boat_homes = [f"R{i}" for i in range(0, len(river), max(1, len(river) // 7))][:7] if river else []
    ground_homes = _farthest_points(sorted(land), land, 6)
    return {
        "format": "resqnet-city/1",
        "name": opt.name,
        "synthetic": opt.synthetic,
        "source": {
            "attribution": "© OpenStreetMap contributors" if not opt.synthetic else "Synthetic test fixture in OSM XML format (not real geography)",
            "license": "ODbL 1.0 (derived database: share-alike)" if not opt.synthetic else "Part of this repository",
            "osm_timestamp": meta["timestamp"], "generator": meta["generator"], **(source or {}),
            "projection": {"type": "local equirectangular, km", "lat0": round(proj.lat0, 6), "lon0": round(proj.lon0, 6)},
            "options": {"merge_km": opt.merge_km, "river_step_km": opt.river_step_km, "jetty_max_km": opt.jetty_max_km, "neighbourhoods": opt.neighbourhoods},
        },
        "assumptions": [
            "Elevation is a scenario-assumed proxy from distance to the river (no DEM used).",
            "Jetties (boat landing points) are scenario-assumed: nearest road node within the jetty radius of the river.",
            "Bridge clearances are scenario-assumed.",
            "Shelters are hypothetical, not verified relief camps.",
            "Road junctions closer than merge_km are merged; minor geometry is simplified.",
        ],
        "neighbourhoods": nb_list,
        "nodes": out_nodes,
        "edges": out_edges,
        "shelters": shelters,
        "boat_homes": boat_homes,
        "ground_homes": ground_homes,
        "landmarks": landmarks,
        "basemap": _basemap(nodes, ways, proj),
        "stats": {"land_nodes": len(land), "river_nodes": len(river), "roads": sum(1 for e in out_edges if e["kind"] == "road"), "bridges": nbr, "jetties": jetties, "landmarks": len(landmarks)},
    }


def overpass_query(south: float, west: float, north: float, east: float, road_types: Iterable[str] = ROAD_TYPES) -> str:
    bbox = f"{south},{west},{north},{east}"
    hw = "|".join(sorted(road_types))
    return (f'[out:xml][timeout:180];(way["highway"~"^({hw})$"]({bbox});way["waterway"~"^(river|canal)$"]({bbox});'
            f'node["name"]({bbox});way["amenity"]["name"]({bbox});way["building"]["name"]({bbox}););(._;>;);out body;')
