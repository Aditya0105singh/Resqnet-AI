import { create } from "zustand";
import { api, ApiError } from "../lib/api";
import type { AuditRecord, Frame, RoundSummary, SimSummary, StaticWorld, Strategy } from "../types";

export type Selection = { type: "incident" | "resource" | "shelter" | "edge"; id: string } | null;
export type Conn = "connecting" | "live" | "reconnecting" | "offline";
export interface Toast {
  id: number;
  kind: "ok" | "warn" | "crit" | "info";
  title: string;
  body?: string;
}
export interface Layers {
  roads: boolean;
  water: boolean;
  flood: boolean;
  closures: boolean;
  routes: boolean;
  incidents: boolean;
  units: boolean;
  shelters: boolean;
  uncertain: boolean;
  labels: boolean;
}

interface SimState {
  world: StaticWorld | null;
  sim: SimSummary | null;
  frame: Frame | null;
  conn: Conn;
  audit: AuditRecord[];
  rounds: RoundSummary[];
  selection: Selection;
  decisionId: string | null;
  layers: Layers;
  toasts: Toast[];
  lastSeq: number;
  busy: Record<string, boolean>;
  setSelection: (s: Selection) => void;
  askOpen: boolean;
  setAskOpen: (v: boolean) => void;
  openDecision: (id: string | null) => void;
  toggleLayer: (k: keyof Layers) => void;
  toast: (t: Omit<Toast, "id">) => void;
  dismiss: (id: number) => void;
  loadWorld: () => Promise<void>;
  bootstrap: () => Promise<void>;
  createSim: (scenario: string, strategy: Strategy, overrides?: Record<string, unknown>) => Promise<void>;
  attach: (id: string) => Promise<void>;
  control: (action: "start" | "pause" | "reset" | "step", ticks?: number) => Promise<void>;
  setSpeed: (speed: number) => Promise<void>;
  inject: (type: string, params: Record<string, unknown>, label?: string) => Promise<boolean>;
  /** The latest failure injected from the UI, for the "what just happened" card. */
  disruption: Disruption | null;
  clearDisruption: () => void;
  applySocket: (msg: any) => void;
  setConn: (c: Conn) => void;
}

export interface Disruption {
  id: number;
  label: string;
  tick: number;
  effects: string[];
  /** affected rescue requests and the units they had before the failure */
  affected: { incident: string; before: string[] }[];
}
const FAILURES = new Set(["TRIPLE_FAILURE", "CLOSE_EDGE", "RESOURCE_FAILURE", "SHELTER_CAPACITY", "FLOOD_SURGE", "COMM_BLACKOUT", "NETWORK_PARTITION", "CONTRADICTORY_REPORT"]);
let disruptionSeq = 1;

const SIM_KEY = "resqnet.sim";
let toastSeq = 1;

export const useSim = create<SimState>((set, get) => ({
  world: null,
  sim: null,
  frame: null,
  conn: "connecting",
  audit: [],
  rounds: [],
  selection: null,
  decisionId: null,
  layers: { roads: true, water: true, flood: true, closures: true, routes: true, incidents: true, units: true, shelters: true, uncertain: true, labels: false },
  toasts: [],
  disruption: null,
  clearDisruption: () => set({ disruption: null }),
  lastSeq: 0,
  busy: {},
  setSelection: (selection) => set({ selection }),
  askOpen: false,
  setAskOpen: (askOpen) => set({ askOpen }),
  openDecision: (decisionId) => set({ decisionId }),
  toggleLayer: (k) => set((s) => ({ layers: { ...s.layers, [k]: !s.layers[k] } })),
  toast: (t) => {
    const id = toastSeq++;
    set((s) => ({ toasts: [...s.toasts.slice(-4), { ...t, id }] }));
    setTimeout(() => get().dismiss(id), t.kind === "crit" ? 7000 : 4500);
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })),
  loadWorld: async () => {
    if (get().world) return;
    const world = await api.get<StaticWorld>("/api/world");
    set({ world });
  },
  bootstrap: async () => {
    try {
      await get().loadWorld();
    } catch (e) {
      set({ conn: "offline" });
      get().toast({ kind: "crit", title: "Backend unreachable", body: (e as Error).message });
      return;
    }
    let id: string | null = null;
    try {
      id = localStorage.getItem(SIM_KEY);
    } catch {
      /* storage unavailable */
    }
    if (id) {
      try {
        await get().attach(id);
        return;
      } catch {
        /* stale id → create fresh */
      }
    }
    // open on the real Aluva map when it is installed; Riverbend (synthetic) otherwise
    const geos = await api.get<{ geographies: { id: string }[] }>("/api/geographies").catch(() => ({ geographies: [] }));
    await get().createSim("normal", "decentralized", geos.geographies.some((g) => g.id === "aluva") ? { geography: "aluva" } : {});
  },
  createSim: async (scenario, strategy, overrides = {}) => {
    set((s) => ({ busy: { ...s.busy, create: true } }));
    try {
      const r = await api.post<SimSummary & { frame: Frame }>("/api/simulations", { scenario, strategy, overrides });
      const { frame, ...sim } = r;
      try {
        localStorage.setItem(SIM_KEY, sim.id);
      } catch {
        /* ignore */
      }
      set({ sim, frame, audit: [], rounds: [], selection: null, decisionId: null, lastSeq: 0 });
      set({ world: await api.get<StaticWorld>(`/api/world?sim=${sim.id}`) }); // each run may use a different city
    } catch (e) {
      get().toast({ kind: "crit", title: "Could not create simulation", body: (e as Error).message });
      throw e;
    } finally {
      set((s) => ({ busy: { ...s.busy, create: false } }));
    }
  },
  attach: async (id) => {
    const r = await api.get<SimSummary & { frame: Frame }>(`/api/simulations/${id}`);
    const { frame, ...sim } = r;
    try {
      localStorage.setItem(SIM_KEY, sim.id);
    } catch {
      /* ignore */
    }
    set({ sim, frame, audit: [], rounds: [], selection: null, lastSeq: 0 });
    set({ world: await api.get<StaticWorld>(`/api/world?sim=${sim.id}`) });
  },
  control: async (action, ticks = 1) => {
    const sim = get().sim;
    if (!sim) return;
    set((s) => ({ busy: { ...s.busy, [action]: true } }));
    try {
      const r = await api.post<any>(`/api/simulations/${sim.id}/${action}`, action === "step" ? { ticks } : {});
      const { frame, ...summary } = r;
      set((s) => ({ sim: { ...s.sim!, ...summary }, ...(frame ? { frame } : {}), ...(action === "reset" ? { audit: [], rounds: [], selection: null } : {}) }));
    } catch (e) {
      get().toast({ kind: "crit", title: `${action} failed`, body: (e as ApiError).message });
    } finally {
      set((s) => ({ busy: { ...s.busy, [action]: false } }));
    }
  },
  setSpeed: async (speed) => {
    const sim = get().sim;
    if (!sim) return;
    try {
      const r = await api.post<SimSummary>(`/api/simulations/${sim.id}/speed`, { speed });
      set((s) => ({ sim: { ...s.sim!, ...r } }));
    } catch (e) {
      get().toast({ kind: "crit", title: "Speed change failed", body: (e as Error).message });
    }
  },
  inject: async (type, params, label) => {
    const sim = get().sim;
    if (!sim) return false;
    set((s) => ({ busy: { ...s.busy, [type]: true } }));
    try {
      const before = get().frame;
      const r = await api.post<any>(`/api/simulations/${sim.id}/events`, { type, params });
      set({ frame: r.frame });
      if (FAILURES.has(type) && before) {
        const effects = r.event.effects as string[];
        const named = new Set(effects.join(" ").match(/I-\d{3}/g) ?? []);
        const after = Object.fromEntries((r.frame.incidents as any[]).map((i) => [i.id, i.assigned as string[]]));
        const affected = before.incidents
          .filter((i) => named.has(i.id) || (i.assigned.length > 0 && i.assigned.some((u) => !(after[i.id] ?? []).includes(u))))
          .map((i) => ({ incident: i.id, before: i.assigned }));
        set({ disruption: { id: disruptionSeq++, label: label ?? type.replace(/_/g, " ").toLowerCase(), tick: r.frame.tick, effects, affected } });
      }
      // failures get the "what just happened" card instead of a long toast
      get().toast({ kind: FAILURES.has(type) ? "warn" : "info", title: label ?? type.replace(/_/g, " ").toLowerCase(), body: FAILURES.has(type) ? undefined : (r.event.effects as string[]).join(" · ") });
      return true;
    } catch (e) {
      get().toast({ kind: "crit", title: "Rejected by engine", body: (e as Error).message });
      return false;
    } finally {
      set((s) => ({ busy: { ...s.busy, [type]: false } }));
    }
  },
  applySocket: (msg) => {
    const st = get();
    if (!st.sim || msg.sim_id !== st.sim.id) return;
    if (msg.type === "error") return;
    const full = !!msg.full;
    set((s) => {
      const merge = <T extends { id: string }>(prev: T[], next: T[] = [], cap: number) => {
        const seen = new Set(prev.map((x) => x.id));
        return [...prev, ...next.filter((x) => !seen.has(x.id))].slice(-cap);
      };
      const audit = full ? msg.audit : msg.type === "reset" ? [] : merge(s.audit, msg.audit, 800);
      const rounds = full ? msg.rounds : msg.type === "reset" ? [] : merge(s.rounds, msg.rounds, 300);
      return {
        frame: msg.frame ?? s.frame,
        sim: { ...s.sim!, status: msg.status, speed: msg.speed, tick: msg.frame?.tick ?? s.sim!.tick, version: msg.state_version, ...(msg.summary ?? {}) },
        audit,
        rounds,
        lastSeq: msg.seq ?? s.lastSeq,
      };
    });
  },
  setConn: (conn) => set({ conn }),
}));
