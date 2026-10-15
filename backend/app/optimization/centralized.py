"""Centralised baselines.

* centralized — a global coordinator with instant, complete information (true network
  state, every unit's position, current incident estimates) solves a min-cost
  assignment (Hungarian algorithm, scipy.optimize.linear_sum_assignment) over all
  idle units x open requests each tick, using the *same* cost function.
* greedy — nearest-feasible: requests in priority order each take the idle unit with
  the smallest pickup ETA.

Both reserve shelter capacity through the same shelter agents and pass the same
safety shield as the decentralised strategy; the baseline is not weakened.
"""
from __future__ import annotations

import time
from typing import Any, Optional

import numpy as np
from scipy.optimize import linear_sum_assignment

from ..negotiation.common import (
    NegotiationRound,
    available_resources,
    evaluate,
    incident_view,
    neighbourhood_waits,
    open_requests,
    shelter_offers,
    try_commit,
)

INFEASIBLE = 1e6


def _prepare(engine: Any, strategy: str, trigger: str):
    world = engine.world
    units = available_resources(world)
    reqs = open_requests(world)
    if not units or not reqs:
        return None
    rnd = NegotiationRound(engine.next_round_id(), world.tick, strategy, trigger)
    rnd.incidents = [r.id for r in reqs]
    rnd.resources = [u.id for u in units]
    for u in units:
        rnd.msg("STATUS", u.id, "coordinator", "", node=u.node, capacity=u.capacity)
    for r in reqs:
        rnd.msg("REQUEST", r.id, "coordinator", r.id, people=r.people_estimate, urgency=r.urgency)
    offers = shelter_offers(world)
    for sid, free in offers.items():
        rnd.msg("OFFER", sid, "coordinator", "", free=free)
    waits = neighbourhood_waits(world)
    cache: dict = {}
    views = {r.id: incident_view(world, r) for r in reqs}
    cands = {(u.id, r.id): evaluate(world, engine.cfg, u, views[r.id], offers, waits, None, cache) for u in units for r in reqs}
    decisions = {r.id: engine.new_decision(rnd, r, [cands[(u.id, r.id)] for u in units], views[r.id]) for r in reqs}
    return world, units, reqs, rnd, cands, decisions


def run_centralized(engine: Any, trigger: str) -> Optional[NegotiationRound]:
    t0 = time.perf_counter()
    prep = _prepare(engine, "centralized", trigger)
    if prep is None:
        return None
    world, units, reqs, rnd, cands, decisions = prep
    taken_units: set[str] = set()
    done: set[str] = set()
    for _pass in range(3):
        us = [u for u in units if u.id not in taken_units]
        rs = [r for r in reqs if r.id not in done]
        if not us or not rs:
            break
        m = np.full((len(us), len(rs)), INFEASIBLE)
        for i, u in enumerate(us):
            for j, r in enumerate(rs):
                c = cands[(u.id, r.id)]
                if c.feasible and not getattr(c, "_failed", False):
                    m[i, j] = c.cost
        rows, cols = linear_sum_assignment(m)
        rnd.iterations += 1
        pairs = [(us[i], rs[j]) for i, j in zip(rows, cols) if m[i, j] < INFEASIBLE]
        if not pairs:
            break
        pairs.sort(key=lambda p: reqs.index(p[1]))
        progress = False
        for u, r in pairs:
            c = cands[(u.id, r.id)]
            rnd.matching.append({"pass": _pass + 1, "resource": u.id, "incident": r.id, "cost": round(c.cost, 4)})
            rnd.msg("DIRECTIVE", "coordinator", u.id, r.id, cost=round(c.cost, 4), eta_pickup=round(c.eta_pickup, 1))
            decisions[r.id]["selected"] = c.to_dict()
            a = try_commit(engine, c, rnd, decisions[r.id])
            if a is None:
                c._failed = True  # type: ignore[attr-defined]
                continue
            taken_units.add(u.id)
            done.add(r.id)
            progress = True
        if not progress:
            break
    rnd.duration_ms = (time.perf_counter() - t0) * 1000
    for dec in decisions.values():
        engine.finalize_decision(dec)
    return rnd


def run_greedy(engine: Any, trigger: str) -> Optional[NegotiationRound]:
    t0 = time.perf_counter()
    prep = _prepare(engine, "greedy", trigger)
    if prep is None:
        return None
    world, units, reqs, rnd, cands, decisions = prep
    taken: set[str] = set()
    for r in reqs:
        rnd.iterations += 1
        options = sorted(
            (cands[(u.id, r.id)] for u in units if u.id not in taken and cands[(u.id, r.id)].feasible),
            key=lambda c: (c.eta_pickup, c.resource_id),
        )
        for c in options:
            rnd.msg("DIRECTIVE", "coordinator", c.resource_id, r.id, eta_pickup=round(c.eta_pickup, 1))
            decisions[r.id]["selected"] = c.to_dict()
            rnd.matching.append({"pass": 1, "resource": c.resource_id, "incident": r.id, "cost": round(c.cost, 4)})
            if try_commit(engine, c, rnd, decisions[r.id]) is not None:
                taken.add(c.resource_id)
                break
    rnd.duration_ms = (time.perf_counter() - t0) * 1000
    for dec in decisions.values():
        engine.finalize_decision(dec)
    return rnd
