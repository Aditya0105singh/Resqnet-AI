import { useEffect, useState } from "react";
import { MousePointerClick } from "lucide-react";
import { api } from "../lib/api";
import { useSim } from "../store/sim";
import type { Decision } from "../types";
import { fmt, INCIDENT_TONE, statusLabel, UNIT_TONE, URGENCY_TONE } from "../lib/format";
import { Badge, Button, Empty, inputCls, KV, Meter } from "./ui";

/** Detail + actions for whatever is selected on the map. All actions are engine events. */
export function SelectionPanel() {
  const sel = useSim((s) => s.selection);
  const frame = useSim((s) => s.frame);
  const world = useSim((s) => s.world);
  const inject = useSim((s) => s.inject);
  const sim = useSim((s) => s.sim);
  const openDecision = useSim((s) => s.openDecision);
  const [decs, setDecs] = useState<Decision[]>([]);
  const [cap, setCap] = useState("");

  const key = sel ? `${sel.type}:${sel.id}` : "";
  useEffect(() => {
    setDecs([]);
    if (!sel || !sim || (sel.type !== "incident" && sel.type !== "resource")) return;
    const q = sel.type === "incident" ? `incident=${sel.id}` : `resource=${sel.id}`;
    api
      .get<{ decisions: Decision[] }>(`/api/simulations/${sim.id}/decisions?${q}&limit=8`)
      .then((r) => setDecs(r.decisions))
      .catch(() => setDecs([]));
    // refresh when the selection or the number of rounds changes
  }, [key, sim?.id, frame?.round_count]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!sel || !frame || !world) return <Empty icon={<MousePointerClick className="size-5" />} title="Select something on the map" body="Click an incident, unit, shelter or road to inspect it and act on it." />;

  if (sel.type === "incident") {
    const i = frame.incidents.find((x) => x.id === sel.id);
    if (!i) return <Empty title="Incident not found" />;
    const open = i.status !== "RESCUED" && i.status !== "FALSE_ALARM";
    return (
      <div className="space-y-3 p-4">
        <div className="flex items-center justify-between">
          <div className="font-display text-lg font-semibold">{i.id}</div>
          <div className="flex gap-1">
            <Badge tone={URGENCY_TONE(i.urgency)}>urgency {i.urgency}</Badge>
            <Badge tone={INCIDENT_TONE[i.status]}>{statusLabel(i.status)}</Badge>
          </div>
        </div>
        <div>
          <KV k="Location" v={`${i.node} · ${world.neighbourhoods.find((n) => n.id === i.neighbourhood)?.name}`} />
          <KV k="Waiting / uncovered" v={`${i.people} / ${i.unassigned}`} />
          <KV k="Rescued" v={i.rescued} />
          <KV k="Confidence" v={`${fmt(i.confidence, 2)}${i.provisional ? " · provisional" : ""}`} />
          <KV k="Reported → deadline" v={`t=${i.reported_tick} → t=${i.deadline}`} />
          <KV k="First pickup" v={i.first_pickup_tick ?? "—"} />
          <KV k="Assigned units" v={i.assigned.join(", ") || "—"} />
          <KV k="Reports" v={i.reports.length} />
          {i.evidence && (
            <>
              <KV k="Evidence for" v={`${fmt(i.evidence.cp, 2)} · ${i.evidence.present_sources} independent of ${i.evidence.present_reports} report(s)`} />
              <KV k="Evidence against" v={i.evidence.negative_reports ? `${fmt(i.evidence.cn, 2)} · ${i.evidence.negative_sources} independent of ${i.evidence.negative_reports}` : "none"} />
              {i.evidence.forwarded_copies > 0 && <KV k="Forwarded copies" v={`${i.evidence.forwarded_copies} (counted once)`} />}
              {i.verdict && <KV k="Dispatcher verdict" v={i.verdict} />}
            </>
          )}
        </div>
        {i.status === "DISPUTED" && (
          <div className="rounded-lg border border-crit/30 bg-crit/[0.04] p-3">
            <div className="text-[13px] font-medium">{i.verdict === "verify" ? "Verification visit ordered" : "Credible reports conflict: dispatcher decision needed"}</div>
            <p className="mt-1 text-[12px] leading-relaxed text-mute">
              {i.verdict === "verify"
                ? "One unit is being dispatched to check on scene. You can still confirm or dismiss if new information arrives."
                : `The system does not pick a side automatically. Without a decision, one unit is sent at t=${i.review_due} to verify on scene.`}
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Button size="sm" variant="solid" onClick={() => inject("RESOLVE_DISPUTE", { incident_id: i.id, decision: "confirm" }, `${i.id} confirmed`)}>
                Confirm victims
              </Button>
              {i.verdict !== "verify" && (
                <Button size="sm" variant="info" onClick={() => inject("RESOLVE_DISPUTE", { incident_id: i.id, decision: "verify" }, `${i.id}: verify now`)}>
                  Verify now
                </Button>
              )}
              <Button size="sm" variant="danger" onClick={() => inject("RESOLVE_DISPUTE", { incident_id: i.id, decision: "dismiss" }, `${i.id} dismissed`)}>
                Dismiss as false alarm
              </Button>
            </div>
          </div>
        )}
        {open && i.unassigned > 0 && (
          <Button size="sm" variant="info" onClick={() => inject("PROPOSE_ACTION", { action: "MANUAL_ASSIGN", params: { incident_id: i.id, resource_id: "auto" }, source: "recommender" }, `Suggestion for ${i.id} sent to Approvals`)}>
            Suggest unit (needs approval)
          </Button>
        )}
        {open && (
          <div className="flex flex-wrap gap-1.5">
            <Button size="sm" variant="danger" onClick={() => inject("CONTRADICTORY_REPORT", { incident_id: i.id, claim: "NO_VICTIMS", source: "responder" }, `Responder: no victims at ${i.id}`)}>
              Responder: no victims
            </Button>
            <Button size="sm" onClick={() => inject("CONTRADICTORY_REPORT", { incident_id: i.id, claim: "NO_VICTIMS", source: "resident" }, `Resident: no victims at ${i.id}`)}>
              Resident: no victims
            </Button>
            <Button size="sm" variant="info" onClick={() => inject("CONTRADICTORY_REPORT", { incident_id: i.id, claim: "PRESENT", source: "sensor", people: i.people + 3 }, `Sensor: +3 people at ${i.id}`)}>
              Sensor: +3 people
            </Button>
          </div>
        )}
        <DecisionList decs={decs} onOpen={openDecision} />
      </div>
    );
  }

  if (sel.type === "resource") {
    const r = frame.resources.find((x) => x.id === sel.id);
    if (!r) return <Empty title="Unit not found" />;
    const a = frame.assignments.find((x) => x.id === r.assignment_id);
    return (
      <div className="space-y-3 p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-display text-lg font-semibold">{r.id}</div>
            <div className="text-xs text-mute">
              {r.name} · {r.kind} · {r.speed_kmh} km/h
            </div>
          </div>
          <Badge tone={UNIT_TONE[r.status]}>{statusLabel(r.status)}</Badge>
        </div>
        <div>
          <div className="mb-1 flex justify-between text-xs text-mute">
            <span>Load</span>
            <span className="mono">
              {r.load}/{r.capacity}
            </span>
          </div>
          <Meter value={r.load} max={r.capacity} tone="ok" />
        </div>
        <div>
          <KV k="Position" v={r.next_node ? `${r.node} → ${r.next_node}` : r.node} />
          <KV k="Mission" v={a ? `${a.id}: ${a.incident_id} → ${a.shelter_id}` : "—"} />
          <KV k="ETA" v={r.eta !== null ? `t=${r.eta}` : "—"} />
          <KV k="Route remaining" v={`${r.route.length} nodes`} />
          <KV k="Distance driven" v={`${r.distance_km} km`} />
          <KV k="Busy / idle ticks" v={`${r.busy_ticks} / ${r.idle_ticks}`} />
          {r.blackout_until !== null && <KV k="Comms" v={<span className="text-warn">down until t={r.blackout_until}</span>} />}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {r.status === "DISABLED" ? (
            <Button size="sm" variant="info" onClick={() => inject("RESOURCE_RESTORE", { resource_id: r.id }, `${r.id} restored`)}>
              Restore unit
            </Button>
          ) : (
            <Button size="sm" variant="danger" onClick={() => inject("RESOURCE_FAILURE", { resource_id: r.id, reason: "operator: breakdown" }, `${r.id} disabled`)}>
              Mark unavailable
            </Button>
          )}
          {a?.status === "COMMITTED" && (
            <Button size="sm" onClick={() => inject("REQUEST_REASSIGN", { resource_id: r.id }, `${r.id} released for reassignment`)}>
              Request reassignment
            </Button>
          )}
          {r.status !== "DISABLED" && r.blackout_until === null && (
            <Button size="sm" onClick={() => inject("COMM_BLACKOUT", { resource_id: r.id, duration: 15 }, `${r.id} comms blackout`)}>
              Comms blackout 15′
            </Button>
          )}
        </div>
        <DecisionList decs={decs} onOpen={openDecision} />
      </div>
    );
  }

  if (sel.type === "shelter") {
    const s = frame.shelters.find((x) => x.id === sel.id);
    if (!s) return <Empty title="Shelter not found" />;
    const res = frame.reservations.filter((x) => x.shelter_id === s.id);
    return (
      <div className="space-y-3 p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-display text-lg font-semibold">{s.id}</div>
            <div className="text-xs text-mute">{s.name}</div>
          </div>
          <Badge tone={s.free <= 0 ? "crit" : s.free < 8 ? "warn" : "ok"}>{s.free} free</Badge>
        </div>
        <Meter value={s.occupancy} reserved={s.reserved} max={s.capacity} tone={s.free <= 0 ? "crit" : "ink"} />
        <div>
          <KV k="Occupancy" v={`${s.occupancy}/${s.capacity}`} />
          <KV k="Reserved (inbound)" v={s.reserved} />
          <KV k="Version" v={`v${s.version}`} />
        </div>
        <div className="flex items-end gap-1.5">
          <input className={inputCls} type="number" min={0} max={1000} placeholder="New capacity" value={cap} onChange={(e) => setCap(e.target.value)} />
          <Button size="sm" disabled={cap === ""} onClick={() => inject("SHELTER_CAPACITY", { shelter_id: s.id, capacity: Number(cap), reason: "operator" }, `${s.id} capacity → ${cap}`).then(() => setCap(""))}>
            Set
          </Button>
          <Button size="sm" variant="danger" onClick={() => inject("SHELTER_CAPACITY", { shelter_id: s.id, capacity: "occupancy", reason: "overflow" }, `${s.id} overflow`)}>
            Overflow
          </Button>
        </div>
        <div>
          <div className="label mb-1">active reservations</div>
          {res.length === 0 ? (
            <div className="text-xs text-mute">None</div>
          ) : (
            res.map((x) => (
              <div key={x.id} className="mono flex justify-between text-[11.5px] text-ink-2">
                <span>{x.id}</span>
                <span>
                  {x.resource_id}→{x.incident_id} · {x.people} seats · exp t={x.expires}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    );
  }

  const e = world.edges.find((x) => x.id === sel.id);
  const st = frame.edges[sel.id];
  if (!e || !st) return <Empty title="Road not found" />;
  return (
    <div className="space-y-3 p-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="font-display text-lg font-semibold">{e.name || e.id}</div>
          <div className="text-xs text-mute">
            {e.kind} · {e.u} ↔ {e.v} · {e.length_km} km
          </div>
        </div>
        <Badge tone={st[2] ? "crit" : st[0] ? "ok" : "warn"}>{st[2] ? "closed" : st[0] ? "open" : "flooded"}</Badge>
      </div>
      <div>
        <KV k="Ground passable" v={st[0] ? "yes" : "no"} />
        <KV k="Boat navigable" v={st[1] ? "yes" : "no"} />
        <KV k="Flood depth" v={`${st[3]} m`} />
        <KV k="Route risk" v={st[4]} />
        {e.clearance && <KV k="Bridge clearance" v={`${e.clearance} m (river ${frame.river_level} m)`} />}
      </div>
      {st[2] ? (
        <Button size="sm" variant="info" onClick={() => inject("OPEN_EDGE", { edge_id: e.id }, `${e.name || e.id} reopened`)}>
          Reopen
        </Button>
      ) : (
        <Button size="sm" variant="danger" onClick={() => inject("CLOSE_EDGE", { edge_id: e.id, reason: "operator closure" }, `${e.name || e.id} closed`)}>
          Close {e.kind}
        </Button>
      )}
    </div>
  );
}

function DecisionList({ decs, onOpen }: { decs: Decision[]; onOpen: (id: string) => void }) {
  if (!decs.length) return null;
  return (
    <div>
      <div className="label mb-1">decision records</div>
      <div className="space-y-1">
        {decs.map((d) => (
          <button key={d.id} onClick={() => onOpen(d.id)} className="flex w-full items-center gap-2 rounded-lg border border-line px-2 py-1.5 text-left text-xs hover:border-info">
            <span className="mono text-mute">t={d.tick}</span>
            <span className="mono">{d.incident_id}</span>
            <Badge tone={d.outcome === "COMMITTED" ? "ok" : d.outcome === "UNMATCHED" ? "neutral" : "crit"}>{d.outcome.replace("_", " ").toLowerCase()}</Badge>
            <span className="ml-auto truncate text-mute">{d.selected?.resource_id ?? ""}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
