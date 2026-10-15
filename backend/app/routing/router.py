"""Resource-specific routing over the shared road + water graph (NetworkX Dijkstra).

`believed_closed` lets a decentralised agent plan on its own (possibly stale)
picture of the network; the safety shield always re-validates against truth.
"""
from __future__ import annotations

from typing import Iterable, Optional

import networkx as nx

from ..simulation.flood import GROUND_MAX_DEPTH
from ..simulation.state import EdgeKind, GraphEdge, RescueResource, ResourceKind, WorldState

def graph_for(world: WorldState) -> nx.Graph:
    """Undirected topology graph (edge ids as attributes). Topology never changes during a run,
    so it is cached on the world itself; an id()-keyed global would hand a new world with a
    different map the graph of a collected one."""
    g = world.__dict__.get("_graph")
    if g is None:
        g = nx.Graph()
        for e in world.edges.values():
            g.add_edge(e.u, e.v, eid=e.id)
        world.__dict__["_graph"] = g
    return g


def edge_between(world: WorldState, a: str, b: str) -> Optional[GraphEdge]:
    data = graph_for(world).get_edge_data(a, b)
    return world.edges[data["eid"]] if data else None


def truly_traversable(e: GraphEdge, kind: str) -> bool:
    return e.ground_ok if kind == ResourceKind.GROUND else e.boat_ok


def speed_factor(e: GraphEdge, kind: str) -> float:
    if kind == ResourceKind.GROUND:
        return e.speed * max(0.35, 1.0 - 0.5 * min(e.depth, GROUND_MAX_DEPTH) / GROUND_MAX_DEPTH)
    if e.kind == EdgeKind.RIVER:
        return 1.0
    if e.kind == EdgeKind.JETTY:
        return 0.5
    return 0.6  # flooded street: debris, low speed


def edge_minutes(e: GraphEdge, kind: str, speed_kmh: float) -> float:
    return e.length_km / (speed_kmh * speed_factor(e, kind)) * 60.0


def _weight(world: WorldState, kind: str, speed: float, closed: Optional[set[str] | frozenset]):
    edges = world.edges

    def w(u: str, v: str, d: dict) -> Optional[float]:
        e = edges[d["eid"]]
        if closed is not None:
            # believed graph: the (possibly stale) set of edges this agent thinks are
            # impassable for its mode — includes mode-incompatible edges by construction
            if e.id in closed:
                return None
            if kind == ResourceKind.GROUND and e.kind not in (EdgeKind.ROAD, EdgeKind.BRIDGE):
                return None
            if kind == ResourceKind.BOAT and e.kind == EdgeKind.BRIDGE:
                return None
            return edge_minutes(e, kind, speed)
        if not truly_traversable(e, kind):
            return None
        return edge_minutes(e, kind, speed)

    return w


def sssp(world: WorldState, kind: str, speed: float, source: str, closed: Optional[set[str] | frozenset] = None):
    """Single-source shortest paths. Returns (dist_minutes, paths)."""
    g = graph_for(world)
    return nx.single_source_dijkstra(g, source, weight=_weight(world, kind, speed, closed))


def believed_closed(world: WorldState, res: RescueResource, delay: int) -> frozenset:
    """Edges the agent believes are closed: the network state it last heard about
    (now - delay, or the start of a comms blackout) plus closures it discovered
    physically, minus re-openings it has seen."""
    seen_tick = world.tick - delay
    if res.blackout_until >= world.tick:
        seen_tick = min(seen_tick, res.blackout_start)
    hist = world.trav_history
    if not hist:
        base: frozenset = frozenset()
    else:
        t = max([k for k in hist if k <= max(seen_tick, min(hist))] or [min(hist)])
        seen_tick = t
        base = hist[t]["ground" if res.kind == ResourceKind.GROUND else "boat"]
    discovered = {e for e, t_disc in res.known_closed.items() if t_disc > seen_tick}
    return frozenset(set(base) | discovered)


def path_edges(world: WorldState, path: list[str]) -> list[GraphEdge]:
    out = []
    for a, b in zip(path, path[1:]):
        e = edge_between(world, a, b)
        if e is not None:
            out.append(e)
    return out


def path_valid(world: WorldState, kind: str, path: Iterable[str]) -> tuple[bool, Optional[str]]:
    p = list(path)
    for e in path_edges(world, p):
        if not truly_traversable(e, kind):
            return False, e.id
    if len(path_edges(world, p)) != max(0, len(p) - 1):
        return False, "missing-edge"
    return True, None


def path_minutes(world: WorldState, kind: str, speed: float, path: list[str]) -> float:
    return sum(edge_minutes(e, kind, speed) for e in path_edges(world, path))


def path_risk(world: WorldState, path: list[str]) -> float:
    es = path_edges(world, path)
    return max((e.risk for e in es), default=0.0)


def origin_options(world: WorldState, res: RescueResource) -> list[tuple[str, float]]:
    """Where a resource can start planning from: its node, or — if mid-edge — either
    end of the edge it is on (continuing forward only if that edge is still open)."""
    if not res.next_node or not res.edge_id:
        return [(res.node, 0.0)]
    e = world.edges[res.edge_id]
    full = edge_minutes(e, res.kind, res.speed_kmh)
    opts = [(res.node, res.edge_progress * full)]  # retreat is always permitted
    if truly_traversable(e, res.kind):
        opts.append((res.next_node, (1 - res.edge_progress) * full))
    return opts


def plan_from_resource(world: WorldState, res: RescueResource, closed: Optional[frozenset] = None):
    """SSSP from a (possibly mid-edge) resource. Returns {target: (minutes, path)}."""
    best: dict[str, tuple[float, list[str]]] = {}
    for origin, offset in origin_options(world, res):
        dist, paths = sssp(world, res.kind, res.speed_kmh, origin, closed)
        for tgt, d in dist.items():
            cand = d + offset
            if tgt not in best or cand < best[tgt][0] - 1e-9:
                best[tgt] = (cand, paths[tgt])
    return best
