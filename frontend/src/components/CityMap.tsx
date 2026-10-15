import { useMemo, useRef, useState } from "react";
import { Minus, Plus, Scan } from "lucide-react";
import type { StaticWorld } from "../types";
import { useSim, type Layers, type Selection } from "../store/sim";
import { NB_COLOR, statusLabel, URGENCY_COLOR } from "../lib/format";
import { cx } from "./ui";

/** Minimal frame shape the map needs (full frames and counterfactual compact frames). */
export interface MapFrame {
  route_ghosts?: {resource: string; tick: number; edge: string; path: string[]}[];
  tick: number;
  resources: { id: string; kind: string; x: number; y: number; status: string; load: number; incident_id: string | null; route: string[]; blackout_until?: number | null; partition?: string | null }[];
  incidents: { id: string; x: number; y: number; status: string; urgency: number; people: number; unassigned: number; confidence?: number; provisional?: boolean }[];
  shelters: { id: string; x: number; y: number; capacity: number; occupancy: number; reserved: number; name?: string }[];
  edges: Record<string, number[]>;
  depths?: Record<string, number>;
}

interface Props {
  world: StaticWorld;
  frame: MapFrame;
  layers?: Partial<Layers>;
  selection?: Selection;
  onSelect?: (s: Selection) => void;
  onEdgeClick?: (edgeId: string) => void;
  onNodeClick?: (nodeId: string) => void;
  mode?: "select" | "close-edge" | "new-incident";
  transitionMs?: number;
  compact?: boolean;
  className?: string;
  highlight?: string[];
}

const ALL: Layers = { roads: true, water: true, flood: true, closures: true, routes: true, incidents: true, units: true, shelters: true, uncertain: true, labels: false };
const PAD = 0.7;

/** Map symbols are sized for Riverbend's ~10 km extent. Other cities are drawn in display
 * units (km ÷ extent/10) so markers keep their size; distances in the engine stay in km. */
function displayScale(world: StaticWorld): number {
  if (world.name.startsWith("Riverbend")) return 1;
  const xs = world.nodes.map((n) => n.x), ys = world.nodes.map((n) => n.y);
  const extent = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
  return extent > 0 ? extent / 10 : 1;
}

export function CityMap({ world: rawWorld, frame: rawFrame, layers: layerProp, selection, onSelect, onEdgeClick, onNodeClick, mode = "select", transitionMs = 900, compact, className, highlight = [] }: Props) {
  const u = useMemo(() => displayScale(rawWorld), [rawWorld]);
  const world = useMemo(() => {
    if (u === 1) return rawWorld;
    const sp = (pts?: number[][]) => pts?.map(([x, y]) => [x / u, y / u]);
    const bm = rawWorld.basemap;
    return {
      ...rawWorld,
      nodes: rawWorld.nodes.map((n) => ({ ...n, x: n.x / u, y: n.y / u })),
      edges: rawWorld.edges.map((e) => (e.geometry ? { ...e, geometry: sp(e.geometry) } : e)),
      basemap: bm && Object.fromEntries(Object.entries(bm).map(([k, v]) => [k, (v ?? []).map((pts) => sp(pts)!)])),
    };
  }, [rawWorld, u]);
  const frame = useMemo(() => {
    if (u === 1) return rawFrame;
    const sc = <T extends { x: number; y: number }>(xs: T[]) => xs.map((e) => ({ ...e, x: e.x / u, y: e.y / u }));
    return { ...rawFrame, resources: sc(rawFrame.resources), incidents: sc(rawFrame.incidents), shelters: sc(rawFrame.shelters) };
  }, [rawFrame, u]);
  const layers = { ...ALL, ...layerProp };
  const nodes = useMemo(() => Object.fromEntries(world.nodes.map((n) => [n.id, n])), [world]);
  // real road shapes, looked up by node pair in either direction (display only)
  const shapes = useMemo(() => {
    const m: Record<string, number[][]> = {};
    for (const e of world.edges) {
      if (!e.geometry) continue;
      m[e.u + ">" + e.v] = e.geometry;
      m[e.v + ">" + e.u] = [...e.geometry].reverse();
    }
    return m;
  }, [world]);
  const edgePts = (e: { u: string; v: string; geometry?: number[][] }) => e.geometry ?? [[nodes[e.u].x, nodes[e.u].y], [nodes[e.v].x, nodes[e.v].y]];
  /** Node path → polyline points following real road shapes where known. */
  const pathPts = (ids: string[], start?: [number, number]) => {
    const out: number[][] = start ? [start] : [];
    ids.forEach((id, i) => {
      const prev = ids[i - 1];
      const shape = prev ? shapes[prev + ">" + id] : undefined;
      if (shape) out.push(...shape.slice(1));
      else if (nodes[id]) out.push([nodes[id].x, nodes[id].y]);
    });
    return out.map((p) => p.join(",")).join(" ");
  };
  const bounds = useMemo(() => {
    const xs = world.nodes.map((n) => n.x);
    const ys = world.nodes.map((n) => n.y);
    return { x0: Math.min(...xs) - PAD, y0: Math.min(...ys) - PAD, w: Math.max(...xs) - Math.min(...xs) + 2 * PAD, h: Math.max(...ys) - Math.min(...ys) + 2 * PAD };
  }, [world]);
  // river nodes in channel order (R0, R1, …): a real river can meander back on itself
  const river = useMemo(() => world.nodes.filter((n) => n.kind === "river").sort((a, b) => Number(a.id.slice(1)) - Number(b.id.slice(1)) || a.x - b.x), [world]);
  const nbColor = useMemo(() => {
    const extra = ["#0891b2", "#7c3aed", "#d97706", "#dc2626", "#15803d", "#db2777", "#0d9488", "#4f46e5"];
    return Object.fromEntries(world.neighbourhoods.map((z, i) => [z.id, NB_COLOR[z.id] ?? extra[i % extra.length]]));
  }, [world]);
  const nbCentroids = useMemo(() => {
    const acc: Record<string, { x: number; y: number; n: number }> = {};
    for (const n of world.nodes) {
      if (n.kind === "river") continue;
      const a = (acc[n.neighbourhood] ??= { x: 0, y: 0, n: 0 });
      a.x += n.x;
      a.y += n.y;
      a.n += 1;
    }
    return Object.entries(acc).map(([id, a]) => ({ id, x: a.x / a.n, y: a.y / a.n, name: world.neighbourhoods.find((z) => z.id === id)?.name ?? id }));
  }, [world]);

  // area tint: discs overlap more in dense real cities, so each is fainter there
  const tint = useMemo(() => 0.035 * Math.min(1, 60 / Math.max(1, world.nodes.length)), [world]);
  const [view, setView] = useState({ k: 1, tx: 0, ty: 0 });
  const drag = useRef<{ x: number; y: number; tx: number; ty: number; moved: boolean } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const scaleOf = () => {
    const r = svgRef.current!.getBoundingClientRect();
    return Math.min(r.width / bounds.w, r.height / bounds.h);
  };
  const onWheel = (e: React.WheelEvent) => {
    const k2 = Math.max(1, Math.min(4, view.k * (e.deltaY < 0 ? 1.15 : 1 / 1.15)));
    setView((v) => ({ ...v, k: k2 }));
  };
  const onDown = (e: React.PointerEvent) => {
    drag.current = { x: e.clientX, y: e.clientY, tx: view.tx, ty: view.ty, moved: false };
  };
  const onMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d || e.buttons !== 1) return;
    const sc = scaleOf() * view.k;
    const mx = (e.clientX - d.x) / sc;
    const my = (e.clientY - d.y) / sc;
    if (Math.abs(mx) + Math.abs(my) > 0.05) d.moved = true;
    setView((v) => ({ ...v, tx: d.tx + mx, ty: d.ty + my }));
  };
  const onUp = () => {
    setTimeout(() => (drag.current = null), 0);
  };
  const clicked = () => !drag.current?.moved;

  const sw = (px: number) => px / 100; // stroke widths in world units
  const routeColor = (status: string) => (status === "EN_ROUTE_SHELTER" || status === "UNLOADING" ? "#15803d" : status === "HOLDING" ? "#dc2626" : "#0891b2");
  const sel = (t: string, id: string) => selection?.type === t && selection.id === id;
  const depths = frame.depths ?? {};

  return (
    <div className={cx("relative h-full w-full overflow-hidden rounded-[inherit] bg-[#fbfbfa]", mode !== "select" && "cursor-crosshair", className)}>
      <svg
        ref={svgRef}
        viewBox={`${bounds.x0} ${bounds.y0} ${bounds.w} ${bounds.h}`}
        className="h-full w-full touch-none select-none"
        preserveAspectRatio="xMidYMid meet"
        onWheel={onWheel}
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerLeave={onUp}
        role="img"
        aria-label={`Map of ${world.name}`}
      >
        <defs>
          <filter id="blur-flood" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="0.18" />
          </filter>
          <pattern id="grid" width="0.5" height="0.5" patternUnits="userSpaceOnUse">
            <path d="M0.5 0H0V0.5" fill="none" stroke="#000" strokeOpacity="0.035" strokeWidth={sw(1)} />
          </pattern>
        </defs>
        <rect x={bounds.x0} y={bounds.y0} width={bounds.w} height={bounds.h} fill="url(#grid)" />
        <g transform={`translate(${bounds.x0 + bounds.w / 2} ${bounds.y0 + bounds.h / 2}) scale(${view.k}) translate(${-(bounds.x0 + bounds.w / 2) + view.tx} ${-(bounds.y0 + bounds.h / 2) + view.ty})`}>
          {/* districts */}
          {world.nodes
            .filter((n) => n.kind !== "river")
            .map((n) => (
              <circle key={"d" + n.id} cx={n.x} cy={n.y} r={0.78} fill={nbColor[n.neighbourhood]} opacity={tint} />
            ))}
          {/* background map: buildings, parks, ponds, streams, railway (display only) */}
          {world.basemap && !compact && (
            <g pointerEvents="none">
              {world.basemap.green?.map((p, i) => <polygon key={"g" + i} points={p.map((q) => q.join(",")).join(" ")} fill="#dfeedd" />)}
              {world.basemap.water?.map((p, i) => <polygon key={"w" + i} points={p.map((q) => q.join(",")).join(" ")} fill="#cfe6f2" />)}
              {world.basemap.streams?.map((p, i) => <polyline key={"s" + i} points={p.map((q) => q.join(",")).join(" ")} fill="none" stroke="#bcdcec" strokeWidth={sw(2)} />)}
              {world.basemap.buildings?.map((p, i) => <polygon key={"b" + i} points={p.map((q) => q.join(",")).join(" ")} fill="#dcd8cf" stroke="#c9c4b8" strokeWidth={sw(0.6)} />)}
              {world.basemap.rail?.map((p, i) => (
                <g key={"r" + i}>
                  <polyline points={p.map((q) => q.join(",")).join(" ")} fill="none" stroke="#a8a29e" strokeWidth={sw(3)} />
                  <polyline points={p.map((q) => q.join(",")).join(" ")} fill="none" stroke="#fff" strokeWidth={sw(1.4)} strokeDasharray="0.05 0.05" />
                </g>
              ))}
            </g>
          )}
          {/* river */}
          {layers.water && (
            <>
              <polyline
                points={(u === 1 ? [`${river[0].x - 1.2},${river[0].y}`, ...river.map((r) => `${r.x},${r.y}`), `${river[river.length - 1].x + 1.2},${river[river.length - 1].y}`] : river.map((r) => `${r.x},${r.y}`)).join(" ")}
                fill="none"
                stroke="#d4e9f4"
                strokeWidth={0.62 + Math.max(0, (frame as any).river_level ? ((frame as any).river_level - 2) * 0.1 : 0)}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <polyline points={river.map((r) => `${r.x},${r.y}`).join(" ")} fill="none" stroke="#b9dbec" strokeWidth={0.16} strokeLinecap="round" strokeDasharray="0.02 0.18" />
            </>
          )}
          {/* flood */}
          {layers.flood && (
            <g filter="url(#blur-flood)">
              {Object.entries(depths).map(([id, d]) => {
                const n = nodes[id];
                if (!n || n.kind === "river") return null;
                return <circle key={"f" + id} cx={n.x} cy={n.y} r={0.35 + 0.28 * Math.min(d, 2)} fill={d >= 0.5 ? "#7fb9d6" : "#a9d2e6"} opacity={0.22 + 0.28 * Math.min(d / 1.6, 1)} />;
              })}
            </g>
          )}
          {/* district labels */}
          {!compact &&
            nbCentroids.map((c) => (
              <text key={"nl" + c.id} x={c.x} y={c.y + (c.y < 3 ? -0.95 : 1.05)} textAnchor="middle" fontSize={0.2} fontFamily="JetBrains Mono" letterSpacing={0.02} fill={nbColor[c.id]} opacity={0.85} stroke="#fff" strokeWidth={0.06} strokeOpacity={0.85} paintOrder="stroke" style={{ pointerEvents: "none" }}>
                {c.name.toUpperCase()}
              </text>
            ))}
          {/* edges */}
          {layers.roads &&
            world.edges.map((e) => {
              const a = nodes[e.u];
              const b = nodes[e.v];
              const st = frame.edges[e.id] ?? [1, 0, 0];
              const [g, boat, manual] = st;
              const isWater = e.kind === "river" || e.kind === "jetty";
              if (isWater && !layers.water) return null;
              let stroke = "#cfcfca";
              let width = sw(4.5);
              let dash: string | undefined;
              let op = 1;
              if (e.kind === "bridge") {
                stroke = "#27272a";
                width = sw(9);
              }
              if (e.kind === "jetty") {
                stroke = "#8cc3dd";
                width = sw(2.5);
                dash = "0.05 0.06";
              }
              if (e.kind === "river") {
                stroke = "transparent";
              }
              if (!isWater && !g && layers.closures) {
                stroke = boat ? "#6fb2d3" : "#93c5dd";
                dash = "0.1 0.07";
                op = 0.9;
              }
              if (manual && layers.closures) {
                stroke = "#dc2626";
                dash = "0.12 0.08";
                width = sw(e.kind === "bridge" ? 9 : 6);
              }
              if (!isWater && !g && e.kind === "bridge" && !manual && layers.closures) {
                stroke = "#d97706";
                dash = "0.12 0.08";
              }
              const P = edgePts(e);
              const ep = P.map((q) => q.join(",")).join(" ");
              const mid = P[Math.floor((P.length - 1) / 2)];
              const mid2 = P[Math.ceil((P.length - 1) / 2)];
              const mx = P.length % 2 ? mid[0] : (mid[0] + mid2[0]) / 2;
              const my = P.length % 2 ? mid[1] : (mid[1] + mid2[1]) / 2;
              const hot = sel("edge", e.id);
              return (
                <g key={e.id}>
                  {boat && e.kind === "road" && layers.flood ? <polyline points={ep} fill="none" stroke="#cfe6f2" strokeWidth={sw(14)} strokeLinecap="round" strokeLinejoin="round" /> : null}
                  <polyline points={ep} fill="none" stroke={hot ? "#0891b2" : stroke} strokeWidth={hot ? width * 1.6 : width} strokeDasharray={dash} strokeLinecap="round" strokeLinejoin="round" opacity={op} />
                  {(onEdgeClick || onSelect) && !isWater && (
                    <polyline
                      points={ep}
                      fill="none"
                      stroke="transparent"
                      strokeWidth={sw(22)}
                      className={cx(mode === "close-edge" && "cursor-pointer hover:stroke-[#dc262633]")}
                      onClick={() => {
                        if (!clicked()) return;
                        if (mode === "close-edge" && onEdgeClick) onEdgeClick(e.id);
                        else onSelect?.({ type: "edge", id: e.id });
                      }}
                    >
                      <title>{`${e.name || e.id} · ${e.kind}${manual ? " · CLOSED" : !g ? " · impassable for ground" : ""}${boat && e.kind === "road" ? " · navigable by boat" : ""}`}</title>
                    </polyline>
                  )}
                  {manual && layers.closures ? (
                    <g transform={`translate(${mx} ${my})`}>
                      <circle r={0.11} fill="#fff" stroke="#dc2626" strokeWidth={sw(2.5)} />
                      <path d="M-0.05 -0.05L0.05 0.05M0.05 -0.05L-0.05 0.05" stroke="#dc2626" strokeWidth={sw(2.5)} strokeLinecap="round" />
                    </g>
                  ) : null}
                  {e.kind === "bridge" && !compact && (
                    <text x={mx + 0.16} y={my + 0.05} fontSize={0.15} fontFamily="JetBrains Mono" fill={manual ? "#dc2626" : "#3f3f46"} stroke="#fff" strokeWidth={0.05} paintOrder="stroke" style={{ pointerEvents: "none" }}>
                      {e.name}
                    </text>
                  )}
                </g>
              );
            })}
          {/* nodes (for incident placement) */}
          {mode === "new-incident" &&
            world.nodes
              .filter((n) => n.kind === "land")
              .map((n) => (
                <circle key={"n" + n.id} cx={n.x} cy={n.y} r={0.12} fill="#fff" stroke="#0891b2" strokeWidth={sw(2)} className="cursor-pointer hover:fill-[#e0f7fb]" onClick={() => clicked() && onNodeClick?.(n.id)}>
                  <title>{`${n.id} · ${n.neighbourhood} · elev ${n.elevation} m · depth ${depths[n.id] ?? 0} m`}</title>
                </circle>
              ))}
          {layers.labels &&
            world.nodes.map((n) => (
              <text key={"lb" + n.id} x={n.x} y={n.y - 0.13} fontSize={0.11} textAnchor="middle" fontFamily="JetBrains Mono" fill="#a1a1aa">
                {n.id}
              </text>
            ))}
          {/* routes */}
          {layers.routes && frame.route_ghosts?.map((g, i) => (
            <polyline key={`${g.resource}-${g.tick}-${i}`} points={pathPts(g.path.filter((id) => nodes[id]))}
              fill="none" stroke="#e11d48" strokeWidth={sw(4)} strokeDasharray="0.12 0.1" opacity={0.65} pointerEvents="none">
              <title>{g.resource}: route before {g.edge} closed at minute {g.tick}</title>
            </polyline>
          ))}
          {layers.routes &&
            frame.resources.map((r) => {
              if (!r.route?.length || r.status === "DISABLED") return null;
              const ptsStr = pathPts(r.route.filter((id) => nodes[id]), [r.x, r.y]);
              const c = routeColor(r.status);
              const hot = sel("resource", r.id);
              return (
                <g key={"rt" + r.id} opacity={selection && !hot && selection.type === "resource" ? 0.25 : 1}>
                  <polyline points={ptsStr} fill="none" stroke={c} strokeOpacity={0.18} strokeWidth={sw(hot ? 16 : 11)} strokeLinecap="round" strokeLinejoin="round" />
                  <polyline points={ptsStr} fill="none" stroke={c} strokeWidth={sw(hot ? 4 : 2.6)} strokeDasharray="0.06 0.06" pathLength={undefined} className="route-dash" strokeLinecap="round" strokeLinejoin="round" style={{ strokeDashoffset: 0 }} />
                </g>
              );
            })}
          {/* shelters */}
          {layers.shelters &&
            frame.shelters.map((s) => {
              const full = s.occupancy + s.reserved >= s.capacity;
              const occ = s.capacity ? Math.min(1, s.occupancy / s.capacity) : 1;
              const res = s.capacity ? Math.min(1 - occ, s.reserved / s.capacity) : 0;
              const hot = sel("shelter", s.id);
              return (
                <g key={s.id} transform={`translate(${s.x} ${s.y})`} className="cursor-pointer" onClick={() => clicked() && onSelect?.({ type: "shelter", id: s.id })}>
                  <title>{`${s.id} ${s.name ?? ""} · ${s.occupancy}/${s.capacity} occupied · ${s.reserved} reserved`}</title>
                  {hot && <rect x={-0.27} y={-0.27} width={0.54} height={0.54} rx={0.1} fill="none" stroke="#0891b2" strokeWidth={sw(3)} />}
                  <rect x={-0.2} y={-0.2} width={0.4} height={0.4} rx={0.07} fill={full ? "#fee2e2" : "#fff"} stroke={full ? "#dc2626" : "#0a0a0a"} strokeWidth={sw(2.6)} />
                  <path d="M-0.1 0.06V-0.02L0 -0.1L0.1 -0.02V0.06Z" fill={full ? "#dc2626" : "#0a0a0a"} />
                  <rect x={-0.24} y={0.26} width={0.48} height={0.06} rx={0.03} fill="#e4e4e0" />
                  <rect x={-0.24} y={0.26} width={0.48 * occ} height={0.06} rx={0.03} fill={full ? "#dc2626" : "#0a0a0a"} />
                  <rect x={-0.24 + 0.48 * occ} y={0.26} width={0.48 * res} height={0.06} fill="#22d3ee" />
                  {!compact && (
                    <text x={0} y={0.48} textAnchor="middle" fontSize={0.13} fontFamily="JetBrains Mono" fill="#3f3f46">
                      {s.id} {s.occupancy}/{s.capacity}
                    </text>
                  )}
                </g>
              );
            })}
          {/* incidents */}
          {layers.incidents &&
            frame.incidents.map((i) => {
              const done = i.status === "RESCUED";
              const fa = i.status === "FALSE_ALARM";
              const uncertain = i.status === "UNVERIFIED" || i.status === "SUSPECTED" || i.status === "DISPUTED";
              if (uncertain && !layers.uncertain) return null;
              const c = URGENCY_COLOR(i.urgency);
              const r = 0.1 + Math.min(0.12, i.people * 0.012);
              const hot = sel("incident", i.id) || highlight.includes(i.id);
              const open = !done && !fa;
              return (
                <g key={i.id} transform={`translate(${i.x + 0.0} ${i.y})`} className="cursor-pointer" onClick={() => clicked() && onSelect?.({ type: "incident", id: i.id })} opacity={done || fa ? 0.55 : 1}>
                  <title>{`${i.id} · ${i.status} · urgency ${i.urgency} · ${i.people} waiting${i.confidence !== undefined ? ` · confidence ${i.confidence}` : ""}`}</title>
                  {open && i.urgency >= 5 && i.unassigned > 0 && <circle r={0.3} fill={c} className="pulse" />}
                  {hot && <circle r={r + 0.12} fill="none" stroke="#0891b2" strokeWidth={sw(3)} />}
                  {done ? (
                    <>
                      <circle r={0.09} fill="#15803d" />
                      <path d="M-0.04 0L-0.01 0.03L0.045 -0.03" stroke="#fff" strokeWidth={sw(2.4)} fill="none" strokeLinecap="round" />
                    </>
                  ) : fa ? (
                    <>
                      <circle r={0.09} fill="#fff" stroke="#a1a1aa" strokeWidth={sw(2)} />
                      <path d="M-0.035 -0.035L0.035 0.035M0.035 -0.035L-0.035 0.035" stroke="#a1a1aa" strokeWidth={sw(2)} />
                    </>
                  ) : (
                    <>
                      <rect x={-r} y={-r} width={2 * r} height={2 * r} transform="rotate(45)" rx={0.025} fill={i.unassigned > 0 ? c : "#fff"} stroke={c} strokeWidth={sw(uncertain ? 2.2 : 3)} strokeDasharray={uncertain ? "0.035 0.03" : undefined} fillOpacity={uncertain && i.unassigned > 0 ? 0.55 : 1} />
                      {!compact && (
                        <text y={0.035} textAnchor="middle" fontSize={0.11} fontWeight={600} fontFamily="JetBrains Mono" fill={i.unassigned > 0 ? "#fff" : c}>
                          {i.people}
                        </text>
                      )}
                    </>
                  )}
                  {!compact && open && (
                    <text x={r + 0.06} y={-r} fontSize={0.12} fontFamily="JetBrains Mono" fill="#52525b">
                      {i.id.replace("I-0", "I")}
                    </text>
                  )}
                </g>
              );
            })}
          {/* units */}
          {layers.units &&
            frame.resources.map((r) => {
              const hot = sel("resource", r.id);
              const dis = r.status === "DISABLED";
              const hold = r.status === "HOLDING";
              const black = (r.blackout_until !== null && r.blackout_until !== undefined) || !!r.partition;
              return (
                <g
                  key={r.id}
                  className="unit cursor-pointer"
                  style={{ transform: `translate(${r.x}px, ${r.y}px)`, transitionDuration: `${transitionMs}ms` }}
                  onClick={() => clicked() && onSelect?.({ type: "resource", id: r.id })}
                >
                  <title>{`${r.kind === "boat" ? "Boat" : "Road team"} ${r.id} · ${statusLabel(r.status)}${r.load ? ` · ${r.load} aboard` : ""}${black ? (r.partition ? ` · cut off from the network (${r.partition})` : " · no radio contact") : ""} · click for details`}</title>
                  {hot && <circle r={0.3} fill="#22d3ee" opacity={0.18} />}
                  {hold && <circle r={0.26} fill="none" stroke="#dc2626" strokeWidth={sw(2)} className="pulse" />}
                  {r.kind === "boat" ? (
                    <path d="M-0.17 -0.07H0.1L0.19 0L0.1 0.07H-0.17Z" fill={dis ? "#fff" : "#0a0a0a"} stroke={dis ? "#dc2626" : hot ? "#22d3ee" : "#fff"} strokeWidth={sw(2)} />
                  ) : (
                    <rect x={-0.13} y={-0.09} width={0.26} height={0.18} rx={0.05} fill={dis ? "#fff" : "#0e7490"} stroke={dis ? "#dc2626" : hot ? "#22d3ee" : "#fff"} strokeWidth={sw(2)} />
                  )}
                  <text y={0.04} x={r.kind === "boat" ? -0.02 : 0} textAnchor="middle" fontSize={0.1} fontWeight={600} fontFamily="JetBrains Mono" fill={dis ? "#dc2626" : "#fff"}>
                    {r.id}
                  </text>
                  {r.load > 0 && (
                    <g transform="translate(0.17 -0.14)">
                      <circle r={0.075} fill="#15803d" />
                      <text y={0.03} textAnchor="middle" fontSize={0.085} fontWeight={700} fill="#fff" fontFamily="JetBrains Mono">
                        {r.load}
                      </text>
                    </g>
                  )}
                  {black && (
                    <text x={0} y={-0.16} textAnchor="middle" fontSize={0.09} fontFamily="JetBrains Mono" fill="#b45309">
                      no comms
                    </text>
                  )}
                </g>
              );
            })}
        </g>
      </svg>
      {world.attribution && <div className="no-print pointer-events-none absolute bottom-1 left-2 text-[10px] text-mute">{world.attribution}</div>}
      {!compact && (
        <div className="no-print absolute right-3 bottom-3 flex flex-col overflow-hidden rounded-xl border border-line-2 bg-white/90 shadow-sm backdrop-blur">
          <button aria-label="Zoom in" className="p-1.5 hover:bg-wash" onClick={() => setView((v) => ({ ...v, k: Math.min(4, v.k * 1.25) }))}>
            <Plus className="size-4" />
          </button>
          <button aria-label="Zoom out" className="border-t border-line p-1.5 hover:bg-wash" onClick={() => setView((v) => ({ ...v, k: Math.max(1, v.k / 1.25) }))}>
            <Minus className="size-4" />
          </button>
          <button aria-label="Reset view" className="border-t border-line p-1.5 hover:bg-wash" onClick={() => setView({ k: 1, tx: 0, ty: 0 })}>
            <Scan className="size-4" />
          </button>
        </div>
      )}
    </div>
  );
}

export function MapLegend() {
  const layers = useSim((s) => s.layers);
  const toggle = useSim((s) => s.toggleLayer);
  const item = (el: React.ReactNode, label: string, layer: keyof Layers) => (
    <button type="button" onClick={() => toggle(layer)} aria-pressed={layers[layer]} title={`${layers[layer] ? "Hide" : "Show"} ${label} on the map`} className={cx("inline-flex items-center gap-1.5 rounded px-0.5 hover:text-ink", !layers[layer] && "line-through opacity-50")}>
      {el}
      {label}
    </button>
  );
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11.5px] text-mute">
      {item(<span className="inline-block size-2.5 rotate-45 rounded-[2px] bg-crit" />, "urgent request", "incidents")}
      {item(<span className="inline-block size-2.5 rotate-45 rounded-[2px] border border-dashed border-warn" />, "unconfirmed", "uncertain")}
      {item(<svg viewBox="-0.2 -0.1 0.4 0.2" className="h-2.5 w-4"><path d="M-0.17 -0.07H0.1L0.19 0L0.1 0.07H-0.17Z" fill="#0a0a0a" /></svg>, "boat", "units")}
      {item(<span className="inline-block h-2.5 w-3.5 rounded-sm bg-brand" />, "road team", "units")}
      {item(<span className="inline-block size-2.5 rounded-[3px] border-[1.5px] border-ink" />, "shelter", "shelters")}
      {item(<span className="inline-block h-0.5 w-4 border-t-2 border-dashed border-info" />, "route", "routes")}
      {item(<span className="inline-block h-0.5 w-4 border-t-2 border-dashed border-crit" />, "closed", "closures")}
      {item(<span className="inline-block h-0.5 w-4 border-t-2 border-dashed border-[#93c5dd]" />, "flooded", "flood")}
    </div>
  );
}
