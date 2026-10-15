import type { Incident, Resource } from "../types";

export const fmt = (v: number | null | undefined, d = 1) => (v === null || v === undefined || Number.isNaN(v) ? "—" : Number(v).toFixed(d).replace(/\.0+$/, ""));
export const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`);
export const clock = (tick: number) => {
  const h = Math.floor(tick / 60);
  const m = tick % 60;
  return `T+${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
};

export const URGENCY_TONE = (u: number) => (u >= 5 ? "crit" : u >= 4 ? "warn" : u >= 3 ? "info" : "neutral");
export const URGENCY_COLOR = (u: number) => (u >= 5 ? "#dc2626" : u >= 4 ? "#d97706" : u >= 3 ? "#0891b2" : "#71717a");

export const INCIDENT_TONE: Record<string, string> = {
  UNVERIFIED: "neutral",
  SUSPECTED: "warn",
  VERIFIED: "info",
  ASSIGNED: "ink",
  RESCUED: "ok",
  FALSE_ALARM: "neutral",
};

export const UNIT_TONE: Record<string, string> = {
  IDLE: "neutral",
  EN_ROUTE_PICKUP: "info",
  LOADING: "warn",
  EN_ROUTE_SHELTER: "ok",
  UNLOADING: "ok",
  HOLDING: "crit",
  DISABLED: "crit",
};

export const statusLabel = (s: string) => s.replace(/_/g, " ").toLowerCase();

export const isOpen = (i: Incident) => i.status !== "RESCUED" && i.status !== "FALSE_ALARM";
export const unitLabel = (r: Resource) => `${r.id} · ${r.name}`;

export const STRATEGY_LABEL: Record<string, string> = {
  decentralized: "Multi-agent",
  message_passing: "Message-passing",
  centralized: "Centralised",
  greedy: "Greedy",
};

export const NB_COLOR: Record<string, string> = {
  NB: "#0891b2",
  HC: "#7c3aed",
  OQ: "#d97706",
  RS: "#dc2626",
  EM: "#15803d",
};
