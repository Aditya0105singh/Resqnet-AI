#!/usr/bin/env python
"""Download a real flood event for a map and store it as a committed JSON snapshot.

Sources (free, no API key):
  * GloFAS v4 river-discharge reanalysis via the Open-Meteo Flood API (daily, ~5 km grid)
  * IMD gridded daily rainfall (0.25 degree, gauge-based; India Meteorological Department)
  * ERA5 reanalysis rainfall via the Open-Meteo Archive API (hourly), used for the diurnal shape

The simulator replays the discharge curve (time-compressed) as its river level, and uses the
rainfall to shape when SOS reports arrive. IMD is the observed product, so its daily totals
are kept and distributed over the day with ERA5's hourly pattern. Nothing here is observed
flood depth.

    python scripts/build_flood_event.py kerala_aluva
    python scripts/build_flood_event.py --list
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request

import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAPS = ROOT / "backend" / "app" / "data" / "maps"
OUT = ROOT / "backend" / "app" / "data" / "events"
UA = "resqnet-research/0.1 (educational flood-rescue simulation; one-off event snapshot)"

EVENTS = {
    "kerala_2018": {
        "name": "Kerala floods · August 2018",
        # four days from the start of the main rise (14 Aug) through the peak (16 Aug) and early recession
        "start": "2018-08-14",
        "end": "2018-08-18",
        "note": "Extreme monsoon rainfall and simultaneous dam releases drove the worst Kerala floods in about a century.",
    }
}


IMD_URL = "https://imdpune.gov.in/cmpg/Griddata/rainfall.php"
IMD_LAT0, IMD_LON0, IMD_STEP, IMD_NLAT, IMD_NLON = 6.5, 66.5, 0.25, 129, 135
CACHE = ROOT / "tmp" / "imd_cache"


def imd_year(year: int) -> np.ndarray:
    """IMD 0.25 degree daily rainfall (mm) for a year: array (days, 129 lat, 135 lon), NaN = missing."""
    days = 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365
    want = days * IMD_NLAT * IMD_NLON * 4
    path = CACHE / f"rain{year}.grd"
    if not path.exists() or path.stat().st_size != want:
        CACHE.mkdir(parents=True, exist_ok=True)
        print(f"downloading IMD rainfall {year} ({want // 1_000_000} MB) ...", flush=True)
        for attempt in range(4):
            try:
                req = urllib.request.Request(IMD_URL, data=urllib.parse.urlencode({"rain": year}).encode(), headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=280) as r:
                    body = r.read()
                if len(body) == want:
                    path.write_bytes(body)
                    break
                print(f"  unexpected size {len(body)} (want {want})", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"  retry {attempt + 1}: {e}", flush=True)
                time.sleep(5 * (attempt + 1))
        else:
            raise RuntimeError("IMD archive unavailable")
    a = np.fromfile(path, dtype="<f4").reshape(days, IMD_NLAT, IMD_NLON)
    return np.where(a < -900, np.nan, a)


def imd_point(grid: np.ndarray, doy: int, lat: float, lon: float) -> float:
    """Bilinear interpolation of one day's IMD grid at a point (NaN-safe)."""
    fi = (lat - IMD_LAT0) / IMD_STEP
    fj = (lon - IMD_LON0) / IMD_STEP
    i0, j0 = int(np.floor(fi)), int(np.floor(fj))
    num = den = 0.0
    for di in (0, 1):
        for dj in (0, 1):
            v = grid[doy, i0 + di, j0 + dj]
            if np.isnan(v):
                continue
            w = (1 - abs(fi - (i0 + di))) * (1 - abs(fj - (j0 + dj)))
            num += w * float(v)
            den += w
    return num / den if den else float("nan")


def get_json(url: str, params: dict) -> dict:
    full = url + "?" + urllib.parse.urlencode(params)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(full, headers={"User-Agent": UA}), timeout=60) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            print(f"  retry {attempt + 1}: {e}", flush=True)
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"unavailable: {url}")


def build(map_id: str, event_id: str) -> dict:
    ev = EVENTS[event_id]
    snap = json.loads((MAPS / f"{map_id}.json").read_text(encoding="utf-8"))
    lat, lng = snap["origin"]
    # GloFAS needs a few days of lead-in so the daily series is not clipped at the window edges
    d0 = datetime.fromisoformat(ev["start"]) - timedelta(days=1)
    d1 = datetime.fromisoformat(ev["end"]) + timedelta(days=1)
    q = get_json(
        "https://flood-api.open-meteo.com/v1/flood",
        {"latitude": lat, "longitude": lng, "daily": "river_discharge", "start_date": d0.date().isoformat(), "end_date": d1.date().isoformat()},
    )
    r = get_json(
        "https://archive-api.open-meteo.com/v1/archive",
        {"latitude": lat, "longitude": lng, "hourly": "precipitation", "start_date": ev["start"], "end_date": (datetime.fromisoformat(ev["end"]) - timedelta(days=1)).date().isoformat(), "timezone": "Asia/Kolkata"},
    )
    days = q["daily"]["time"]
    disc = [float(v) for v in q["daily"]["river_discharge"]]
    # daily values are centred on the day: interpolate linearly to hourly across the window
    t_days = [datetime.fromisoformat(d) + timedelta(hours=12) for d in days]
    hours = []
    t = datetime.fromisoformat(ev["start"])
    end = datetime.fromisoformat(ev["end"])
    while t < end:
        hours.append(t)
        t += timedelta(hours=1)
    hourly_q = []
    for h in hours:
        for i in range(len(t_days) - 1):
            if t_days[i] <= h <= t_days[i + 1]:
                f = (h - t_days[i]) / (t_days[i + 1] - t_days[i])
                hourly_q.append(round(disc[i] + (disc[i + 1] - disc[i]) * f, 1))
                break
        else:
            hourly_q.append(round(disc[0] if h < t_days[0] else disc[-1], 1))
    era = [float(v or 0.0) for v in r["hourly"]["precipitation"]][: len(hours)]
    era += [0.0] * (len(hours) - len(era))
    # observed daily totals (IMD) distributed over each day with ERA5's hourly shape
    year = datetime.fromisoformat(ev["start"]).year
    grid = imd_year(year)
    rain: list[float] = []
    daily_imd: dict[str, float] = {}
    daily_era: dict[str, float] = {}
    for d0_ in sorted({h.date() for h in hours}):
        idx = [i for i, h in enumerate(hours) if h.date() == d0_]
        doy = (d0_ - datetime(year, 1, 1).date()).days
        imd_mm = imd_point(grid, doy, lat, lng)
        era_mm = sum(era[i] for i in idx)
        daily_imd[d0_.isoformat()] = round(imd_mm, 1)
        daily_era[d0_.isoformat()] = round(era_mm, 1)
        for i in idx:
            if np.isnan(imd_mm):
                rain.append(round(era[i], 2))
            elif era_mm > 2.0:
                rain.append(round(era[i] * imd_mm / era_mm, 2))
            else:
                rain.append(round(imd_mm / len(idx), 2))
    peak_i = max(range(len(hourly_q)), key=lambda i: hourly_q[i])
    return {
        "id": event_id,
        "map": map_id,
        "name": ev["name"],
        "note": ev["note"],
        "point": {"requested": [lat, lng], "glofas_cell": [q.get("latitude"), q.get("longitude")]},
        "source": {
            "discharge": "GloFAS v4 river discharge reanalysis (Copernicus / ECMWF) via Open-Meteo Flood API",
            "rainfall": "IMD 0.25 degree gauge-based daily rainfall (India Meteorological Department), distributed hourly with the ERA5 pattern",
            "built": time.strftime("%Y-%m-%d"),
        },
        "start": ev["start"],
        "hours": len(hours),
        "baseline_m3s": min(hourly_q),
        "peak_m3s": max(hourly_q),
        "peak_time": hours[peak_i].isoformat(timespec="minutes"),
        "rain_total_mm": round(sum(rain), 1),
        "rain_daily_imd_mm": daily_imd,
        "rain_daily_era5_mm": daily_era,
        "discharge_m3s": hourly_q,
        "rain_mm_h": rain,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("map", nargs="?", default="kerala_aluva")
    ap.add_argument("--event", default="kerala_2018")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        for k, v in EVENTS.items():
            print(k, v["name"], v["start"], "->", v["end"])
        return
    data = build(a.map, a.event)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{a.event}__{a.map}.json"
    path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {path.name}: {data['hours']} h, discharge {data['baseline_m3s']:.0f} -> {data['peak_m3s']:.0f} m3/s (peak {data['peak_time']}), rain {data['rain_total_mm']} mm, GloFAS cell {data['point']['glofas_cell']}")


if __name__ == "__main__":
    sys.exit(main())
