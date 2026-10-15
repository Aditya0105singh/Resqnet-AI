"""Simulated agent-to-agent message transport.

Every message between agents in the `message_passing` strategy goes through this
bus; agents never call each other directly. The bus models:

* latency     — a message sent at tick t is deliverable at t + latency
                (latency 0 = sub-minute radio: delivered in the next protocol phase
                of the same tick)
* loss        — each message is independently dropped with probability `loss`
* duplicates  — at-least-once delivery: a message is delivered twice with probability
                `duplicate`; receivers must process idempotently (dedup by message id)
* partitions  — a message is lost if sender and receiver cannot reach each other at
                send time *or* at delivery time (comms blackout / network partition)

All randomness comes from a dedicated seeded RNG, so runs stay reproducible and the
bus never perturbs the world's own random streams.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from ..simulation.state import WorldState


@dataclass
class Envelope:
    id: str
    type: str
    frm: str
    to: str
    sent_tick: int
    deliver_tick: int
    incident: str = ""
    proposal: str = ""  # proposal / call-for-proposals id this message belongs to
    payload: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


@dataclass
class Bus:
    latency: int = 0
    loss: float = 0.0
    duplicate: float = 0.0
    seed: int = 0
    in_flight: list[Envelope] = field(default_factory=list)
    inbox: dict[str, list[Envelope]] = field(default_factory=dict)
    seen: dict[str, set[str]] = field(default_factory=dict)  # receiver -> processed message ids
    seq: int = 0
    stats: dict[str, int] = field(default_factory=lambda: {"sent": 0, "delivered": 0, "lost": 0, "partitioned": 0, "duplicated": 0, "deduplicated": 0})
    log: list[dict[str, Any]] = field(default_factory=list)  # transport-level drops, drained by the protocol

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed * 31337 + 11)

    def send(self, world: WorldState, type_: str, frm: str, to: str, incident: str = "", proposal: str = "", reason: str = "", **payload: Any) -> Envelope:
        self.seq += 1
        env = Envelope(f"M-{self.seq:06d}", type_, frm, to, world.tick, world.tick + max(0, self.latency), incident, proposal, payload, reason)
        self.stats["sent"] += 1
        # draw both random numbers unconditionally so the stream does not depend on topology
        lost = self.rng.random() < self.loss
        dup = self.rng.random() < self.duplicate
        if not world.reachable(frm, to):
            self._drop(env, "partitioned", "sender and receiver cannot reach each other")
            return env
        if lost:
            self._drop(env, "lost", f"dropped in transit (loss {self.loss:.0%})")
            return env
        self.in_flight.append(env)
        if dup:
            self.stats["duplicated"] += 1
            self.in_flight.append(env)  # same id: at-least-once redelivery
        return env

    def _drop(self, env: Envelope, kind: str, why: str) -> None:
        self.stats[kind] += 1
        self.log.append({"type": "LOST", "msg": env, "reason": why})

    def deliver(self, world: WorldState) -> int:
        """Move every message due by now into its receiver's inbox. Returns count delivered."""
        due = [e for e in self.in_flight if e.deliver_tick <= world.tick]
        if not due:
            return 0
        self.in_flight = [e for e in self.in_flight if e.deliver_tick > world.tick]
        n = 0
        for env in due:  # in_flight is append-ordered, so delivery order is deterministic
            if not world.reachable(env.frm, env.to):
                self._drop(env, "partitioned", "receiver unreachable at delivery time")
                continue
            self.inbox.setdefault(env.to, []).append(env)
            n += 1
        return n

    def take(self, agent_id: str) -> list[Envelope]:
        """Drain an agent's inbox, discarding messages it has already processed."""
        msgs = self.inbox.pop(agent_id, [])
        seen = self.seen.setdefault(agent_id, set())
        out = []
        for env in msgs:
            if env.id in seen:
                self.stats["deduplicated"] += 1
                continue
            seen.add(env.id)
            out.append(env)
            self.stats["delivered"] += 1
        return out

    def pending(self, world: WorldState) -> bool:
        return any(self.inbox.values()) or any(e.deliver_tick <= world.tick for e in self.in_flight)
