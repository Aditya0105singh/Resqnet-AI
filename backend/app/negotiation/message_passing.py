"""Message-passing negotiation: independent agents that interact only through the bus.

Unlike `decentralized.py`, which computes every agent's bids inside one function with
an instantaneous message log, here every agent is a separate handler with its own
local state. Each handler reads only its own inbox and its own knowledge, and acts
only by sending messages through `transport.Bus`. The bus can add latency, drop or
duplicate messages, and split the network.

Protocol (asynchronous contract net with proposal ids, timeouts and leases)

    incident ──REQUEST(cfp)──▶ every rescue agent        (call for proposals)
    rescue   ──BID(cfp)──────▶ incident                  (top-3 cheapest known requests)
    incident ──PROPOSE(pid)──▶ best bidder               (one outstanding proposal; expires)
    rescue   ──RESERVE(pid)──▶ shelter                   (or DECLINE(pid) ▶ incident)
    shelter  ──ACCEPT_RESERVATION / REJECT_RESERVATION──▶ rescue (lease until t+L)
    rescue   ── safety shield ── commit ──CONFIRM(pid)──▶ incident
    shelter  ──OFFER──▶ every rescue agent               (free capacity, on change)
    incident ──WITHDRAW──▶ every rescue agent            (request no longer open)

Safety rules
* Shelter agents own their capacity, so a reservation is exclusive. A rescue agent
  commits only while holding an ACCEPTed reservation and only if the shield passes
  against authoritative state (S1–S7, including incident/resource versions).
* An agent cut off from incidents or shelters makes no new commitments. It keeps
  executing commitments that are already valid. Availability is lost, never safety.
* Every handler is idempotent. Duplicate deliveries are discarded by message id,
  and replies to unknown or expired proposal ids are ignored or cancelled.
* Lost messages are recovered by timeouts: an unanswered PROPOSE expires and the
  incident moves to its next bidder. An unclaimed reservation lease expires and the
  shelter frees the seats.

Information model: a rescue agent knows its own state exactly. It knows requests and
shelter offers only from messages it has received, and it plans routes on its
believed network (`believed_closed`, as in the instant protocol).
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from ..routing.router import believed_closed
from ..simulation.state import IncidentStatus, ReservationStatus, ResourceStatus
from .common import (
    Candidate,
    NegotiationRound,
    commit_reserved,
    evaluate,
    incident_view,
    is_eligible,
    neighbourhood_waits,
    priority_key,
    release_reservation,
    request_reservation,
    unassigned_people,
)
from .transport import Bus, Envelope

TOP_K_BIDS = 3
MAX_PHASES = 12  # protocol phases per tick (latency 0 = several hops inside one minute)
REBROADCAST = 10  # ticks before an unanswered call for proposals is re-sent
PROPOSAL_SLACK = 2
LEASE_SLACK = 3


@dataclass
class IncidentAgentState:
    cfp: Optional[str] = None
    cfp_tick: int = -1
    cfp_version: int = -1
    bids: dict[str, dict[str, Any]] = field(default_factory=dict)  # resource -> bid payload
    excluded: dict[str, str] = field(default_factory=dict)  # resource -> why (this cfp)
    proposal: Optional[dict[str, Any]] = None  # {id, resource, sent, expires}


@dataclass
class RescueAgentState:
    known: dict[str, dict[str, Any]] = field(default_factory=dict)  # incident -> REQUEST view
    offers: dict[str, int] = field(default_factory=dict)  # shelter -> free seats (as last heard)
    bid_on: set[tuple[str, str]] = field(default_factory=set)  # (incident, cfp)
    evaluated: Any = None  # key of the last evaluation, to avoid re-planning every phase
    pending: Optional[dict[str, Any]] = None  # proposal being executed


@dataclass
class ShelterAgentState:
    handled: dict[str, str] = field(default_factory=dict)  # proposal id -> reservation id / ""
    last_offer: Optional[int] = None


@dataclass
class MASState:
    bus: Bus
    incidents: dict[str, IncidentAgentState] = field(default_factory=dict)
    rescuers: dict[str, RescueAgentState] = field(default_factory=dict)
    shelters: dict[str, ShelterAgentState] = field(default_factory=dict)
    seq: int = 0

    def next(self, prefix: str) -> str:
        self.seq += 1
        return f"{prefix}-{self.seq:05d}"


def init_state(engine: Any) -> MASState:
    cfg = engine.cfg
    return MASState(Bus(latency=int(cfg.msg_latency), loss=float(cfg.msg_loss), duplicate=float(cfg.msg_duplicate), seed=int(cfg.seed)))


class _Ctx:
    """Per-call helpers: sending through the bus and logging into the round."""

    def __init__(self, engine: Any, mas: MASState, rnd: NegotiationRound):
        self.engine = engine
        self.world = engine.world
        self.cfg = engine.cfg
        self.mas = mas
        self.bus = mas.bus
        self.rnd = rnd
        self.waits: Optional[dict[str, float]] = None

    def send(self, type_: str, frm: str, to: str, incident: str = "", proposal: str = "", reason: str = "", log: Optional[dict[str, Any]] = None, **payload: Any) -> Envelope:
        env = self.bus.send(self.world, type_, frm, to, incident, proposal, reason, **payload)
        self.rnd.msg(type_, frm, to, incident, reason, msg=env.id, proposal=proposal, deliver=env.deliver_tick, **(log or {}))
        return env

    def drain_drops(self) -> None:
        for d in self.bus.log:
            env = d["msg"]
            self.rnd.msg("LOST", "network", env.to, env.incident, d["reason"], msg=env.id, lost_type=env.type, sender=env.frm, proposal=env.proposal)
        self.bus.log.clear()

    def neighbourhood_waits(self) -> dict[str, float]:
        if self.waits is None:
            self.waits = neighbourhood_waits(self.world)
        return self.waits


# ======================================================================= agents


def _incident_open(world: Any, inc: Any) -> bool:
    if inc.status in (IncidentStatus.RESCUED, IncidentStatus.FALSE_ALARM):
        return False
    ok, _ = is_eligible(world, inc)
    return ok and unassigned_people(world, inc) > 0


def _incident_step(ctx: _Ctx, iid: str) -> bool:
    world, bus = ctx.world, ctx.bus
    inc = world.incidents[iid]
    st = ctx.mas.incidents.setdefault(iid, IncidentAgentState())
    acted = False
    for m in bus.take(iid):
        acted = True
        if m.type == "BID":
            if m.proposal == st.cfp and m.frm not in st.excluded:
                st.bids[m.frm] = m.payload
        elif m.type == "DECLINE":
            if st.proposal and m.proposal == st.proposal["id"]:
                st.excluded[m.frm] = m.reason or "declined"
                st.proposal = None
        elif m.type == "CONFIRM":
            if st.proposal and m.proposal == st.proposal["id"]:
                st.proposal = None
    if not _incident_open(world, inc):
        if st.cfp is not None:
            for rid in sorted(world.resources):
                ctx.send("WITHDRAW", iid, rid, iid, st.cfp, reason=f"request closed ({inc.status.lower()})")
            st.cfp, st.bids, st.excluded, st.proposal = None, {}, {}, None
            return True
        return acted
    # proposal timeout: the bidder never answered (lost message, partition, failure)
    if st.proposal and world.tick > st.proposal["expires"]:
        rid = st.proposal["resource"]
        st.excluded[rid] = f"no answer to {st.proposal['id']} by t={st.proposal['expires']}"
        ctx.rnd.msg("EXPIRE", iid, rid, iid, st.excluded[rid], proposal=st.proposal["id"])
        st.proposal = None
        acted = True
    if st.proposal:
        return acted
    usable = {r: b for r, b in st.bids.items() if r not in st.excluded}
    stale = st.cfp is None or st.cfp_version != inc.version
    if stale or (not usable and world.tick - st.cfp_tick >= REBROADCAST):
        st.cfp = ctx.mas.next("CFP")
        st.cfp_tick, st.cfp_version, st.bids, st.excluded = world.tick, inc.version, {}, {}
        view = incident_view(world, inc)
        for rid in sorted(world.resources):
            if world.resources[rid].status == ResourceStatus.DISABLED:
                continue
            ctx.send("REQUEST", iid, rid, iid, st.cfp, log={"people": view["unassigned"], "urgency": view["urgency"], "version": view["version"]}, view=view)
        return True
    if usable and world.tick >= st.cfp_tick + 2 * ctx.bus.latency:
        rid, bid = min(usable.items(), key=lambda kv: (kv[1]["cost"], kv[0]))
        pid = ctx.mas.next("P")
        expires = world.tick + 4 * ctx.bus.latency + PROPOSAL_SLACK
        st.proposal = {"id": pid, "resource": rid, "sent": world.tick, "expires": expires, "cost": bid["cost"]}
        ctx.send("PROPOSE", iid, rid, iid, pid, log={"cost": round(bid["cost"], 4), "expires": expires}, view=incident_view(world, inc), cfp=st.cfp)
        return True
    return acted


def _rescue_available(world: Any, r: Any) -> bool:
    return r.status == ResourceStatus.IDLE and r.load == 0 and r.assignment_id is None


def _evaluate(ctx: _Ctx, r: Any, st: RescueAgentState, view: dict[str, Any]) -> Candidate:
    closed = believed_closed(ctx.world, r, max(0, int(ctx.cfg.comm_delay)))
    offers = {sid: free for sid, free in st.offers.items()}
    return evaluate(ctx.world, ctx.cfg, r, view, offers, ctx.neighbourhood_waits(), closed, None, knowledge=f"messages@t{ctx.world.tick}")


def _decline(ctx: _Ctx, rid: str, m_or_pending: Any, reason: str) -> None:
    if isinstance(m_or_pending, Envelope):
        ctx.send("DECLINE", rid, m_or_pending.frm, m_or_pending.incident, m_or_pending.proposal, reason=reason)
    else:
        p = m_or_pending
        ctx.send("DECLINE", rid, p["incident"], p["incident"], p["pid"], reason=reason)


def _reserve_next(ctx: _Ctx, rid: str, st: RescueAgentState) -> None:
    p = st.pending
    world = ctx.world
    if p["opt"] >= len(p["cand"].shelter_options):
        _decline(ctx, rid, p, "no shelter accepted a reservation")
        _record(ctx, p, "NO_SHELTER")
        st.pending = None
        return
    sid, mins, _path = p["cand"].shelter_options[p["opt"]]
    eta = world.tick + int(math.ceil(p["cand"].eta_pickup + 2 + mins))
    p["eta_drop"] = eta
    p["expires"] = world.tick + 2 * ctx.bus.latency + PROPOSAL_SLACK
    ctx.send("RESERVE", rid, sid, p["incident"], p["pid"], log={"people": p["cand"].people, "eta": eta}, people=p["cand"].people, eta=eta, assignment=p["aid"])


def _record(ctx: _Ctx, p: dict[str, Any], outcome: str, finalize: bool = True) -> dict[str, Any]:
    """Decision record for the audit trail (observer view: the bids the incident holds)."""
    engine, world = ctx.engine, ctx.world
    inc = world.incidents[p["incident"]]
    ist = ctx.mas.incidents.get(inc.id)
    cands = [p["cand"]]
    if ist:
        for r2, b in sorted(ist.bids.items()):
            if r2 != p["cand"].resource_id and isinstance(b.get("cand"), Candidate):
                cands.append(b["cand"])
    dec = engine.new_decision(ctx.rnd, inc, cands, p["view"])
    dec["selected"] = p["cand"].to_dict()
    dec["shelter_log"] = list(p["shelter_log"])
    dec["outcome"] = outcome
    if ist:
        dec["rejections"] = [{"resource": r2, "reason": why} for r2, why in sorted(ist.excluded.items())]
    dec["protocol"] = {"proposal": p["pid"], "cfp": p.get("cfp"), "transport": {"latency": ctx.bus.latency, "loss": ctx.bus.loss}}
    if finalize:
        engine.finalize_decision(dec)
    return dec


def _rescue_step(ctx: _Ctx, rid: str) -> bool:
    world, bus = ctx.world, ctx.bus
    r = world.resources[rid]
    st = ctx.mas.rescuers.setdefault(rid, RescueAgentState())
    msgs = bus.take(rid)
    acted = bool(msgs)
    proposals: list[Envelope] = []
    for m in msgs:
        if m.type == "REQUEST":
            st.known[m.incident] = {**m.payload["view"], "cfp": m.proposal}
        elif m.type == "WITHDRAW":
            if st.known.get(m.incident, {}).get("cfp") == m.proposal:
                st.known.pop(m.incident, None)
        elif m.type == "OFFER":
            st.offers[m.frm] = int(m.payload["free"])
        elif m.type == "PROPOSE":
            proposals.append(m)
        elif m.type in ("ACCEPT_RESERVATION", "REJECT_RESERVATION"):
            _on_shelter_reply(ctx, rid, r, st, m)
    if r.status == ResourceStatus.DISABLED:
        if st.pending:
            st.pending = None
        for m in proposals:
            _decline(ctx, rid, m, f"{rid} disabled")
        return acted or bool(proposals)
    # a pending proposal whose shelter never answered: give it up (the lease will lapse)
    if st.pending and world.tick > st.pending["expires"]:
        p = st.pending
        _decline(ctx, rid, p, "no reply from shelter before timeout")
        p["shelter_log"].append({"shelter": p["cand"].shelter_options[p["opt"]][0], "accepted": False, "reason": "timed out"})
        _record(ctx, p, "NO_SHELTER")
        st.pending = None
        acted = True
    # proposals: accept the cheapest one we can execute, decline the rest
    proposals.sort(key=lambda m: m.proposal)
    chosen: Optional[Candidate] = None
    best: Optional[Envelope] = None
    if proposals and _rescue_available(world, r) and st.pending is None:
        evals = [(_evaluate(ctx, r, st, m.payload["view"]), m) for m in proposals]
        feas = sorted((x for x in evals if x[0].feasible), key=lambda x: (x[0].cost, priority_key(world.incidents[x[1].incident])))
        if feas:
            chosen, best = feas[0]
        for c, m in evals:
            if m is best:
                continue
            _decline(ctx, rid, m, f"engaged with {best.incident} (cost {chosen.cost:.3f})" if best else (c.reason or "infeasible"))
    else:
        for m in proposals:
            why = f"{rid} busy ({r.status.lower()})" if not _rescue_available(world, r) else f"already executing {st.pending['pid']}"
            _decline(ctx, rid, m, why)
    if best is not None and chosen is not None:
        st.pending = {"pid": best.proposal, "incident": best.incident, "cand": chosen, "view": best.payload["view"], "cfp": best.payload.get("cfp"), "opt": 0, "aid": world.next_id("A"), "shelter_log": []}
        _reserve_next(ctx, rid, st)
        acted = True
    # bidding on requests we know about
    if _rescue_available(world, r) and st.pending is None and st.known:
        key = (tuple(sorted((i, v["cfp"]) for i, v in st.known.items())), r.version, r.node, tuple(sorted(st.offers.items())))
        if key != st.evaluated:
            st.evaluated = key
            evals = [_evaluate(ctx, r, st, v) for _, v in sorted(st.known.items())]
            feas = sorted((c for c in evals if c.feasible), key=lambda c: (c.cost, priority_key(world.incidents[c.incident_id])))
            for c in feas[:TOP_K_BIDS]:
                cfp = st.known[c.incident_id]["cfp"]
                if (c.incident_id, cfp) in st.bid_on:
                    continue
                st.bid_on.add((c.incident_id, cfp))
                ctx.send("BID", rid, c.incident_id, c.incident_id, cfp, log={"cost": round(c.cost, 4), "eta_pickup": round(c.eta_pickup, 1), "people": c.people, "shelter": c.shelter_options[0][0]}, cost=c.cost, cand=c)
                acted = True
    return acted


def _on_shelter_reply(ctx: _Ctx, rid: str, r: Any, st: RescueAgentState, m: Envelope) -> None:
    world = ctx.world
    p = st.pending
    if m.type == "ACCEPT_RESERVATION":
        rsv = world.reservations.get(m.payload.get("reservation", ""))
        if not p or p["pid"] != m.proposal or rsv is None or rsv.status != ReservationStatus.ACTIVE:
            # late or duplicate grant: hand the seats back (idempotent at the shelter)
            ctx.send("CANCEL_RESERVATION", rid, m.frm, m.incident, m.proposal, reason="proposal no longer pending", reservation=m.payload.get("reservation"))
            return
        p["shelter_log"].append({"shelter": m.frm, "accepted": True, "reason": m.reason, "reservation": rsv.id})
        _sid, _mins, dpath = p["cand"].shelter_options[p["opt"]]
        dec = _record(ctx, p, "PENDING", finalize=False)
        a = commit_reserved(ctx.engine, p["cand"], rsv, dpath, p["eta_drop"], p["aid"], ctx.rnd, dec, committer=rid)
        if a is not None:
            ctx.send("CONFIRM", rid, p["incident"], p["incident"], p["pid"], log={"assignment": a.id}, assignment=a.id)
        else:
            _decline(ctx, rid, p, f"safety shield: {dec.get('rejection_code')}")
        ctx.engine.finalize_decision(dec)
        st.pending = None
        return
    if p and p["pid"] == m.proposal:
        p["shelter_log"].append({"shelter": m.frm, "accepted": False, "reason": m.reason})
        p["opt"] += 1
        _reserve_next(ctx, rid, st)


def _shelter_step(ctx: _Ctx, sid: str) -> bool:
    world = ctx.world
    sh = world.shelters[sid]
    st = ctx.mas.shelters.setdefault(sid, ShelterAgentState())
    acted = False
    for m in ctx.bus.take(sid):
        acted = True
        if m.type == "RESERVE":
            if m.proposal in st.handled:
                continue  # already answered this proposal: never reserve twice
            people, eta = int(m.payload["people"]), int(m.payload["eta"])
            rsv, why = request_reservation(world, sid, people, m.frm, m.incident, eta, m.payload["assignment"])
            if rsv is None:
                st.handled[m.proposal] = ""
                ctx.send("REJECT_RESERVATION", sid, m.frm, m.incident, m.proposal, reason=why)
                continue
            rsv.pending_until = world.tick + 2 * ctx.bus.latency + LEASE_SLACK
            st.handled[m.proposal] = rsv.id
            ctx.send("ACCEPT_RESERVATION", sid, m.frm, m.incident, m.proposal, reason=why, log={"reservation": rsv.id, "lease_until": rsv.pending_until}, reservation=rsv.id)
        elif m.type == "CANCEL_RESERVATION":
            rsv = world.reservations.get(m.payload.get("reservation") or "")
            if rsv and rsv.status == ReservationStatus.ACTIVE and rsv.assignment_id not in world.assignments:
                release_reservation(world, rsv.id)
    free = max(0, sh.effective_free(world))
    if free != st.last_offer:
        st.last_offer = free
        for rid in sorted(world.resources):
            if world.resources[rid].status != ResourceStatus.DISABLED:
                ctx.send("OFFER", sid, rid, "", "", log={"free": free}, free=free)
        acted = True
    return acted


# ======================================================================= driver


def run(engine: Any, trigger: str) -> Optional[NegotiationRound]:
    if engine.mas is None:
        engine.mas = init_state(engine)
    mas: MASState = engine.mas
    world = engine.world
    t0 = time.perf_counter()
    rnd = NegotiationRound(engine.next_round_id(), world.tick, "message_passing", trigger)
    ctx = _Ctx(engine, mas, rnd)
    order = sorted(world.incidents.values(), key=priority_key)
    for _phase in range(MAX_PHASES):
        mas.bus.deliver(world)
        acted = False
        for sid in sorted(world.shelters):
            acted |= _shelter_step(ctx, sid)
        for inc in order:
            acted |= _incident_step(ctx, inc.id)
        for rid in sorted(world.resources):
            acted |= _rescue_step(ctx, rid)
        ctx.drain_drops()
        rnd.iterations += 1
        if not mas.bus.pending(world):
            break
    rnd.duration_ms = (time.perf_counter() - t0) * 1000
    if not rnd.messages:
        engine._round_seq -= 1  # nothing happened this tick: do not burn a round id
        return None
    rnd.incidents = sorted({m.incident for m in rnd.messages if m.incident})
    rnd.resources = sorted({m.frm for m in rnd.messages if m.frm in world.resources})
    return rnd
