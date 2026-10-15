#!/usr/bin/env python
"""Validate the simulator's flood footprint against an observed Sentinel-1 water mask.

Observed side: Sentinel-1 RTC VV backscatter (Microsoft Planetary Computer, no account needed).
Change detection between a pre-flood scene and a post-peak scene of the SAME relative orbit
(3x3 mean-despeckled VV in dB):
    flooded = VV(post) - VV(pre) < -drop  and  VV(post) < dark
Shallow water among vegetation and buildings rarely reaches open-water levels (< -17 dB), so a
pure absolute threshold misses most of it; the darkening against the pre-flood pass is the signal.
Model side: the simulator's water-depth model run at the river discharge GloFAS reports for the
satellite pass time (same mapping the replay scenario uses).

Reported per map: confusion matrix / precision / recall / F1 at the node level, ranking skill
(AUC of model depth vs observed wetness) and how that compares with two naive baselines.

    python scripts/validate_flood.py kerala_aluva
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds as tf_from_bounds
from rasterio.warp import transform as warp_transform, transform_bounds
from rasterio.windows import from_bounds
from scipy.ndimage import uniform_filter
from scipy.stats import rankdata, spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.simulation.engine import Engine  # noqa: E402
from app.simulation.events import _read as read_event  # noqa: E402
from app.simulation.flood import BOAT_MIN_DEPTH, update_flood  # noqa: E402
from app.simulation.scenarios import get_preset  # noqa: E402

PC = "https://planetarycomputer.microsoft.com/api"
CACHE = ROOT / "tmp" / "s1_cache"  # scenes and API answers, so repeated runs don't hit rate limits
UA = "resqnet-research/0.1 (educational flood-rescue simulation; validation)"


def jget(url: str, body: dict | None = None, cache: bool = True) -> dict:
    import hashlib

    key = CACHE / ("q_" + hashlib.sha1((url + json.dumps(body, sort_keys=True)).encode()).hexdigest()[:20] + ".json")
    if cache and key.exists():
        return json.loads(key.read_text())
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "content-type": "application/json"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                out = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 4:
                raise
            import time

            time.sleep(15 * (attempt + 1))
    if cache:
        CACHE.mkdir(parents=True, exist_ok=True)
        key.write_text(json.dumps(out))
    return out


def find_scene(bbox, day: str, orbit_state: str, rel_orbit: int | None) -> dict:
    d0 = datetime.fromisoformat(day)
    res = jget(f"{PC}/stac/v1/search", {"collections": ["sentinel-1-rtc"], "bbox": list(bbox), "datetime": f"{d0.date()}T00:00:00Z/{(d0 + timedelta(days=1)).date()}T00:00:00Z", "limit": 20})
    for f in res["features"]:
        p = f["properties"]
        if p.get("sat:orbit_state") == orbit_state and (rel_orbit is None or p.get("sat:relative_orbit") == rel_orbit):
            return f
    raise RuntimeError(f"no Sentinel-1 {orbit_state} scene on {day}")


def read_vv(item: dict, bbox, px_m: float = 40.0):
    tag = CACHE / f"{item['id']}_{'_'.join(f'{x:.3f}' for x in bbox)}_{px_m:.0f}.npz"
    if tag.exists():
        z = np.load(tag, allow_pickle=False)
        return z["arr"], tuple(z["ext"]), rasterio.crs.CRS.from_string(str(z["crs"]))
    href = item["assets"]["vv"]["href"]
    u = urllib.parse.urlparse(href)
    tok = jget(f"{PC}/sas/v1/token/{u.netloc.split('.')[0]}/{u.path.split('/')[1]}", cache=False)["token"]
    with rasterio.open(href + "?" + tok) as ds:
        l, b, r, t = transform_bounds("EPSG:4326", ds.crs, *bbox)
        w = from_bounds(l, b, r, t, ds.transform)
        h, wd = max(8, int(round((t - b) / px_m))), max(8, int(round((r - l) / px_m)))
        arr = ds.read(1, window=w, out_shape=(h, wd), resampling=Resampling.average, boundless=True, fill_value=np.nan).astype("float32")
        CACHE.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(tag, arr=arr, ext=np.array([l, b, r, t]), crs=np.array(ds.crs.to_string()))
        return arr, (l, b, r, t), ds.crs


def to_db(lin: np.ndarray) -> np.ndarray:
    lin = np.where(np.isfinite(lin) & (lin > 0), lin, np.nan)
    sm = uniform_filter(np.nan_to_num(lin, nan=np.nanmedian(lin)), size=3)
    return 10 * np.log10(np.clip(sm, 1e-6, None))


def discharge_at(map_id: str, when: datetime) -> float:
    ev = read_event("kerala_2018", map_id)
    lat, lng = ev["point"]["requested"]
    d0, d1 = (when - timedelta(days=3)).date(), (when + timedelta(days=3)).date()
    q = jget(f"https://flood-api.open-meteo.com/v1/flood?latitude={lat}&longitude={lng}&daily=river_discharge&start_date={d0}&end_date={d1}")["daily"]
    pts = [(datetime.fromisoformat(t).replace(tzinfo=timezone.utc) + timedelta(hours=12), v) for t, v in zip(q["time"], q["river_discharge"])]
    for (ta, va), (tb, vb) in zip(pts, pts[1:]):
        if ta <= when <= tb:
            return va + (vb - va) * (when - ta) / (tb - ta)
    return pts[-1][1]


def auc(score: np.ndarray, positive: np.ndarray) -> float:
    pos, neg = score[positive], score[~positive]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    r = rankdata(np.concatenate([pos, neg]))
    return float((r[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def prf(pred: np.ndarray, obs: np.ndarray) -> dict:
    tp = int((pred & obs).sum()); fp = int((pred & ~obs).sum()); fn = int((~pred & obs).sum()); tn = int((~pred & ~obs).sum())
    p = tp / (tp + fp) if tp + fp else float("nan")
    r = tp / (tp + fn) if tp + fn else float("nan")
    f1 = 2 * p * r / (p + r) if p == p and r == r and p + r else float("nan")
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": p, "recall": r, "f1": f1, "accuracy": (tp + tn) / max(1, tp + fp + fn + tn)}


def validate(map_id: str, pre_day: str, post_day: str, orbit_state: str, thr: float, rel_orbit: int | None, wet_frac: float, drop: float = 3.0, radius_m: float = 120.0) -> dict:
    snap = json.loads((ROOT / "backend" / "app" / "data" / "maps" / f"{map_id}.json").read_text(encoding="utf-8"))
    s, w, n, e = snap["bbox"]
    bbox = (w, s, e, n)  # lon/lat order
    pre = find_scene(bbox, pre_day, orbit_state, rel_orbit)
    ro = pre["properties"].get("sat:relative_orbit")
    post = find_scene(bbox, post_day, orbit_state, ro)
    a_pre, ext, crs = read_vv(pre, bbox)
    a_post, _, _ = read_vv(post, bbox)
    h = min(a_pre.shape[0], a_post.shape[0]); wd = min(a_pre.shape[1], a_post.shape[1])
    db_pre, db_post = to_db(a_pre[:h, :wd]), to_db(a_post[:h, :wd])
    valid = np.isfinite(a_pre[:h, :wd]) & np.isfinite(a_post[:h, :wd])
    flooded = ((db_post - db_pre) < -drop) & (db_post < thr) & valid
    # node sampling: fraction of observed flooded pixels within radius_m of each junction
    l, b, r, t = ext
    lats = [x["lat"] for x in snap["nodes"] if x["kind"] != "river"]
    lons = [x["lng"] for x in snap["nodes"] if x["kind"] != "river"]
    ids = [x["id"] for x in snap["nodes"] if x["kind"] != "river"]
    xs, ys = warp_transform("EPSG:4326", crs, lons, lats)
    pw, ph = (r - l) / wd, (t - b) / h
    obs = []
    for x, y in zip(xs, ys):
        c, rr = int((x - l) / pw), int((t - y) / ph)
        k = max(1, int(round(radius_m / pw)))
        win = flooded[max(0, rr - k) : rr + k + 1, max(0, c - k) : c + k + 1]
        obs.append(float(win.mean()) if win.size else np.nan)
    obs = np.array(obs)
    keep = np.isfinite(obs)
    # model at the discharge for the pass time
    when = datetime.fromisoformat(post["properties"]["datetime"].replace("Z", "+00:00"))
    q_obs = discharge_at(map_id, when)
    ev = read_event("kerala_2018", map_id)
    lo, hi = min(ev["discharge_m3s"]), max(ev["discharge_m3s"])
    c = float(np.clip((q_obs - lo) / (hi - lo), 0, 1))
    eng = Engine(get_preset("kerala_2018", map=map_id), "decentralized", record_frames=False)
    wd_ = eng.world
    wd_.flood_curve = [c]
    wd_.tick = 0
    update_flood(wd_, eng.cfg.flood_severity, eng.cfg.flood_peak_tick)
    depth = np.array([wd_.nodes[i].depth for i in ids])
    elev = np.array([wd_.nodes[i].elevation for i in ids])
    # baseline: distance to the nearest river node (closer = wetter)
    rn = [(x.lat, x.lng) for x in wd_.nodes.values() if x.kind == "river"]
    dist = np.array([min(np.hypot((wd_.nodes[i].lat - la) * 110.6, (wd_.nodes[i].lng - lo_) * 109.6) for la, lo_ in rn) for i in ids])
    wet = obs >= wet_frac
    wet_k, depth_k, elev_k, dist_k, obs_k = wet[keep], depth[keep], elev[keep], dist[keep], obs[keep]
    model_wet = depth_k >= 0.30
    rho = spearmanr(depth_k, obs_k)
    return {
        "map": map_id,
        "pre": pre["id"][:48], "post": post["id"][:48], "relative_orbit": ro, "orbit": orbit_state, "dark_threshold_db": thr, "darkening_db": drop, "wet_fraction": wet_frac, "radius_m": radius_m,
        "post_time": post["properties"]["datetime"], "discharge_m3s": round(q_obs), "ramp_c": round(c, 3), "river_level_model_m": round(1.0 + eng.cfg.flood_severity * 2.0 * (0.35 + 0.65 * c), 2),
        "nodes": int(keep.sum()), "observed_wet": int(wet_k.sum()), "model_wet": int(model_wet.sum()),
        "observed_flooded_area_km2": round(float(flooded.sum()) * pw * ph / 1e6, 2), "scene_area_km2": round(float(valid.sum()) * pw * ph / 1e6, 1),
        "confusion": prf(model_wet, wet_k),
        "auc_model_depth": auc(depth_k, wet_k), "auc_inverse_elevation": auc(-elev_k, wet_k), "auc_inverse_river_distance": auc(-dist_k, wet_k),
        "spearman_depth_vs_observed_fraction": float(rho.correlation) if rho.correlation == rho.correlation else None,
        "base_rate": float(wet_k.mean()),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("map", nargs="?", default="kerala_aluva")
    ap.add_argument("--pre", default="2018-08-09")
    ap.add_argument("--post", default="2018-08-21")
    ap.add_argument("--orbit", default="descending")
    ap.add_argument("--rel-orbit", type=int, default=None)
    ap.add_argument("--threshold", type=float, default=-10.0, help="post-flood VV must be darker than this (dB)")
    ap.add_argument("--drop", type=float, default=3.0, help="required darkening vs the pre-flood pass (dB)")
    ap.add_argument("--wet-fraction", type=float, default=0.2)
    ap.add_argument("--radius", type=float, default=400.0, help="neighbourhood around each junction (m)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    res = validate(a.map, a.pre, a.post, a.orbit, a.threshold, a.rel_orbit, a.wet_fraction, a.drop, a.radius)
    print(json.dumps(res, indent=2) if a.json else res)


if __name__ == "__main__":
    main()
