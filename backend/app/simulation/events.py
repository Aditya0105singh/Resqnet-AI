"""Real flood events (committed snapshots from scripts/build_flood_event.py).

An event supplies an hourly river-discharge curve (GloFAS) and hourly rainfall (ERA5) for a
map. The simulator replays the discharge, time-compressed onto the scenario's ticks, as the
river-level ramp, and uses rainfall to shape when SOS reports arrive. Water depths themselves
remain the simulator's threshold model: nothing here is observed inundation.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

EVENTS_DIR = Path(__file__).resolve().parent.parent / "data" / "events"


@lru_cache(maxsize=16)
def _read(event_id: str, map_id: str) -> Optional[dict[str, Any]]:
    path = EVENTS_DIR / f"{event_id}__{map_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _at(series: list[float], pos: float) -> float:
    i = max(0, min(len(series) - 1, int(pos)))
    j = min(len(series) - 1, i + 1)
    f = max(0.0, min(1.0, pos - i))
    return series[i] + (series[j] - series[i]) * f


def load_event(event_id: str, map_id: str, duration: int) -> Optional[dict[str, Any]]:
    """Per-tick curves for an event on a map, or None when there is no data for that pair."""
    if not event_id:
        return None
    raw = _read(event_id, map_id)
    if raw is None:
        return None
    n = raw["hours"]
    q = raw["discharge_m3s"]
    lo, hi = min(q), max(q)
    span = max(hi - lo, 1e-9)
    ticks = max(1, duration)
    discharge = [round(_at(q, t / ticks * (n - 1)), 1) for t in range(ticks + 1)]
    curve = [round((d - lo) / span, 4) for d in discharge]
    rain = [_at(raw["rain_mm_h"], t / ticks * (n - 1)) for t in range(ticks + 1)]
    start = datetime.fromisoformat(raw["start"])
    return {
        "id": raw["id"],
        "name": raw["name"],
        "note": raw.get("note", ""),
        "source": raw["source"],
        "start": raw["start"],
        "hours": n,
        "real_hours_per_tick": round((n - 1) / ticks, 3),
        "baseline_m3s": lo,
        "peak_m3s": hi,
        "peak_time": raw["peak_time"],
        "rain_total_mm": raw.get("rain_total_mm"),
        "rain_daily_mm": raw.get("rain_daily_imd_mm"),
        "glofas_cell": raw.get("point", {}).get("glofas_cell"),
        "discharge": discharge,
        "curve": curve,
        "rain": rain,
        "time_at": [(start + timedelta(hours=t / ticks * (n - 1))).isoformat(timespec="minutes") for t in range(ticks + 1)],
    }
