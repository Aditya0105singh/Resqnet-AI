"""After-action report — assembled only from the run's own state, events and metrics."""
from __future__ import annotations

import io
from typing import Any

from ..analysis.runs import rebuild
from ..metrics.metrics import SUMMARY_KEYS, compute_metrics
from ..simulation.engine import Engine

COMMON_LIMITATIONS = [
    "The flood model is a simplified threshold model, not hydraulic forecasting.",
    "Report confidence is a noisy-OR heuristic over source reliability metadata, not a calibrated probability.",
    "Cost weights are proposed starting values, not trained or validated parameters.",
    "Results describe this simulator only and must not be used for operational emergency dispatch.",
]


def limitations_for(world: Any) -> list[str]:
    """What is real and what is simulated, for the map this run used."""
    ev = world.meta.get("flood_event")
    if world.meta.get("real"):
        return [
            f"Road, bridge and river geometry for {world.meta.get('name', 'this area')} come from OpenStreetMap contributors and were simplified to a coarse junction graph; "
            "OSM may be incomplete or out of date.",
            "Terrain is sampled from a 90 m Copernicus DEM and mapped monotonically into the simulator's water-level frame; node elevations are not survey-grade.",
            "Bridge deck clearances, shelter capacities, unit positions, people counts and SOS reports are assumed or generated from a seed, not observed.",
            (
                f"River discharge replays the {ev['name']} GloFAS reanalysis, time-compressed ({ev['real_hours_per_tick']:.2f} real hours per tick); rainfall shapes SOS arrivals. "
                "Inundation depths are still produced by the simulator's threshold model and are not observed flood extent."
                if ev
                else "Flood depths come from a synthetic rise and are not calibrated to any historical event."
            ),
        ] + COMMON_LIMITATIONS
    return ["Riverbend is a synthetic city; geography, people counts and reports are generated from a seed."] + COMMON_LIMITATIONS


def build_report(engine: Engine, sim_id: str, compare: bool = True) -> dict[str, Any]:
    m = compute_metrics(engine)
    w = engine.world
    critical = [
        {"tick": a.tick, "category": a.category, "message": a.message, "severity": a.severity}
        for a in engine.audit_log
        if a.severity in ("critical",) or (a.category == "event" and a.severity == "ok" and "Recovered" in a.message)
    ]
    outcomes = []
    for i in sorted(w.incidents.values(), key=lambda i: i.id):
        outcomes.append(
            {
                "id": i.id,
                "neighbourhood": w.neighbourhoods[i.neighbourhood].name,
                "urgency": i.urgency,
                "status": i.status,
                "reported": i.reported_tick,
                "first_pickup": i.first_pickup_tick,
                "completed": i.completed_tick,
                "rescued": i.people_rescued,
                "waiting": i.people_estimate if i.status not in ("RESCUED", "FALSE_ALARM") else 0,
                "deadline": i.deadline_tick,
                "missed_deadline": i.urgency >= 4 and ((i.first_pickup_tick or 10**6) > i.deadline_tick) and (i.first_pickup_tick is not None or w.tick > i.deadline_tick),
            }
        )
    resources = [
        {
            "id": r.id,
            "name": r.name,
            "kind": r.kind,
            "status": r.status,
            "busy_ticks": r.busy_ticks,
            "idle_ticks": r.idle_ticks,
            "distance_km": round(r.distance_km, 1),
            "missions": sum(1 for a in w.assignments.values() if a.resource_id == r.id and a.status == "COMPLETED"),
            "cancelled": sum(1 for a in w.assignments.values() if a.resource_id == r.id and a.status == "CANCELLED"),
        }
        for r in sorted(w.resources.values(), key=lambda r: r.id)
    ]
    key_decisions = [
        {"id": d["id"], "tick": d["tick"], "incident": d["incident_id"], "outcome": d["outcome"], "explanation": d.get("explanation", "")}
        for d in engine.decisions.values()
        if d["outcome"] in ("SAFETY_REJECTED", "NO_SHELTER") or (d["outcome"] == "COMMITTED" and d["incident_id"] in {x for dd in engine.disruptions for x in dd["incidents"]})
    ][:30]
    comparison = []
    if compare:
        for strat in ("decentralized", "centralized", "greedy"):
            if strat == engine.strategy:
                cm = m
            else:
                other = rebuild(engine.base_cfg, strat, engine.injected, engine.world.tick)
                cm = compute_metrics(other)
            comparison.append({"strategy": strat, **{k: cm[k] for k in SUMMARY_KEYS}, "same_events": True})
    safety = {
        "route_violations": m["route_violations"],
        "invariant_violations": m["invariant_violations"],
        "commit_rejections": m["safety_rejections"],
        "movement_blocks": m["blocked_moves"],
        "by_code": _count([s.get("code") or s["type"] for s in engine.safety_log]),
    }
    lessons = _lessons(m, engine)
    return {
        "simulation_id": sim_id,
        "title": f"After-Action Report — {engine.cfg.name}",
        "disclaimer": "Research and educational simulation. Real map data with simulated floods and incidents. Not an operational emergency-dispatch system." if w.meta.get("real") else "Research and educational simulation. Synthetic data. Not an operational emergency-dispatch system.",
        "scenario": {"key": engine.cfg.key, "name": engine.cfg.name, "description": engine.cfg.description, "seed": engine.cfg.seed, "strategy": engine.strategy, "policy": engine.cfg.policy, "weights": engine.cfg.weights, "comm_delay": engine.cfg.comm_delay, "duration": engine.cfg.duration, "ticks_run": w.tick},
        "metrics": m,
        "critical_timeline": critical[:80],
        "disruptions": engine.disruptions,
        "outcomes": outcomes,
        "resources": resources,
        "shelters": [{"id": s.id, "name": s.name, "capacity": s.capacity, "occupancy": s.occupancy} for s in w.shelters.values()],
        "key_decisions": key_decisions,
        "safety": safety,
        "strategy_comparison": comparison,
        "injected_events": engine.injected,
        "lessons": lessons,
        "limitations": limitations_for(w),
    }


def _count(xs: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in xs:
        out[x] = out.get(x, 0) + 1
    return out


def _lessons(m: dict[str, Any], engine: Engine) -> list[str]:
    out = []
    worst = max((n for n in m["fairness_by_neighbourhood"] if n["mean_wait"] is not None), key=lambda n: n["mean_wait"], default=None)
    if worst:
        out.append(f"{worst['name']} had the longest mean wait ({worst['mean_wait']} min) across {worst['incidents']} incidents.")
    if m["unmet_people"]:
        shelters_full = all(s.occupancy >= s.capacity for s in engine.world.shelters.values())
        out.append(f"{m['unmet_people']} people were not delivered to a shelter by t={m['tick']}" + (" — shelter capacity was exhausted." if shelters_full else "."))
    if m["deadline_misses"]:
        out.append(f"{m['deadline_misses']} urgent incidents missed their response deadline.")
    rec = [d for d in engine.disruptions if d["recovery"] is not None]
    if rec:
        slow = max(rec, key=lambda d: d["recovery"])
        out.append(f"Slowest recovery: {slow['type']} at t={slow['tick']} took {slow['recovery']} min to re-cover affected demand.")
    if m["false_alarm_visits"]:
        out.append(f"{m['false_alarm_visits']} trips were spent verifying reports that proved false.")
    if m["route_violations"] == 0 and m["invariant_violations"] == 0:
        out.append("No route or capacity invariant was violated; the shield blocked every unsafe move or commit.")
    return out


def report_pdf(rep: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm, title=rep["title"])
    ss = getSampleStyleSheet()
    h1, h2, body = ss["Title"], ss["Heading2"], ss["BodyText"]
    small = ss["BodyText"].clone("small", fontSize=8, leading=10)
    story: list[Any] = [Paragraph(rep["title"], h1), Paragraph(rep["disclaimer"], small), Spacer(1, 6)]
    sc = rep["scenario"]
    story.append(Paragraph(f"Scenario <b>{sc['name']}</b> · seed {sc['seed']} · strategy <b>{sc['strategy']}</b> · policy {sc['policy']} · comms delay {sc['comm_delay']} · ticks {sc['ticks_run']}/{sc['duration']}", body))

    def table(rows: list[list[Any]], widths: list[float] | None = None) -> Table:
        t = Table([[Paragraph(str(c), small) for c in r] for r in rows], colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111111")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d4d4d4")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        return t

    m = rep["metrics"]
    story += [Spacer(1, 8), Paragraph("Outcome metrics", h2)]
    story.append(table([["Metric", "Value"]] + [[k.replace("_", " "), m[k]] for k in ("people_rescued", "unmet_people", "mean_time_to_service", "median_time_to_service", "deadline_misses", "utilisation", "idle_with_demand_ticks", "fairness_jain", "reassignments", "reroutes", "route_violations", "safety_rejections", "negotiation_messages", "mean_recovery_time")], [70 * mm, 60 * mm]))
    story += [Spacer(1, 8), Paragraph("Fairness by neighbourhood", h2)]
    story.append(table([["Neighbourhood", "Incidents", "Served", "Mean wait", "Max wait", "Deadline misses"]] + [[n["name"], n["incidents"], n["served"], n["mean_wait"], n["max_wait"], n["deadline_misses"]] for n in m["fairness_by_neighbourhood"]]))
    if rep["strategy_comparison"]:
        story += [Spacer(1, 8), Paragraph("Strategy comparison (same seed, same events)", h2)]
        story.append(table([["Strategy", "Mean TTS", "Misses", "Unmet", "Fairness", "Messages"]] + [[c["strategy"], c["mean_time_to_service"], c["deadline_misses"], c["unmet_people"], c["fairness_jain"], c["negotiation_messages"]] for c in rep["strategy_comparison"]]))
    story += [Spacer(1, 8), Paragraph("Lessons from this run", h2)] + [Paragraph("• " + x, body) for x in rep["lessons"]]
    story += [Spacer(1, 8), Paragraph("Critical timeline", h2)]
    story.append(table([["t", "Category", "Event"]] + [[e["tick"], e["category"], e["message"]] for e in rep["critical_timeline"][:40]], [12 * mm, 22 * mm, 140 * mm]))
    if rep["key_decisions"]:
        story += [Spacer(1, 8), Paragraph("Key decisions", h2)]
        story.append(table([["Decision", "t", "Incident", "Outcome", "Explanation"]] + [[d["id"], d["tick"], d["incident"], d["outcome"], d["explanation"][:400]] for d in rep["key_decisions"][:15]], [18 * mm, 10 * mm, 16 * mm, 24 * mm, 108 * mm]))
    story += [Spacer(1, 8), Paragraph("Limitations", h2)] + [Paragraph("• " + x, body) for x in rep["limitations"]]
    doc.build(story)
    return buf.getvalue()
