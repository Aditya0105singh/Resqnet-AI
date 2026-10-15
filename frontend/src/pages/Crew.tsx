import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AlertOctagon, CheckCircle2, Circle, CloudOff, Navigation, RefreshCw, Ship, Truck, Wifi } from "lucide-react";
import { api } from "../lib/api";
import { useSim } from "../store/sim";
import { Badge, Button, cx, Panel, Segmented } from "../components/ui";

type Edge = { id: string; name: string; kind: string; from: string; to: string; ok: boolean; closed_reason: string };
type View = {
  tick: number;
  unit: { id: string; name: string; kind: string; status: string; node: string; next_node: string | null; load: number; capacity: number; crew_driven: boolean; comms: string };
  mission: null | {
    assignment: string;
    status: string;
    step: string;
    incident: { id: string; node: string; urgency: number; people_expected: number; people_waiting: number; status: string; neighbourhood: string; messages: { source: string; text: string; lang: string; tick: number }[] };
    shelter: { id: string; name: string; node: string; free: number };
    eta_pickup: number;
    eta_dropoff: number;
    heading_to: string;
    at_target: boolean;
    route: { nodes: { id: string; x: number; y: number }[]; edges: Edge[]; blocked: Edge[] };
    ack_deadline: number | null;
  };
  allowed_actions: string[];
  recent: { tick: number; message: string; severity: string }[];
};
type Outbox = { uuid: string; action: string; params: Record<string, unknown>; client_tick: number; label: string };
type SyncResult = { label: string; outcome: "applied" | "duplicate" | "rejected"; detail: string; at: number };

const STEPS: [string, string][] = [
  ["awaiting_ack", "Accept"],
  ["acked", "Depart"],
  ["en_route", "To scene"],
  ["on_scene", "On scene"],
  ["boarded", "Boarded"],
  ["en_route_shelter", "To shelter"],
  ["at_shelter", "Hand-over"],
];

const uuid = () => (typeof globalThis.crypto?.randomUUID === "function" ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`);

function load<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(key);
    return v ? (JSON.parse(v) as T) : fallback;
  } catch {
    return fallback;
  }
}
function save(key: string, v: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(v));
  } catch {
    /* storage unavailable: the outbox lives in memory only */
  }
}

function RouteMap({ m, unitNode }: { m: NonNullable<View["mission"]>; unitNode: string }) {
  const pts = m.route.nodes;
  if (pts.length < 2) return <div className="p-4 text-[13px] text-mute">At {unitNode}: no route left on this leg.</div>;
  const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const pad = 0.4, w = Math.max(1, x1 - x0) + 2 * pad, h = Math.max(1, y1 - y0) + 2 * pad;
  const by = Object.fromEntries(pts.map((p) => [p.id, p]));
  return (
    <svg viewBox={`${x0 - pad} ${y0 - pad} ${w} ${h}`} className="h-56 w-full rounded-lg bg-[#f4f8fb]" role="img" aria-label="Route to target">
      {m.route.edges.map((e) => (
        <line key={e.id} x1={by[e.from].x} y1={by[e.from].y} x2={by[e.to].x} y2={by[e.to].y} stroke={e.ok ? "#0891b2" : "#dc2626"} strokeWidth={e.ok ? 0.08 : 0.12} strokeDasharray={e.ok ? undefined : "0.15 0.1"} strokeLinecap="round" />
      ))}
      <circle cx={pts[0].x} cy={pts[0].y} r={0.14} fill="#0a0a0a" />
      <circle cx={pts[pts.length - 1].x} cy={pts[pts.length - 1].y} r={0.16} fill={m.step.includes("shelter") ? "#15803d" : "#d97706"} />
    </svg>
  );
}

function UnitPicker() {
  const frame = useSim((s) => s.frame);
  return (
    <div className="mx-auto max-w-md space-y-3 p-3">
      <Panel title="rescue crew app" sub="Pick the unit you are crewing. The app is built for a phone.">
        <div className="grid grid-cols-2 gap-2 p-3">
          {(frame?.resources ?? []).map((r) => (
            <Link key={r.id} to={`/crew/${r.id}`} className="flex items-center gap-2 rounded-lg border border-line-2 bg-white px-3 py-2.5 hover:border-ink">
              {r.kind === "boat" ? <Ship className="size-4" /> : <Truck className="size-4" />}
              <div className="min-w-0">
                <div className="text-[13.5px] font-medium">{r.id}</div>
                <div className="truncate text-[11px] text-mute">{r.status.toLowerCase().replace(/_/g, " ")}</div>
              </div>
            </Link>
          ))}
        </div>
      </Panel>
    </div>
  );
}

export default function Crew() {
  const { unitId } = useParams();
  if (!unitId) return <UnitPicker />;
  return <CrewApp unitId={unitId.toUpperCase()} />;
}

function CrewApp({ unitId }: { unitId: string }) {
  const sim = useSim((s) => s.sim);
  const nav = useNavigate();
  const key = `resqnet.crew.${sim?.id}.${unitId}`;
  const [view, setView] = useState<View | null>(null);
  const [tab, setTab] = useState<"mission" | "route" | "escalate">("mission");
  const [noSignal, setNoSignal] = useState(false);
  const [outbox, setOutbox] = useState<Outbox[]>([]);
  const [log, setLog] = useState<SyncResult[]>([]);
  const [count, setCount] = useState("");
  const [reason, setReason] = useState("engine trouble");
  const [syncing, setSyncing] = useState(false);
  const online = !noSignal && (typeof navigator === "undefined" || navigator.onLine !== false);

  useEffect(() => {
    setOutbox(load<Outbox[]>(`${key}.outbox`, []));
    setView(load<View | null>(`${key}.view`, null));
  }, [key]);
  useEffect(() => save(`${key}.outbox`, outbox), [key, outbox]);

  const refresh = useCallback(async () => {
    if (!sim || !online) return;
    try {
      const v = await api.get<View>(`/api/simulations/${sim.id}/crew/${unitId}`);
      setView(v);
      save(`${key}.view`, v);
    } catch {
      /* keep the cached view */
    }
  }, [sim?.id, unitId, online, key]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 1500);
    return () => clearInterval(t);
  }, [refresh]);

  const flush = useCallback(async () => {
    if (!sim || !online || syncing) return;
    const items = load<Outbox[]>(`${key}.outbox`, outbox);
    if (!items.length) return;
    setSyncing(true);
    const results: SyncResult[] = [];
    let rest = [...items];
    for (const it of items) {
      try {
        const r = await api.post<{ event: { effects: string[] } }>(`/api/simulations/${sim.id}/events`, { type: "CREW_UPDATE", params: { ...it.params, action: it.action, event_uuid: it.uuid, client_tick: it.client_tick } });
        const eff = r?.event?.effects?.[0] ?? "";
        results.push({ label: it.label, outcome: eff.startsWith("duplicate") ? "duplicate" : "applied", detail: eff, at: Date.now() });
        rest = rest.filter((x) => x.uuid !== it.uuid);
      } catch (e) {
        const msg = (e as Error).message;
        if (msg.includes("unreachable")) break; // still offline: keep the rest queued, in order
        results.push({ label: it.label, outcome: "rejected", detail: msg, at: Date.now() });
        rest = rest.filter((x) => x.uuid !== it.uuid);
      }
    }
    setOutbox(rest);
    save(`${key}.outbox`, rest);
    setLog((l) => [...results.reverse(), ...l].slice(0, 12));
    setSyncing(false);
    refresh();
  }, [sim?.id, online, syncing, key, outbox, refresh]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (online && outbox.length) flush();
  }, [online, outbox.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const act = (action: string, label: string, extra: Record<string, unknown> = {}) => {
    if (!view?.mission) return;
    const item: Outbox = { uuid: uuid(), action, label, client_tick: view.tick, params: { resource_id: unitId, assignment_id: view.mission.assignment, ...extra } };
    setOutbox((o) => [...o, item]);
  };
  const setMode = async (on: boolean) => {
    if (!sim) return;
    await api.post(`/api/simulations/${sim.id}/events`, { type: "CREW_MODE", params: { resource_id: unitId, on } }).catch(() => undefined);
    refresh();
  };

  const m = view?.mission;
  const stepIdx = m ? STEPS.findIndex(([k]) => k === m.step) : -1;
  const queued = useMemo(() => new Set(outbox.map((o) => o.action)), [outbox]);
  const can = (a: string) => !!view?.allowed_actions.includes(a) && !queued.has(a);

  if (!sim) return null;
  return (
    <div className="mx-auto max-w-md space-y-3 p-3">
      <div className={cx("flex items-center gap-2 rounded-xl px-3 py-2 text-[12.5px]", online ? "bg-ok-soft text-ok" : "bg-warn-soft text-warn")}>
        {online ? <Wifi className="size-4" /> : <CloudOff className="size-4" />}
        <span className="flex-1">{online ? "Connected" : `No signal: ${outbox.length} update(s) queued on this phone`}</span>
        <label className="flex items-center gap-1.5 text-[11.5px] text-ink">
          <input type="checkbox" checked={noSignal} onChange={(e) => setNoSignal(e.target.checked)} /> simulate no signal
        </label>
      </div>

      <Panel
        title={
          <span className="flex items-center gap-2 normal-case tracking-normal">
            {view?.unit.kind === "boat" ? <Ship className="size-4" /> : <Truck className="size-4" />}
            <span className="text-[15px] font-semibold text-ink">
              {unitId} {view?.unit.name ? `· ${view.unit.name}` : ""}
            </span>
          </span>
        }
        right={
          <button className="text-[11.5px] text-mute underline" onClick={() => nav("/crew")}>
            switch unit
          </button>
        }
      >
        <div className="flex flex-wrap items-center gap-2 px-4 py-3 text-[12.5px]">
          <Badge tone={view?.mission && view.unit.crew_driven && !["en_route", "en_route_shelter"].includes(view.mission.step) ? "warn" : "neutral"}>
            {view?.mission && view.unit.crew_driven && !["en_route", "en_route_shelter"].includes(view.mission.step) ? "holding for crew" : (view?.unit.status ?? "…").toLowerCase().replace(/_/g, " ")}
          </Badge>
          <span className="mono">
            {view?.unit.load ?? 0}/{view?.unit.capacity ?? "?"} aboard · at {view?.unit.node}
          </span>
          {view && !online && <span className="mono text-warn">last update t={view.tick}</span>}
          <span className="ml-auto">
            {view?.unit.crew_driven ? (
              <Button size="sm" variant="ghost" onClick={() => setMode(false)} disabled={!online}>
                Hand back to automatic
              </Button>
            ) : (
              <Button size="sm" variant="solid" onClick={() => setMode(true)} disabled={!online}>
                Take crew control
              </Button>
            )}
          </span>
        </div>
        {view && !view.unit.crew_driven && <p className="px-4 pb-3 text-[12px] text-mute">This unit runs automatically. Take crew control to accept, depart, board and hand over from this phone; each step then waits for you.</p>}
      </Panel>

      {!m ? (
        <Panel title="mission">
          <div className="p-4 text-[13.5px] text-mute">No mission assigned. Stay available; new missions appear here.</div>
        </Panel>
      ) : (
        <>
          <Segmented value={tab} onChange={setTab} options={[{ value: "mission", label: "Mission" }, { value: "route", label: m.route.blocked.length ? `Route · ${m.route.blocked.length} blocked` : "Route" }, { value: "escalate", label: "Escalate" }]} />
          {tab === "mission" && (
            <Panel title={`mission ${m.assignment}`} sub={`to ${m.incident.id} then ${m.shelter.name}`}>
              <ol className="grid grid-cols-4 gap-1 px-4 pt-3 text-[11px] sm:grid-cols-7">
                {STEPS.map(([k, l], i) => (
                  <li key={k} className="flex items-center gap-1">
                    {i < stepIdx ? <CheckCircle2 className="size-3.5 text-ok" /> : i === stepIdx ? <Navigation className="size-3.5 text-info" /> : <Circle className="size-3.5 text-faint" />}
                    <span className={i === stepIdx ? "font-medium" : "text-mute"}>{l}</span>
                  </li>
                ))}
              </ol>
              <div className="space-y-2 p-4">
                <div className="rounded-lg border border-line bg-white p-3">
                  <div className="flex items-center justify-between">
                    <div className="text-[14px] font-semibold">
                      {m.incident.id} · {m.incident.neighbourhood}
                    </div>
                    <Badge tone={m.incident.urgency >= 5 ? "crit" : m.incident.urgency >= 4 ? "warn" : "info"}>urgency {m.incident.urgency}</Badge>
                  </div>
                  <div className="mono mt-1 text-[12px] text-mute">
                    node {m.incident.node} · expect {m.incident.people_expected} · {m.incident.people_waiting} waiting · pickup ETA t={m.eta_pickup}
                  </div>
                  {m.incident.messages.map((x, i) => (
                    <blockquote key={i} className="mt-2 border-l-2 border-line-2 pl-2 text-[12.5px] leading-relaxed">
                      {x.text}
                      <span className="mono ml-1 text-[10.5px] text-mute">
                        {x.source} t={x.tick}
                      </span>
                    </blockquote>
                  ))}
                </div>
                <div className="mono text-[12px] text-mute">
                  shelter {m.shelter.id} {m.shelter.name} · {m.shelter.free} free · drop-off ETA t={m.eta_dropoff}
                </div>
                {m.ack_deadline !== null && <div className="rounded-md bg-warn-soft px-3 py-2 text-[12.5px] text-warn">Accept by t={m.ack_deadline} or the mission goes to another unit.</div>}
                <div className="space-y-2 pt-1">
                  {can("ACK") && (
                    <Button variant="solid" className="h-12 w-full justify-center text-[15px]" onClick={() => act("ACK", "Accept mission")}>
                      Accept mission
                    </Button>
                  )}
                  {can("DEPART") && (
                    <Button variant="solid" className="h-12 w-full justify-center text-[15px]" onClick={() => act("DEPART", m.step === "boarded" ? "Depart to shelter" : "Depart")}>
                      {m.step === "boarded" ? `Depart to ${m.shelter.id}` : "Depart"}
                    </Button>
                  )}
                  {["en_route", "en_route_shelter"].includes(m.step) && (
                    <Button variant="solid" className="h-12 w-full justify-center text-[15px]" disabled={!can("ARRIVED")} onClick={() => act("ARRIVED", "Arrived")}>
                      {m.at_target ? "Arrived" : `On the way to ${m.heading_to}…`}
                    </Button>
                  )}
                  {can("BOARDED") && (
                    <div className="flex gap-2">
                      <input aria-label="People on board" type="number" min={0} max={view?.unit.capacity} className="h-12 w-24 rounded-lg border border-line-2 px-3 text-[15px]" placeholder={String(Math.min(m.incident.people_waiting, view?.unit.capacity ?? 0))} value={count} onChange={(e) => setCount(e.target.value)} />
                      <Button variant="solid" className="h-12 flex-1 justify-center text-[15px]" onClick={() => {
                        const n = count === "" ? Math.min(m.incident.people_waiting, view?.unit.capacity ?? 0) : Number(count);
                        act("BOARDED", `${n} on board`, { count: n });
                        setCount("");
                      }}>
                        Confirm on board
                      </Button>
                    </div>
                  )}
                  {can("COMPLETE") && (
                    <Button variant="solid" className="h-12 w-full justify-center text-[15px]" onClick={() => act("COMPLETE", "Hand-over complete")}>
                      Hand-over complete
                    </Button>
                  )}
                  {view && !view.unit.crew_driven && <p className="text-[12px] text-mute">Automatic unit: buttons appear once you take crew control.</p>}
                </div>
              </div>
            </Panel>
          )}
          {tab === "route" && (
            <Panel title="route" sub={`heading to ${m.heading_to}${m.route.blocked.length ? " · red segments are blocked" : ""}`}>
              <div className="space-y-2 p-3">
                <RouteMap m={m} unitNode={view!.unit.node} />
                <ul className="space-y-1 text-[12.5px]">
                  {m.route.edges.map((e) => (
                    <li key={e.id} className={cx("mono flex justify-between gap-2", !e.ok && "text-crit")}>
                      <span>
                        {e.from} → {e.to} {e.name ? `(${e.name})` : ""} {e.kind}
                      </span>
                      <span>{e.ok ? "open" : e.closed_reason || "impassable"}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </Panel>
          )}
          {tab === "escalate" && (
            <Panel title="escalate" sub="Tell dispatch you cannot proceed safely. Each report changes the plan for everyone.">
              <div className="space-y-3 p-4">
                <Button className="h-11 w-full justify-center" disabled={!can("UNSAFE_LANDING")} onClick={() => act("UNSAFE_LANDING", "Unsafe segment ahead", { reason: "unsafe landing / debris" })}>
                  Next segment is unsafe
                </Button>
                <div className="flex gap-2">
                  <select aria-label="Reason" className="h-11 flex-1 rounded-lg border border-line-2 bg-white px-2 text-[13px]" value={reason} onChange={(e) => setReason(e.target.value)}>
                    {["engine trouble", "crew injured", "fuel low", "vessel damaged"].map((r) => (
                      <option key={r}>{r}</option>
                    ))}
                  </select>
                  <Button variant="danger" className="h-11" icon={<AlertOctagon className="size-4" />} disabled={!can("CANNOT_CONTINUE")} onClick={() => window.confirm(`Abort mission ${m.assignment}: ${reason}? Passengers on board will be handed to another unit.`) && act("CANNOT_CONTINUE", `Cannot continue: ${reason}`, { reason })}>
                    Cannot continue
                  </Button>
                </div>
              </div>
            </Panel>
          )}
        </>
      )}

      {(outbox.length > 0 || log.length > 0) && (
        <Panel title="updates" right={online && outbox.length > 0 ? <Button size="sm" icon={<RefreshCw className="size-3.5" />} loading={syncing} onClick={flush}>Sync now</Button> : undefined}>
          <ul className="space-y-1 p-3 text-[12.5px]">
            {outbox.map((o) => (
              <li key={o.uuid} className="flex items-center gap-2">
                <Badge tone="warn">queued</Badge>
                {o.label} <span className="mono text-[10.5px] text-mute">t={o.client_tick}</span>
              </li>
            ))}
            {log.map((r, i) => (
              <li key={i} className="flex items-start gap-2">
                <Badge tone={r.outcome === "applied" ? "ok" : r.outcome === "duplicate" ? "neutral" : "crit"}>{r.outcome}</Badge>
                <span>
                  {r.label}
                  {r.outcome !== "applied" && <span className="block text-[11.5px] text-mute">{r.detail}</span>}
                </span>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}
