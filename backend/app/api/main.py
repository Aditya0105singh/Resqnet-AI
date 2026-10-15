"""RESQNET AI — FastAPI application (REST + WebSocket).

The backend is the single authoritative source of simulation state. The UI only
renders frames it receives here; every user action is an event validated by the
engine and logged for exact replay.
"""
from __future__ import annotations

import asyncio
import copy
import json
import os
import time
import uuid
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from ..analysis.runs import adversarial, benchmark, counterfactual, rebuild, verify_replay
from ..metrics.metrics import compute_metrics
from ..persistence import store
from ..routing.router import believed_closed
from ..simulation.engine import EVENT_TYPES, Engine, EventError
from ..simulation.scenarios import POLICIES, PRESETS, STRATEGIES, ScenarioConfig, get_preset
from ..simulation.maps import available_maps, is_known
from ..simulation.serialize import static_world
from ..simulation.world import available_geographies
from ..simulation.state import ResourceStatus
from .report import build_report, report_pdf
from ..intelligence.extract import analyse, fingerprint
from ..intelligence.geocode import Gazetteer
from ..intelligence import commander

app = FastAPI(title="RESQNET AI", version="1.0.0", description="Multi-agent flood rescue coordination digital twin (synthetic research simulation).")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SPEEDS = (0.5, 1, 2, 4, 8, 16)


# ================================================================ errors
def err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


@app.exception_handler(HTTPException)
async def http_error(_req: Any, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "ERROR", "message": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content={"error": detail})


# ================================================================ sessions
class Session:
    def __init__(self, sim_id: str, cfg: ScenarioConfig, strategy: str):
        self.id = sim_id
        self.cfg = cfg
        self.strategy = strategy
        self.engine = Engine(copy.deepcopy(cfg), strategy)
        self.status = "ready"
        self.speed = 2.0
        self.task: Optional[asyncio.Task] = None
        self.clients: set[WebSocket] = set()
        self.msg_seq = 0
        self._audit_sent = 0
        self._round_sent = 0
        self.created = time.time()

    def summary(self) -> dict[str, Any]:
        e = self.engine
        return {
            "id": self.id,
            "scenario": self.cfg.key,
            "scenario_name": self.cfg.name,
            "strategy": self.strategy,
            "status": self.status,
            "speed": self.speed,
            "tick": e.world.tick,
            "duration": self.cfg.duration,
            "version": e.world.version,
            "seed": self.cfg.seed,
            "map": self.cfg.map,
            "map_name": e.world.meta.get("name", self.cfg.map),
            "flood_event": e.world.meta.get("flood_event"),
            "config": self.cfg.to_dict(),
            "injected": e.injected,
        }

    def persist(self) -> None:
        try:
            store.save_simulation(self.id, self.cfg.key, self.strategy, self.cfg.to_dict(), self.engine.injected, self.engine.world.tick, self.status, compute_metrics(self.engine) if self.engine.finished else None)
        except Exception:  # persistence must never break the live simulation
            pass

    def delta_message(self, kind: str = "frame") -> dict[str, Any]:
        e = self.engine
        self.msg_seq += 1
        audit = e.audit_log[self._audit_sent :]
        self._audit_sent = len(e.audit_log)
        rounds = e.rounds[self._round_sent :]
        self._round_sent = len(e.rounds)
        return {
            "type": kind,
            "seq": self.msg_seq,
            "sim_id": self.id,
            "status": self.status,
            "speed": self.speed,
            "state_version": e.world.version,
            "event_id": e.events[-1].id if e.events else None,
            "frame": e.last_frame(),
            "audit": [_audit_dict(a) for a in audit[-200:]],
            "rounds": [r.to_dict(with_messages=False) for r in rounds[-50:]],
        }

    def full_message(self, kind: str) -> dict[str, Any]:
        """Non-advancing snapshot used for (re)connects; broadcasts stay incremental."""
        e = self.engine
        return {
            "type": kind,
            "seq": self.msg_seq,
            "sim_id": self.id,
            "status": self.status,
            "speed": self.speed,
            "state_version": e.world.version,
            "event_id": e.events[-1].id if e.events else None,
            "frame": e.last_frame(),
            "summary": self.summary(),
            "audit": [_audit_dict(a) for a in e.audit_log[-200:]],
            "rounds": [r.to_dict(with_messages=False) for r in e.rounds[-40:]],
            "full": True,
        }

    async def broadcast(self, kind: str = "frame") -> None:
        if not self.clients:
            self._audit_sent = len(self.engine.audit_log)
            self._round_sent = len(self.engine.rounds)
            return
        msg = json.dumps(self.delta_message(kind), default=str)
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    async def run_loop(self) -> None:
        try:
            while self.status == "running":
                self.engine.step()
                if self.engine.finished:
                    self.status = "finished"
                    self.persist()
                await self.broadcast()
                if self.engine.world.tick % 10 == 0:
                    self.persist()
                if self.status != "running":
                    break
                await asyncio.sleep(1.0 / self.speed)
        except asyncio.CancelledError:
            pass


SESSIONS: dict[str, Session] = {}
JOBS: dict[str, dict[str, Any]] = {}


def _audit_dict(a: Any) -> dict[str, Any]:
    return {"id": a.id, "tick": a.tick, "category": a.category, "message": a.message, "refs": a.refs, "state_version": a.state_version, "severity": a.severity}


def get_session(sim_id: str) -> Session:
    s = SESSIONS.get(sim_id)
    if s:
        return s
    rec = store.load_simulation(sim_id)
    if not rec:
        raise err(404, "NOT_FOUND", f"simulation {sim_id} not found")
    # event-sourced restore: rebuild the run from its config + injected-event log
    cfg = ScenarioConfig.from_dict(rec["config"])
    s = Session(sim_id, cfg, rec["strategy"])
    s.engine = rebuild(cfg, rec["strategy"], rec["injected"], rec["tick"], record_frames=True)
    s.status = "finished" if s.engine.finished else "paused"
    SESSIONS[sim_id] = s
    return s


# ================================================================ models
class CreateSimulation(BaseModel):
    scenario: str = "normal"
    strategy: str = "decentralized"
    seed: Optional[int] = None
    overrides: dict[str, Any] = Field(default_factory=dict)
    map: Optional[str] = None  # map source id; see GET /api/maps


class EventIn(BaseModel):
    type: str
    params: dict[str, Any] = Field(default_factory=dict)


class StepIn(BaseModel):
    ticks: int = 1


class SpeedIn(BaseModel):
    speed: float = 2


class ForkIn(BaseModel):
    tick: Optional[int] = None
    modifications: dict[str, Any] = Field(default_factory=dict)
    horizon: Optional[int] = None


class BenchmarkIn(BaseModel):
    scenario: str = "triple_failure"
    strategies: list[str] = Field(default_factory=lambda: ["decentralized", "message_passing", "centralized", "greedy"])
    seeds: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5])
    overrides: dict[str, Any] = Field(default_factory=dict)


class AdversarialIn(BaseModel):
    scenario: str = "normal"
    strategy: str = "decentralized"
    n_failures: int = 3
    categories: list[str] = Field(default_factory=lambda: ["bridge", "boat", "shelter"])
    trials: int = 12
    seed: int = 42
    duration: Optional[int] = None
    map: Optional[str] = None


ALLOWED_OVERRIDES = {
    "seed", "duration", "flood_severity", "flood_peak_tick", "initial_incidents", "arrival_incidents", "arrival_window", "boats", "ground_units",
    "shelter_capacity", "shelter_occupancy", "report_noise", "duplicate_rate", "delayed_report_rate", "false_alarm_rate", "contradiction_rate", "forward_rate", "fusion_dedup", "geography",
    "comm_delay", "msg_latency", "msg_loss", "msg_duplicate", "policy", "weights", "neighbourhood_priority", "schedule", "name", "map", "flood_event", "extra_shelters",
}


def make_config(scenario: str, seed: Optional[int], overrides: dict[str, Any]) -> ScenarioConfig:
    if scenario not in PRESETS:
        raise err(400, "BAD_SCENARIO", f"unknown scenario '{scenario}'")
    bad = set(overrides) - ALLOWED_OVERRIDES
    if bad:
        raise err(400, "BAD_OVERRIDE", f"unsupported override(s): {sorted(bad)}")
    ov = dict(overrides)
    if seed is not None:
        ov["seed"] = seed
    if "map" in ov and ov["map"] is not None and not is_known(str(ov["map"])):
        raise err(400, "BAD_MAP", f"unknown map '{ov['map']}'")
    cfg = get_preset(scenario, **ov)
    checks = [
        (1 <= cfg.duration <= 600, "duration must be 1..600"),
        (0.2 <= cfg.flood_severity <= 2.5, "flood_severity must be 0.2..2.5"),
        (0 <= cfg.boats <= 7, "boats must be 0..7"),
        (0 <= cfg.ground_units <= 6, "ground_units must be 0..6"),
        (0 <= cfg.initial_incidents <= 40 and 0 <= cfg.arrival_incidents <= 60, "incident counts out of range"),
        (0 <= cfg.comm_delay <= 20, "comm_delay must be 0..20"),
        (isinstance(cfg.msg_latency, int) and 0 <= cfg.msg_latency <= 10, "msg_latency must be an integer 0..10"),
        (0 <= cfg.msg_loss <= 0.5 and 0 <= cfg.msg_duplicate <= 0.5, "msg_loss and msg_duplicate must be 0..0.5"),
        (all(0 <= x <= 1 for x in (cfg.report_noise, cfg.duplicate_rate, cfg.delayed_report_rate, cfg.false_alarm_rate, cfg.contradiction_rate, cfg.forward_rate)), "rates must be 0..1"),
        (isinstance(cfg.fusion_dedup, bool), "fusion_dedup must be true or false"),
        (cfg.geography in {g["id"] for g in available_geographies()}, f"geography must be one of {[g['id'] for g in available_geographies()]}"),
        (cfg.policy in POLICIES, f"policy must be one of {list(POLICIES)}"),
        (set(cfg.weights) >= {"T", "R", "U", "F"} and all(0 <= float(v) <= 1 for v in cfg.weights.values()), "weights need T,R,U,F in 0..1"),
        (len(cfg.shelter_capacity) == 3 and all(0 <= int(c) <= 500 for c in cfg.shelter_capacity), "shelter_capacity needs 3 values 0..500"),
    ]
    for ok, msg in checks:
        if not ok:
            raise err(422, "INVALID_CONFIG", msg)
    for ev in cfg.schedule:
        if ev.get("type") not in EVENT_TYPES:
            raise err(422, "INVALID_CONFIG", f"scheduled event type {ev.get('type')} unknown")
    return cfg


# ================================================================ meta
@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "sessions": len(SESSIONS), "time": time.time()}


EVALUATION_SUMMARY = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "evaluation", "benchmarks", "summary.json")


@app.get("/api/evaluation")
def evaluation() -> Any:
    """Published benchmark suites (generated by scripts/run_benchmarks.py)."""
    try:
        with open(EVALUATION_SUMMARY, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise err(404, "NO_EVALUATION", "no published evaluation yet: run python scripts/run_benchmarks.py")


@app.get("/api/geographies")
def geographies() -> dict[str, Any]:
    """Cities a run can use: synthetic Riverbend plus any data/geographic/*.city.json
    produced by scripts/build_geo.py."""
    return {"geographies": available_geographies()}


@app.get("/api/scenarios")
def scenarios() -> dict[str, Any]:
    return {
        "scenarios": [c.to_dict() for c in PRESETS.values()],
        "policies": POLICIES,
        "strategies": list(STRATEGIES),
        "event_types": list(EVENT_TYPES),
    }


@app.get("/api/maps")
def maps() -> dict[str, Any]:
    return {"maps": available_maps()}


@app.get("/api/world")
def world(sim: Optional[str] = None, map: str = "riverbend") -> dict[str, Any]:
    """Static geometry: of a given simulation's city, or of a map (Riverbend by default)."""
    if sim:
        return static_world(get_session(sim).engine.world)
    if not is_known(map):
        raise err(400, "BAD_MAP", f"unknown map '{map}'")
    return static_world(Engine(get_preset("normal", map=map), record_frames=False).world)


# ================================================================ simulations
@app.post("/api/simulations")
async def create_simulation(body: CreateSimulation) -> dict[str, Any]:
    if body.strategy not in STRATEGIES:
        raise err(400, "BAD_STRATEGY", f"strategy must be one of {list(STRATEGIES)}")
    overrides = dict(body.overrides)
    if body.map:
        overrides["map"] = body.map
    cfg = make_config(body.scenario, body.seed, overrides)
    sim_id = uuid.uuid4().hex[:10]
    s = Session(sim_id, cfg, body.strategy)
    SESSIONS[sim_id] = s
    s.persist()
    return {**s.summary(), "frame": s.engine.last_frame()}


@app.get("/api/simulations")
def list_sims() -> dict[str, Any]:
    live = [s.summary() | {"live": True} for s in sorted(SESSIONS.values(), key=lambda s: -s.created)]
    ids = {x["id"] for x in live}
    stored = [x | {"live": False} for x in store.list_simulations() if x["id"] not in ids]
    return {"simulations": [{k: v for k, v in x.items() if k not in ("config", "injected")} for x in live] + stored}


@app.get("/api/simulations/{sim_id}")
def get_sim(sim_id: str) -> dict[str, Any]:
    s = get_session(sim_id)
    return {**s.summary(), "frame": s.engine.last_frame()}


@app.post("/api/simulations/{sim_id}/start")
async def start(sim_id: str) -> dict[str, Any]:
    s = get_session(sim_id)
    if s.engine.finished:
        raise err(409, "FINISHED", "simulation has finished; reset to run again")
    if s.status != "running":
        s.status = "running"
        s.task = asyncio.create_task(s.run_loop())
    await s.broadcast("status")
    return s.summary()


@app.post("/api/simulations/{sim_id}/pause")
async def pause(sim_id: str) -> dict[str, Any]:
    s = get_session(sim_id)
    if s.status == "running":
        s.status = "paused"
        if s.task:
            s.task.cancel()
    s.persist()
    await s.broadcast("status")
    return s.summary()


@app.post("/api/simulations/{sim_id}/step")
async def step(sim_id: str, body: StepIn) -> dict[str, Any]:
    s = get_session(sim_id)
    if s.status == "running":
        raise err(409, "RUNNING", "pause the simulation before stepping")
    n = max(1, min(120, body.ticks))
    for _ in range(n):
        if s.engine.finished:
            break
        s.engine.step()
    s.status = "finished" if s.engine.finished else "paused"
    s.persist()
    await s.broadcast()
    return {**s.summary(), "frame": s.engine.last_frame()}


@app.post("/api/simulations/{sim_id}/reset")
async def reset(sim_id: str) -> dict[str, Any]:
    s = get_session(sim_id)
    if s.task:
        s.task.cancel()
    s.engine = Engine(copy.deepcopy(s.cfg), s.strategy)
    s.status = "ready"
    s._audit_sent = 0
    s._round_sent = 0
    s.persist()
    await s.broadcast("reset")
    return {**s.summary(), "frame": s.engine.last_frame()}


@app.post("/api/simulations/{sim_id}/speed")
async def set_speed(sim_id: str, body: SpeedIn) -> dict[str, Any]:
    s = get_session(sim_id)
    if body.speed not in SPEEDS:
        raise err(400, "BAD_SPEED", f"speed must be one of {SPEEDS}")
    s.speed = body.speed
    await s.broadcast("status")
    return s.summary()


@app.post("/api/simulations/{sim_id}/events")
async def inject_event(sim_id: str, body: EventIn) -> dict[str, Any]:
    s = get_session(sim_id)
    if body.type not in EVENT_TYPES:
        raise err(400, "BAD_EVENT", f"event type must be one of {list(EVENT_TYPES)}")
    try:
        ev = s.engine.inject(body.type, body.params, "user")
    except EventError as exc:
        raise err(422, "EVENT_REJECTED", str(exc))
    s.persist()
    await s.broadcast("event")
    return {"event": {"id": ev.id, "tick": ev.tick, "type": ev.type, "params": ev.params, "effects": ev.effects, "source": ev.source}, "state_version": s.engine.world.version, "frame": s.engine.last_frame()}


@app.get("/api/simulations/{sim_id}/events")
def list_events(sim_id: str) -> dict[str, Any]:
    s = get_session(sim_id)
    return {"events": [{"id": e.id, "tick": e.tick, "type": e.type, "params": e.params, "effects": e.effects, "source": e.source} for e in s.engine.events], "injected": s.engine.injected}


@app.get("/api/simulations/{sim_id}/agents")
def agents(sim_id: str) -> dict[str, Any]:
    s = get_session(sim_id)
    e = s.engine
    w = e.world
    out_res = []
    for r in sorted(w.resources.values(), key=lambda r: r.id):
        closed = believed_closed(w, r, e.cfg.comm_delay) if e.is_decentralized() else None
        truth_closed = {x.id for x in w.edges.values() if not (x.ground_ok if r.kind == "ground" else x.boat_ok)}
        stale = sorted((truth_closed ^ set(closed))) if closed is not None else []
        relevant_stale = [x for x in stale if w.edges[x].kind in (("road", "bridge") if r.kind == "ground" else ("road", "river", "jetty"))]
        out_res.append(
            {
                "id": r.id,
                "name": r.name,
                "kind": r.kind,
                "status": r.status,
                "capacity": r.capacity,
                "load": r.load,
                "information": (
                    f"message-passing agent: knows requests and shelter offers only from messages received (latency {e.cfg.msg_latency} tick/hop, loss {e.cfg.msg_loss:.0%}); network view delayed by {e.cfg.comm_delay} tick(s); closures discovered physically"
                    if e.strategy == "message_passing"
                    else "own state exact; incident + network broadcasts delayed by %d tick(s); closures discovered physically" % e.cfg.comm_delay
                    if e.is_decentralized()
                    else "centralised: coordinator holds complete, instant state"
                ),
                "partition": w.partition_of(r.id),
                "belief_mismatch_edges": relevant_stale[:20],
                "discovered_closures": sorted(r.known_closed),
                "blackout_until": r.blackout_until if r.blackout_until >= w.tick else None,
                "missions": [a.id for a in w.assignments.values() if a.resource_id == r.id],
                "bids_submitted": sum(1 for rd in e.rounds for m in rd.messages if m.type == "BID" and m.frm == r.id),
                "commits": sum(1 for a in w.assignments.values() if a.resource_id == r.id),
            }
        )
    shelters = [
        {
            "id": sh.id,
            "name": sh.name,
            "capacity": sh.capacity,
            "occupancy": sh.occupancy,
            "reserved": sh.reserved(w),
            "free": sh.effective_free(w),
            "reservations": [{"id": x.id, "resource": x.resource_id, "incident": x.incident_id, "people": x.people, "status": x.status, "expires": x.expires_tick, "created": x.created_tick} for x in w.reservations.values() if x.shelter_id == sh.id][-40:],
            "accepts": sum(1 for rd in e.rounds for m in rd.messages if m.type == "ACCEPT_RESERVATION" and m.frm == sh.id),
            "rejects": sum(1 for rd in e.rounds for m in rd.messages if m.type == "REJECT_RESERVATION" and m.frm == sh.id),
        }
        for sh in sorted(w.shelters.values(), key=lambda x: x.id)
    ]
    incidents = [
        {"id": i.id, "status": i.status, "confidence": i.confidence, "publications": i.publications[-4:], "reports": len(i.report_ids)}
        for i in sorted(w.incidents.values(), key=lambda i: i.id)
    ]
    route_agent = {
        "closed_for_ground": sorted(x.id for x in w.edges.values() if not x.ground_ok and x.kind in ("road", "bridge")),
        "navigable_flooded_roads": sorted(x.id for x in w.edges.values() if x.boat_ok and x.kind == "road"),
        "manual_closures": [{"id": x.id, "name": x.name, "reason": x.closed_reason} for x in w.edges.values() if x.manual_closed],
        "bridges": [{"id": x.id, "name": x.name, "ground_ok": x.ground_ok, "clearance": x.clearance, "risk": x.risk} for x in w.edges.values() if x.kind == "bridge"],
    }
    return {"strategy": e.strategy, "resources": out_res, "shelters": shelters, "incidents": incidents, "route_agent": route_agent}


class SosIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    shared_node: Optional[str] = None  # location shared by the sender (simulated GPS pin)
    people: Optional[int] = Field(None, ge=1, le=60)
    needs: list[str] = Field(default_factory=list)


def _sos_rationale(x: Any) -> str:
    loc = {"exact": f"inferred from '{', '.join(x.location.matched)}' (node {x.location.node})", "ambiguous": f"ambiguous: {', '.join(x.location.matched)} → {', '.join(x.location.candidates)}",
           "area": f"neighbourhood only ({', '.join(x.location.matched)})", "none": "not recognised"}[x.location.status]
    if x.location_verified:
        loc = f"shared by the sender (node {x.location.node})"
    parts = [
        f"{x.language} SOS: {x.people_count or '?'} people" + (f", needs {', '.join(x.special_needs)}" if x.special_needs else "") + (f", evidence {', '.join(x.urgency_evidence)}" if x.urgency_evidence else "") + f" → urgency {x.urgency} (rule-based).",
        f"Location {loc}" + (f'; text says "{x.location_text}"' if x.location_text else "") + ".",
    ]
    if x.review_reasons:
        parts.append("Review: " + "; ".join(x.review_reasons) + ".")
    parts.append(f"Extractor: {x.extractor}.")
    return " ".join(parts)


@app.post("/api/simulations/{sim_id}/sos")
async def submit_sos(sim_id: str, body: SosIn) -> dict[str, Any]:
    """Citizen SOS intake (simulation). Extract → geocode → either ingest directly (only when
    the sender shared a location and nothing needs review) or queue for dispatcher approval."""
    s = get_session(sim_id)
    w = s.engine.world
    if body.shared_node is not None and (body.shared_node not in w.nodes or w.nodes[body.shared_node].kind == "river"):
        raise err(422, "BAD_LOCATION", "shared location must be a land node")
    gaz = Gazetteer.for_world(w)
    x = await asyncio.get_running_loop().run_in_executor(None, lambda: analyse(body.text, gaz, shared_node=body.shared_node, form_people=body.people, form_needs=body.needs))
    params = {
        "text": body.text, "node": x.location.node if x.location.status == "exact" else None, "candidates": x.location.candidates[:12],
        "people": x.people_count, "urgency": x.urgency, "lang": x.language, "needs": x.special_needs, "evidence": x.urgency_evidence,
        "claim": x.claim, "location_source": "shared" if x.location_verified else ("inferred" if x.location.status == "exact" else "dispatcher"),
    }
    try:
        if not x.requires_human_review:
            ev = s.engine.inject("SOS_REPORT", params, "citizen")
            routed, ref = "ingested", ev.id
        else:
            ev = s.engine.inject("PROPOSE_ACTION", {"action": "SOS_REPORT", "params": params, "source": "sos-intake", "rationale": _sos_rationale(x)}, "citizen")
            routed, ref = "queued_for_dispatcher", list(s.engine.proposals)[-1]
    except EventError as exc:
        raise err(422, "EVENT_REJECTED", str(exc))
    s.persist()
    await s.broadcast("event")
    return {"receipt": fingerprint(body.text), "routed": routed, "ref": ref, "extraction": x.model_dump(), "status": sos_status(s, fingerprint(body.text))}


def sos_status(s: Any, receipt: str) -> dict[str, Any]:
    """Plain-language status for the sender, looked up by the message fingerprint."""
    e, w = s.engine, s.engine.world
    reps = [r for r in w.reports.values() if r.fingerprint == receipt]
    if reps:
        inc = w.incidents.get(reps[-1].incident_id or "")
        if inc is None:
            return {"stage": "logged", "message": "Your message was recorded. It did not match an open request."}
        units = sorted(a.resource_id for a in w.assignments.values() if a.incident_id == inc.id and a.status in ("COMMITTED", "LOADED"))
        eta = min((a.eta_pickup_tick for a in w.assignments.values() if a.incident_id == inc.id and a.status == "COMMITTED"), default=None)
        if inc.status == "RESCUED":
            stage, msg = "rescued", f"Rescue completed: {inc.people_rescued} people taken to a shelter."
        elif units:
            stage, msg = "help_assigned", f"Help is assigned: {', '.join(units)}" + (f", expected in about {max(0, eta - w.tick)} min" if eta is not None else "") + "."
        elif inc.status == "FALSE_ALARM":
            stage, msg = "closed", "This request was closed: responders found nobody needing rescue."
        else:
            stage, msg = "received", "Received and in the queue for the next available unit."
        return {"stage": stage, "message": msg, "incident": inc.id, "incident_status": inc.status, "reports": len(reps), "units": units, "tick": w.tick}
    props = [p for p in e.proposals.values() if p["action"] == "SOS_REPORT" and fingerprint(p["params"].get("text", "")) == receipt]
    if props:
        p = props[-1]
        msg = {"PENDING": "Received. A dispatcher is confirming the location before sending help.", "REJECTED": "A dispatcher reviewed this message and did not open a rescue request.", "EXPIRED": "Received, but not yet confirmed. Please send your location again."}.get(p["status"], "Received.")
        return {"stage": "awaiting_dispatcher" if p["status"] == "PENDING" else p["status"].lower(), "message": msg, "proposal": p["id"], "tick": w.tick}
    return {"stage": "unknown", "message": "No message with this receipt in the current simulation."}


@app.get("/api/simulations/{sim_id}/sos/{receipt}")
def get_sos_status(sim_id: str, receipt: str) -> dict[str, Any]:
    return sos_status(get_session(sim_id), receipt)


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


@app.post("/api/simulations/{sim_id}/ask")
async def ask_commander(sim_id: str, body: AskIn) -> dict[str, Any]:
    """Mission Commander. Answers from a read-only snapshot taken now (so the running
    simulation is never read mid-tick). Any action it suggests is queued as a proposal
    from "ai-commander" on the live engine; only a dispatcher can approve it."""
    s = get_session(sim_id)
    snap = s.engine.read_snapshot()
    out = await asyncio.get_running_loop().run_in_executor(None, commander.ask, body.question, snap)
    queued = []
    for p in out.pop("proposals"):
        try:
            s.engine.inject("PROPOSE_ACTION", {**p, "source": "ai-commander"}, "ai-commander")
            queued.append(list(s.engine.proposals)[-1])
        except EventError as exc:
            out["warnings"].append(f"could not queue proposal: {exc}")
    out["queued_proposals"] = queued
    if queued:
        s.persist()
        await s.broadcast("event")
    return out


@app.get("/api/simulations/{sim_id}/crew/{resource_id}")
def crew_view(sim_id: str, resource_id: str) -> dict[str, Any]:
    """Everything the crew app needs for one unit: the mission, the route with blocked
    segments, what to expect on scene, and which actions are valid right now. Crew
    actions are sent through POST /events as CREW_UPDATE {resource_id, assignment_id,
    action, event_uuid, client_tick, ...}; they are idempotent by event_uuid."""
    from ..routing.router import edge_between, truly_traversable
    from ..simulation.engine import CREW_ACTIONS

    e = get_session(sim_id).engine
    w = e.world
    r = w.resources.get(resource_id)
    if r is None:
        raise err(404, "NOT_FOUND", f"unknown unit {resource_id}")
    a = w.assignments.get(r.assignment_id or "")
    unit = {"id": r.id, "name": r.name, "kind": r.kind, "status": r.status, "node": r.node, "next_node": r.next_node, "load": r.load, "capacity": r.capacity,
            "crew_driven": r.crew_driven, "comms": "blackout" if r.blackout_until >= w.tick else ("partitioned" if w.partition_of(r.id) else "up")}
    recent = [{"tick": x.tick, "message": x.message, "severity": x.severity} for x in e.audit_log if x.refs.get("resource") == r.id][-6:]
    if a is None:
        return {"tick": w.tick, "unit": unit, "mission": None, "allowed_actions": [], "recent": recent}
    inc, sh = w.incidents[a.incident_id], w.shelters[a.shelter_id]
    path = e.remaining_path(r)
    edges = []
    for x, y in zip(path, path[1:]):
        ed = edge_between(w, x, y)
        if ed:
            edges.append({"id": ed.id, "name": ed.name, "kind": ed.kind, "from": x, "to": y, "ok": truly_traversable(ed, r.kind), "closed_reason": ed.closed_reason})
    reports = [w.reports[x] for x in inc.report_ids][-3:]
    target = inc.node if a.crew_state in ("", "awaiting_ack", "acked", "en_route", "on_scene") else sh.node
    at_target = not r.next_node and r.node == target
    allowed = [k for k, (valid, _what) in CREW_ACTIONS.items() if a.crew_state in valid and (k != "ARRIVED" or at_target)]
    return {
        "tick": w.tick,
        "unit": unit,
        "mission": {
            "assignment": a.id, "status": a.status, "step": a.crew_state or "automatic", "created_tick": a.created_tick,
            "incident": {"id": inc.id, "node": inc.node, "urgency": inc.urgency, "people_expected": a.people, "people_waiting": inc.people_estimate, "status": inc.status,
                         "neighbourhood": w.neighbourhoods[inc.neighbourhood].name, "messages": [{"source": rp.source, "text": rp.text or rp.note, "lang": rp.lang, "tick": rp.tick} for rp in reports]},
            "shelter": {"id": sh.id, "name": sh.name, "node": sh.node, "free": sh.effective_free(w)},
            "eta_pickup": a.eta_pickup_tick, "eta_dropoff": a.eta_dropoff_tick, "heading_to": target, "at_target": at_target,
            "route": {"nodes": [{"id": n, "x": w.nodes[n].x, "y": w.nodes[n].y} for n in path], "edges": edges, "blocked": [x for x in edges if not x["ok"]]},
            "ack_deadline": a.created_tick + 5 if a.crew_state == "awaiting_ack" else None,
        },
        "allowed_actions": allowed,
        "recent": recent,
    }


@app.get("/api/simulations/{sim_id}/proposals")
def proposals(sim_id: str, status: Optional[str] = None) -> dict[str, Any]:
    """Approval queue. Create / approve / reject through POST /events with PROPOSE_ACTION,
    APPROVE_PROPOSAL and REJECT_PROPOSAL so every decision is in the replayable event log."""
    items = list(get_session(sim_id).engine.proposals.values())
    return {"proposals": [p for p in items if status is None or p["status"] == status.upper()]}


@app.get("/api/simulations/{sim_id}/assignments")
def assignments(sim_id: str) -> dict[str, Any]:
    return {"assignments": get_session(sim_id).engine.last_frame()["assignments"]}


@app.get("/api/simulations/{sim_id}/negotiations")
def negotiations(sim_id: str, limit: int = Query(60, ge=1, le=500), incident: Optional[str] = None) -> dict[str, Any]:
    e = get_session(sim_id).engine
    rounds = [r for r in e.rounds if not incident or incident in r.incidents]
    return {"total": len(rounds), "rounds": [r.to_dict(with_messages=False) for r in rounds[-limit:]][::-1]}


@app.get("/api/simulations/{sim_id}/negotiations/{round_id}")
def negotiation(sim_id: str, round_id: str) -> dict[str, Any]:
    e = get_session(sim_id).engine
    r = next((r for r in e.rounds if r.id == round_id), None)
    if not r:
        raise err(404, "NOT_FOUND", f"round {round_id} not found")
    decs = [d for d in e.decisions.values() if d["round_id"] == round_id]
    return {**r.to_dict(), "decisions": decs}


@app.get("/api/simulations/{sim_id}/decisions")
def decisions(sim_id: str, incident: Optional[str] = None, resource: Optional[str] = None, outcome: Optional[str] = None, limit: int = Query(200, ge=1, le=2000)) -> dict[str, Any]:
    e = get_session(sim_id).engine
    ds = list(e.decisions.values())
    if incident:
        ds = [d for d in ds if d["incident_id"] == incident]
    if resource:
        ds = [d for d in ds if (d.get("selected") or {}).get("resource_id") == resource or any(c["resource_id"] == resource for c in d["candidates"])]
    if outcome:
        ds = [d for d in ds if d["outcome"] == outcome]
    return {"total": len(ds), "decisions": ds[-limit:][::-1]}


@app.get("/api/simulations/{sim_id}/decisions/{decision_id}")
def decision(sim_id: str, decision_id: str) -> dict[str, Any]:
    e = get_session(sim_id).engine
    d = e.decisions.get(decision_id)
    if not d:
        raise err(404, "NOT_FOUND", f"decision {decision_id} not found")
    a = e.world.assignments.get(d.get("assignment_id") or "")
    return {**d, "assignment": {"id": a.id, "status": a.status, "cancel_reason": a.cancel_reason, "reroutes": a.reroutes} if a else None}


@app.get("/api/simulations/{sim_id}/metrics")
def metrics(sim_id: str) -> dict[str, Any]:
    e = get_session(sim_id).engine
    return {"metrics": compute_metrics(e), "series": e.metric_series, "disruptions": e.disruptions}


@app.get("/api/simulations/{sim_id}/audit")
def audit(sim_id: str, category: Optional[str] = None, since: int = 0, limit: int = Query(500, ge=1, le=5000)) -> dict[str, Any]:
    e = get_session(sim_id).engine
    rows = [a for a in e.audit_log if a.tick >= since and (not category or a.category == category)]
    return {"total": len(rows), "audit": [_audit_dict(a) for a in rows[-limit:]]}


@app.get("/api/simulations/{sim_id}/safety")
def safety(sim_id: str) -> dict[str, Any]:
    e = get_session(sim_id).engine
    m = compute_metrics(e)
    return {
        "invariants": ["S1 no double booking", "S2 shelter capacity", "S3 prohibited edges", "S4 transport capacity", "S5 stale versions", "S6 reservation validity", "S7 operational & connected"],
        "route_violations": m["route_violations"],
        "invariant_violations": m["invariant_violations"],
        "commit_rejections": m["safety_rejections"],
        "movement_blocks": m["blocked_moves"],
        "log": e.safety_log[-300:][::-1],
    }


@app.get("/api/simulations/{sim_id}/frames")
def frames(sim_id: str, start: int = 0, end: Optional[int] = None, stride: int = Query(1, ge=1, le=20)) -> dict[str, Any]:
    e = get_session(sim_id).engine
    end = e.world.tick if end is None else end
    ticks = [t for t in sorted(e.frames) if start <= t <= end][::stride]
    return {"ticks": ticks, "frames": [e.frames[t] for t in ticks], "hashes": {t: e.hashes.get(t) for t in ticks}}


@app.get("/api/simulations/{sim_id}/replay/verify")
async def replay_verify(sim_id: str) -> dict[str, Any]:
    s = get_session(sim_id)
    snapshot = s.engine.fork()
    return await asyncio.get_running_loop().run_in_executor(None, verify_replay, snapshot)


@app.post("/api/simulations/{sim_id}/fork")
async def fork(sim_id: str, body: ForkIn) -> dict[str, Any]:
    s = get_session(sim_id)
    e = s.engine
    tick = e.world.tick if body.tick is None else body.tick
    if not (0 <= tick <= e.world.tick):
        raise err(422, "BAD_TICK", f"fork tick must be within 0..{e.world.tick}")
    cfg, injected = copy.deepcopy(e.base_cfg), copy.deepcopy(e.injected)
    try:
        return await asyncio.get_running_loop().run_in_executor(None, counterfactual, cfg, e.strategy, injected, tick, body.modifications, body.horizon)
    except EventError as exc:
        raise err(422, "BAD_MODIFICATION", str(exc))


# ================================================================ jobs (benchmarks + adversarial)
def _start_job(kind: str, request: dict[str, Any], fn: Any) -> dict[str, Any]:
    job_id = f"{kind[:3]}-{uuid.uuid4().hex[:8]}"
    job = {"id": job_id, "kind": kind, "status": "running", "progress": 0.0, "request": request, "result": None, "error": None, "created": time.time()}
    JOBS[job_id] = job

    def progress(p: float) -> None:
        job["progress"] = round(p, 3)

    async def runner() -> None:
        try:
            res = await asyncio.get_running_loop().run_in_executor(None, fn, progress)
            job["result"], job["status"], job["progress"] = res, "done", 1.0
            store.save_job(job_id, kind, request, res)
        except Exception as exc:  # surface failures honestly
            job["status"], job["error"] = "error", str(exc)

    asyncio.get_running_loop().create_task(runner())
    return job


@app.post("/api/benchmarks")
async def create_benchmark(body: BenchmarkIn) -> dict[str, Any]:
    if not body.strategies or any(st not in STRATEGIES for st in body.strategies):
        raise err(400, "BAD_STRATEGY", f"strategies must be from {list(STRATEGIES)}")
    if not (1 <= len(body.seeds) <= 30):
        raise err(422, "BAD_SEEDS", "1..30 seeds")
    cfg = make_config(body.scenario, None, body.overrides)
    return _start_job("benchmark", body.model_dump(), lambda p: benchmark(cfg, body.strategies, body.seeds, p))


@app.get("/api/benchmarks/{job_id}")
def get_benchmark(job_id: str) -> dict[str, Any]:
    job = JOBS.get(job_id)
    if job:
        return job
    rec = store.load_job(job_id)
    if not rec:
        raise err(404, "NOT_FOUND", f"job {job_id} not found")
    return {**rec, "status": "done", "progress": 1.0}


@app.post("/api/adversarial")
async def create_adversarial(body: AdversarialIn) -> dict[str, Any]:
    if body.strategy not in STRATEGIES:
        raise err(400, "BAD_STRATEGY", "unknown strategy")
    if not (1 <= body.n_failures <= 5 and 1 <= body.trials <= 60):
        raise err(422, "BAD_REQUEST", "n_failures 1..5, trials 1..60")
    ov: dict[str, Any] = {"duration": body.duration} if body.duration else {}
    if body.map:
        ov["map"] = body.map
    cfg = make_config(body.scenario, None, ov)
    return _start_job("adversarial", body.model_dump(), lambda p: adversarial(cfg, body.strategy, body.n_failures, body.categories, body.trials, body.seed, p))


@app.get("/api/adversarial/{job_id}")
def get_adversarial(job_id: str) -> dict[str, Any]:
    return get_benchmark(job_id)


# ================================================================ reports
@app.get("/api/reports/{sim_id}")
async def report(sim_id: str, format: str = Query("json", pattern="^(json|pdf)$"), compare: bool = True) -> Any:
    s = get_session(sim_id)
    snapshot = s.engine.fork()
    rep = await asyncio.get_running_loop().run_in_executor(None, lambda: build_report(snapshot, sim_id, compare))
    if format == "pdf":
        pdf = await asyncio.get_running_loop().run_in_executor(None, report_pdf, rep)
        return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="resqnet-report-{sim_id}.pdf"'})
    return rep


# ================================================================ websocket
@app.websocket("/ws/simulations/{sim_id}")
async def ws_sim(ws: WebSocket, sim_id: str) -> None:
    await ws.accept()
    try:
        s = get_session(sim_id)
    except HTTPException:
        await ws.send_text(json.dumps({"type": "error", "error": {"code": "NOT_FOUND", "message": f"simulation {sim_id} not found"}}))
        await ws.close()
        return
    s.clients.add(ws)
    await ws.send_text(json.dumps(s.full_message("hello"), default=str))
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if msg.get("type") == "resync":
                await ws.send_text(json.dumps(s.full_message("resync"), default=str))
            elif msg.get("type") == "ping":
                await ws.send_text(json.dumps({"type": "pong", "state_version": s.engine.world.version}))
    except WebSocketDisconnect:
        pass
    finally:
        s.clients.discard(ws)


# ================================================================ single-container deployment
# When the built frontend exists (frontend/dist, or RESQNET_STATIC), serve it from the same
# origin as the API and WebSocket. Registered last so every /api and /ws route wins.
STATIC_DIR = os.path.realpath(os.environ.get("RESQNET_STATIC", os.path.join(os.path.dirname(__file__), "..", "..", "..", "frontend", "dist")))
if os.path.isfile(os.path.join(STATIC_DIR, "index.html")):
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    if os.path.isdir(os.path.join(STATIC_DIR, "assets")):
        app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> Any:
        if path.startswith(("api/", "ws/")) or path in ("api", "ws"):
            raise err(404, "NOT_FOUND", f"no route /{path}")
        target = os.path.realpath(os.path.join(STATIC_DIR, path))
        if path and target.startswith(STATIC_DIR + os.sep) and os.path.isfile(target):
            return FileResponse(target)
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))  # client-side routes (/command, /crew/B1, …)
