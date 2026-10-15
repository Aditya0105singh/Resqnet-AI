import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Rocket, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import { useSim } from "../store/sim";
import { ChaosItems } from "../components/Chaos";
import { SimControls } from "../components/Shell";
import { Badge, Button, cx, Empty, Field, inputCls, PageHeader, Panel, Segmented } from "../components/ui";
import type { ScenarioConfig, Strategy } from "../types";
import { STRATEGY_LABEL } from "../lib/format";

const NB = [
  ["NB", "Northbank"],
  ["HC", "Hillcrest"],
  ["OQ", "Old Quarter"],
  ["RS", "Riverside"],
  ["EM", "Eastmere"],
];
const SCHED_TYPES = ["TRIPLE_FAILURE", "CLOSE_EDGE", "RESOURCE_FAILURE", "SHELTER_CAPACITY", "FLOOD_SURGE", "COMM_BLACKOUT"];

export default function Scenarios() {
  const { sim, frame, createSim, inject } = useSim();
  const nav = useNavigate();
  const [presets, setPresets] = useState<ScenarioConfig[]>([]);
  const [base, setBase] = useState("triple_failure");
  const [cfg, setCfg] = useState<ScenarioConfig | null>(null);
  const [strategy, setStrategy] = useState<Strategy>("decentralized");
  const [launching, setLaunching] = useState(false);
  const [disruptions, setDisruptions] = useState<any[]>([]);
  const [manual, setManual] = useState({ type: "CLOSE_EDGE", target: "BR1" });

  useEffect(() => {
    api.get<{ scenarios: ScenarioConfig[] }>("/api/scenarios").then((r) => {
      setPresets(r.scenarios);
      setCfg(structuredClone(r.scenarios.find((s) => s.key === base) ?? r.scenarios[0]));
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!sim) return;
    api.get<any>(`/api/simulations/${sim.id}/metrics`).then((r) => setDisruptions(r.disruptions)).catch(() => {});
  }, [sim?.id, frame?.last_event_id, frame?.tick]); // eslint-disable-line react-hooks/exhaustive-deps

  const pick = (k: string) => {
    setBase(k);
    const p = presets.find((s) => s.key === k);
    if (p) setCfg(structuredClone(p));
  };
  const set = <K extends keyof ScenarioConfig>(k: K, v: ScenarioConfig[K]) => setCfg((c) => (c ? { ...c, [k]: v } : c));

  const launch = async () => {
    if (!cfg) return;
    setLaunching(true);
    // weights are derived server-side from the chosen policy
    const { key, name, description, weights, ...rest } = cfg;
    void key;
    void description;
    void weights;
    try {
      await createSim(base, strategy, { ...rest, name });
      nav("/command");
    } catch {
      /* toast already shown */
    } finally {
      setLaunching(false);
    }
  };

  const targets: Record<string, string[]> = {
    CLOSE_EDGE: ["BR1", "BR2", "BR3"],
    OPEN_EDGE: ["BR1", "BR2", "BR3"],
    RESOURCE_FAILURE: frame?.resources.map((r) => r.id) ?? [],
    RESOURCE_RESTORE: frame?.resources.filter((r) => r.status === "DISABLED").map((r) => r.id) ?? [],
    COMM_BLACKOUT: frame?.resources.map((r) => r.id) ?? [],
    SHELTER_CAPACITY: ["S1", "S2", "S3"],
    CONTRADICTORY_REPORT: frame?.incidents.filter((i) => i.status !== "RESCUED").map((i) => i.id) ?? [],
  };
  const fireManual = () => {
    const t = manual.type;
    const p: Record<string, unknown> =
      t === "CLOSE_EDGE" || t === "OPEN_EDGE"
        ? { edge_id: manual.target, reason: "chaos lab" }
        : t === "SHELTER_CAPACITY"
          ? { shelter_id: manual.target, capacity: "occupancy", reason: "chaos lab overflow" }
          : t === "COMM_BLACKOUT"
            ? { resource_id: manual.target, duration: 20 }
            : t === "CONTRADICTORY_REPORT"
              ? { incident_id: manual.target, claim: "NO_VICTIMS", source: "resident" }
              : { resource_id: manual.target, reason: "chaos lab" };
    inject(t, p, `${t.toLowerCase().replace(/_/g, " ")} ${manual.target}`);
  };

  return (
    <div className="space-y-3 p-3">
      <SimControls />
      <PageHeader eyebrow="Labs" title="Scenario & failure lab" sub="Design your own flood, or break the current run: close bridges, crash boats, fill shelters and cut the network. Each failure is tracked until everyone affected is covered again." />
      <div className="grid gap-3 xl:grid-cols-[1fr_440px]">
        <Panel title="design a scenario" sub="Start from a preset, adjust anything, then launch a new run" right={<Segmented size="sm" value={strategy} onChange={setStrategy} options={(["decentralized", "message_passing", "centralized", "greedy"] as Strategy[]).map((s) => ({ value: s, label: STRATEGY_LABEL[s] }))} />}>
          {!cfg ? (
            <Empty title="Loading presets…" />
          ) : (
            <div className="space-y-5 p-4">
              <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-4">
                {presets.map((p) => (
                  <button key={p.key} onClick={() => pick(p.key)} className={cx("rounded-xl border p-3 text-left transition", base === p.key ? "border-ink bg-ink text-white" : "border-line bg-white hover:border-ink/30")}>
                    <div className="text-[13px] font-semibold">{p.name}</div>
                    <div className={cx("mt-1 line-clamp-3 text-[11px] leading-snug", base === p.key ? "text-white/70" : "text-mute")}>{p.description}</div>
                  </button>
                ))}
              </div>
              <div className="grid gap-x-5 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
                <Slider label="flood severity" v={cfg.flood_severity} min={0.4} max={2} step={0.05} on={(v) => set("flood_severity", v)} fmt={(v) => `${v.toFixed(2)}×`} />
                <Slider label="flood peak tick" v={cfg.flood_peak_tick} min={20} max={150} step={5} on={(v) => set("flood_peak_tick", v)} />
                <Slider label="incident arrivals" v={cfg.arrival_incidents} min={0} max={40} step={1} on={(v) => set("arrival_incidents", v)} hint={`+${cfg.initial_incidents} at t=0`} />
                <Slider label="rescue boats" v={cfg.boats} min={0} max={7} step={1} on={(v) => set("boats", v)} />
                <Slider label="ground teams" v={cfg.ground_units} min={0} max={6} step={1} on={(v) => set("ground_units", v)} />
                <Slider label="duration (min)" v={cfg.duration} min={60} max={360} step={10} on={(v) => set("duration", v)} />
                {cfg.shelter_capacity.map((c, i) => (
                  <Slider key={i} label={`shelter S${i + 1} capacity`} v={c} min={0} max={120} step={1} on={(v) => set("shelter_capacity", cfg.shelter_capacity.map((x, j) => (j === i ? v : x)))} />
                ))}
                <Slider label="report noise" v={cfg.report_noise} min={0} max={1} step={0.05} on={(v) => set("report_noise", v)} fmt={(v) => `${Math.round(v * 100)}%`} />
                <Slider label="duplicate reports" v={cfg.duplicate_rate} min={0} max={1} step={0.05} on={(v) => set("duplicate_rate", v)} fmt={(v) => `${Math.round(v * 100)}%`} />
                <Slider label="delayed reports" v={cfg.delayed_report_rate} min={0} max={1} step={0.05} on={(v) => set("delayed_report_rate", v)} fmt={(v) => `${Math.round(v * 100)}%`} />
                <Slider label="false alarms" v={cfg.false_alarm_rate} min={0} max={0.5} step={0.02} on={(v) => set("false_alarm_rate", v)} fmt={(v) => `${Math.round(v * 100)}%`} />
                <Slider label="contradictory reports" v={cfg.contradiction_rate} min={0} max={0.6} step={0.02} on={(v) => set("contradiction_rate", v)} fmt={(v) => `${Math.round(v * 100)}%`} />
                <Slider label="communication delay" v={cfg.comm_delay} min={0} max={10} step={1} on={(v) => set("comm_delay", v)} fmt={(v) => `${v} tick${v === 1 ? "" : "s"}`} />
                <Field label="seed">
                  <input className={inputCls} type="number" value={cfg.seed} onChange={(e) => set("seed", Number(e.target.value))} />
                </Field>
                <Field label="priority policy">
                  <select className={inputCls} value={cfg.policy} onChange={(e) => set("policy", e.target.value)}>
                    {["balanced", "fastest", "urgency_first", "equity"].map((p) => (
                      <option key={p}>{p}</option>
                    ))}
                  </select>
                </Field>
              </div>
              <div>
                <div className="label mb-2">neighbourhood priority weights (1.0 = neutral)</div>
                <div className="grid gap-x-5 gap-y-2 sm:grid-cols-2 lg:grid-cols-5">
                  {NB.map(([id, name]) => (
                    <Slider key={id} label={name} v={cfg.neighbourhood_priority[id] ?? 1} min={0.5} max={3} step={0.1} on={(v) => set("neighbourhood_priority", { ...cfg.neighbourhood_priority, [id]: v })} fmt={(v) => `${v.toFixed(1)}×`} />
                  ))}
                </div>
              </div>
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <div className="label">scheduled events</div>
                  <Button size="sm" icon={<Plus className="size-3.5" />} onClick={() => set("schedule", [...cfg.schedule, { tick: 30, type: "CLOSE_EDGE", params: { edge_id: "BR2", reason: "scheduled" } }])}>
                    Add event
                  </Button>
                </div>
                {cfg.schedule.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-line-2 p-3 text-xs text-mute">No scheduled events — inject them live from the console instead.</div>
                ) : (
                  <div className="space-y-1.5">
                    {cfg.schedule.map((e, i) => (
                      <div key={i} className="flex items-center gap-2">
                        <span className="label">t=</span>
                        <input className={cx(inputCls, "w-20")} type="number" value={e.tick} onChange={(ev) => set("schedule", cfg.schedule.map((x, j) => (j === i ? { ...x, tick: Number(ev.target.value) } : x)))} />
                        <select className={cx(inputCls, "w-48")} value={e.type} onChange={(ev) => set("schedule", cfg.schedule.map((x, j) => (j === i ? { ...x, type: ev.target.value, params: defaultParams(ev.target.value) } : x)))}>
                          {SCHED_TYPES.map((t) => (
                            <option key={t}>{t}</option>
                          ))}
                        </select>
                        <input className={cx(inputCls, "mono text-xs")} value={JSON.stringify(e.params)} onChange={(ev) => { try { const p = JSON.parse(ev.target.value); set("schedule", cfg.schedule.map((x, j) => (j === i ? { ...x, params: p } : x))); } catch { /* keep typing */ } }} />
                        <button aria-label="Remove" className="text-faint hover:text-crit" onClick={() => set("schedule", cfg.schedule.filter((_, j) => j !== i))}>
                          <Trash2 className="size-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div className="flex items-center justify-end gap-2 border-t border-line pt-4">
                <span className="text-xs text-mute">Synthetic, seeded and reproducible.</span>
                <Button variant="solid" icon={<Rocket className="size-4" />} loading={launching} onClick={launch}>
                  Launch scenario
                </Button>
              </div>
            </div>
          )}
        </Panel>

        <div className="space-y-3">
          <Panel title="break the live run" sub={sim ? `Affects the current run at minute ${frame?.tick}` : undefined}>
            <div className="space-y-4 p-4">
              <div className="-mx-2 -mt-2">
                <ChaosItems extra />
              </div>
              <div className="rounded-xl border border-line bg-wash p-3">
                <div className="label mb-2">or pick an exact target</div>
                <div className="flex gap-1.5">
                  <select className={cx(inputCls, "flex-1")} value={manual.type} onChange={(e) => setManual({ type: e.target.value, target: targets[e.target.value]?.[0] ?? "" })}>
                    {Object.keys(targets).map((t) => (
                      <option key={t}>{t}</option>
                    ))}
                  </select>
                  <select className={cx(inputCls, "w-28")} value={manual.target} onChange={(e) => setManual({ ...manual, target: e.target.value })}>
                    {(targets[manual.type] ?? []).map((t) => (
                      <option key={t}>{t}</option>
                    ))}
                  </select>
                  <Button variant="solid" disabled={!manual.target} onClick={fireManual}>
                    Inject
                  </Button>
                </div>
              </div>
            </div>
          </Panel>
          <Panel title="failures & recovery" sub="Recovery time = minutes until everyone affected has a unit again">
            <div className="scroll-thin max-h-[420px] overflow-y-auto">
              {disruptions.length === 0 ? (
                <Empty title="No disruptions yet" body="Inject a failure; affected commitments and recovery time appear here." />
              ) : (
                <ul className="divide-y divide-line">
                  {[...disruptions].reverse().map((d) => (
                    <li key={d.event} className="px-4 py-2.5 text-xs">
                      <div className="flex items-center gap-2">
                        <span className="mono font-semibold">{d.event}</span>
                        <Badge tone="warn">{d.type.replace(/_/g, " ").toLowerCase()}</Badge>
                        <span className="mono text-mute">t={d.tick}</span>
                        <span className="ml-auto">{d.recovery === null ? <Badge tone="crit" dot>recovering</Badge> : <Badge tone="ok">recovered in {d.recovery} min</Badge>}</span>
                      </div>
                      <div className="mono mt-1 text-[11px] text-mute">
                        affected requests: {d.incidents.length ? d.incidents.join(", ") : "none"}
                        {d.holds.length ? ` · loaded units re-sheltered: ${d.holds.join(", ")}` : ""}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}

function defaultParams(t: string): Record<string, unknown> {
  switch (t) {
    case "CLOSE_EDGE":
      return { edge_id: "BR2", reason: "scheduled" };
    case "RESOURCE_FAILURE":
      return { resource_id: "B1", reason: "scheduled" };
    case "SHELTER_CAPACITY":
      return { shelter_id: "S2", capacity: "occupancy" };
    case "FLOOD_SURGE":
      return { delta: 0.5 };
    case "COMM_BLACKOUT":
      return { resource_id: "B2", duration: 20 };
    default:
      return {};
  }
}

function Slider({ label, v, min, max, step, on, fmt, hint }: { label: string; v: number; min: number; max: number; step: number; on: (v: number) => void; fmt?: (v: number) => string; hint?: string }) {
  return (
    <Field label={label} hint={(fmt ? fmt(v) : String(v)) + (hint ? ` · ${hint}` : "")}>
      <input type="range" className="w-full accent-[#0a0a0a]" min={min} max={max} step={step} value={v} onChange={(e) => on(Number(e.target.value))} />
    </Field>
  );
}
