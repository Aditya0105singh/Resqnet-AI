import type { StaticWorld, WorldEdge } from "../types";

/** Pixels per km the original SVG markers were designed for (Riverbend ≈ 12 km across ~1000 px). */
export const DESIGN_PX_PER_KM = 83;

export interface Projection {
  lat0: number;
  lon0: number;
  kx: number;
  ky: number;
}

export const xyToLatLng = (p: Projection, x: number, y: number): [number, number] => [p.lat0 - y / p.ky, p.lon0 + x / p.kx];
export const latLngToXY = (p: Projection, lat: number, lng: number): [number, number] => [(lng - p.lon0) * p.kx, (p.lat0 - lat) * p.ky];

/** Web-Mercator pixels per km at a (fractional) zoom and latitude. */
export const pxPerKm = (zoom: number, lat: number) => (256 * 2 ** zoom) / (40075.016 * Math.cos((lat * Math.PI) / 180));

export interface BaseLayer {
  id: string;
  label: string;
  url: string;
  attribution: string;
  subdomains?: string;
  maxZoom: number;
  /** CSS class on each tile (used to mute the basemap so the overlay reads clearly) */
  className?: string;
}

const OSM = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
export const BASE_LAYERS: BaseLayer[] = [
  { id: "light", label: "Light", url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png", attribution: OSM, maxZoom: 19, className: "tiles-muted" },
  { id: "streets", label: "Streets", url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png", attribution: OSM, maxZoom: 19 },
  { id: "terrain", label: "Terrain", url: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", attribution: `${OSM}, SRTM &copy; <a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA)`, subdomains: "abc", maxZoom: 17, className: "tiles-soft" },
  { id: "satellite", label: "Satellite", url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attribution: "Imagery &copy; Esri, Maxar, Earthstar Geographics", maxZoom: 18, className: "tiles-dim" },
];

/** Categorical colours for neighbourhoods, by index, when a map doesn't define its own ids. */
const PALETTE = ["#0891b2", "#7c3aed", "#d97706", "#dc2626", "#15803d", "#db2777", "#4f46e5", "#0d9488"];
export function neighbourhoodColors(world: StaticWorld): Record<string, string> {
  return Object.fromEntries(world.neighbourhoods.map((n, i) => [n.id, PALETTE[i % PALETTE.length]]));
}

export const bridgesOf = (world: StaticWorld) => world.edges.filter((e) => e.kind === "bridge");

export type EdgeLookup = Map<string, WorldEdge>;
export function edgeLookup(world: StaticWorld): EdgeLookup {
  const m: EdgeLookup = new Map();
  for (const e of world.edges) {
    m.set(`${e.u}|${e.v}`, e);
    m.set(`${e.v}|${e.u}`, e);
  }
  return m;
}

/** Polyline (km) for a node path, following real road/river geometry where the map has it. */
export function pathPoints(
  ids: string[],
  nodes: Record<string, { x: number; y: number }>,
  edges: EdgeLookup,
  from?: { x: number; y: number },
): [number, number][] {
  const out: [number, number][] = [];
  const push = (p: [number, number]) => {
    const last = out[out.length - 1];
    if (!last || Math.hypot(last[0] - p[0], last[1] - p[1]) > 1e-4) out.push(p);
  };
  for (let i = 0; i < ids.length - 1; i++) {
    const a = nodes[ids[i]];
    const b = nodes[ids[i + 1]];
    if (!a || !b) continue;
    const e = edges.get(`${ids[i]}|${ids[i + 1]}`);
    let seg: [number, number][] = e?.geometry ? (e.u === ids[i] ? e.geometry : [...e.geometry].reverse()) : [[a.x, a.y], [b.x, b.y]];
    if (i === 0 && from && seg.length > 2) {
      // unit is part-way along the first edge: keep only what is left of it
      let best = 0;
      let bd = Infinity;
      for (let k = 0; k < seg.length - 1; k++) {
        const d = distToSeg(from.x, from.y, seg[k], seg[k + 1]);
        if (d < bd) {
          bd = d;
          best = k;
        }
      }
      seg = seg.slice(best + 1);
    }
    seg.forEach(push);
  }
  if (from) out.unshift([from.x, from.y]);
  return out;
}

function distToSeg(px: number, py: number, a: [number, number], b: [number, number]) {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const l2 = dx * dx + dy * dy;
  const t = l2 ? Math.max(0, Math.min(1, ((px - a[0]) * dx + (py - a[1]) * dy) / l2)) : 0;
  return Math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy));
}

export const toPoints = (pts: [number, number][]) => pts.map((p) => `${p[0]},${p[1]}`).join(" ");
