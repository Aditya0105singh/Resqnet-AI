import { useEffect, useMemo, useState } from "react";
import { GitFork, Pause, Play } from "lucide-react";
import { api } from "../lib/api";
import { useSim } from "../store/sim";
import { CityMap } from "../components/CityMap";
import { SimControls } from "../components/Shell";
import { Badge, Button, cx, Empty, Field, inputCls, PageHeader, Panel, Segmented, Spinner } from "../components/ui";
import { fmt, STRATEGY_LABEL } from "../lib/format";

interface CF {
  fork_tick: number;
  end_tick: number;
  applied: string[];
  baseline: Record<string, any>;
  alternative: Record<string, any>;
  diverged_decisions: { incident: string; baseline: [number, string][]; alternative: [number, string][] }[];
  diverged_count: number;
  frames: { baseline: any[]; alternative: any[] };
  elapsed_ms: number;
}

const ROWS: { k: string; label: string; better: "lower" | "higher"; unit?: string; d?: number }[] = [
  { k: "people_rescued", label: "People rescued", better: "higher" },
  { k: "unmet_people", label: "People not delivered", better: "lower" },
  { k: "mean_time_to_service", label: "Mean time to service", better: "lower", unit: "min" },
  { k: "median_time_to_service", label: "Median time to service", better: "lower", unit: "min" },
  { k: "deadline_misses", label: "Urgent deadline misses", better: "lower" },
  { k: "utilisation", label: "Fleet utilisation", better: "higher", d: 2 },
  { k: "idle_with_demand_ticks", label: "Idle ticks with demand", better: "lower" },
  { k: "fairness_jain", label: "Fairness (Jain)", better: "higher", d: 3 },
  { k: "route_violations", label: "Route violations", better: "lower" },
  { k: "reassignments", label: "Reassignments", better: "lower" },
];

export default function DecisionLab() {
  const { sim, frame, world } = useSim();
  const [tick, setTick] = useState(0);
  const [mods, setMods] = useState({ extra_boats: 2, extra_ground: 0, edges: {} as Record<string, string>, shelter_delta: { S1: 0, S2: 0, S3: 0 } as Record<string, number>, policy: "", comm_delay: "", strategy: "" });
  const [res, setRes] = useState<CF | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [i, setI] = useState(0);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    if (frame && tick === 0) setTick(Math.max(0, Math.min(frame.tick, 20)));
  }, [frame?.tick]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!playing || !res) return;
    const n = Math.min(res.frames.baseline.length, res.frames.alternative.length);
    const t = setInterval(() => setI((x) => (x + 1 >= n ? (setPlaying(false), x) : x + 1)), 160);
    return () => clearInterval(t);
  }, [playing, res]);

  const run = async () => {
    if (!sim) return;
    setBusy(true);
    setErr(null);
    try {
      const body: any = { extra_boats: mods.extra_boats, extra_ground: mods.extra_ground, edges: mods.edges, shelter_delta: mods.shelter_delta };
      if (mods.policy) body.policy = mods.policy;
      if (mods.comm_delay !== "") body.comm_delay = Number(mods.comm_delay);
      if (mods.strategy) body.strategy = mods.strategy;
      const r = await api.post<CF>(`/api/simulations/${sim.id}/fork`, { tick, modifications: body });
      setRes(r);
      setI(0);
      setPlaying(true);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const n = res ? Math.min(res.frames.baseline.length, res.frames.alternative.length) : 0;
  const fb = res?.frames.baseline[Math.min(i, n - 1)];
  const fa = res?.frames.alternative[Math.min(i, n - 1)];
  const changes = useMemo(() => {
    const out: string[] = [];
    if (mods.extra_boats) out.push(`+${mods.extra_boats} boat${mods.extra_boats > 1 ? "s" : ""}`);
    if (mods.extra_ground) out.push(`+${mods.extra_ground} ground team${mods.extra_ground > 1 ? "s" : ""}`);
    Object.entries(mods.edges).forEach(([e, s]) => out.push(`${e} ${s}`));
    Object.entries(mods.shelter_delta).forEach(([s, d]) => d && out.push(`${s} ${d > 0 ? "+" : ""}${d} seats`));
    if (mods.policy) out.push(`policy ${mods.policy}`);
    if (mods.comm_delay !== "") out.push(`comm delay ${mods.comm_delay}`);
    if (mods.strategy) out.push(`strategy ${mods.strategy}`);
    return out;
  }, [mods]);

  if (!sim || !frame || !world) return <Spinner />;
  return (
    <div className="space-y-3 p-3">
      <SimControls />
      <PageHeader
        eyebrow="Labs"
        title="What if we had decided differently?"
        sub="Pick a moment in the run, change one decision, and both futures play out under exactly the same events. You see the measured difference, even when the alternative is worse."
      />
      <div className="grid gap-3 xl:grid-cols-[380px_1fr]">
        <Panel title="alternative decision" sub={`fork any tick in 0…${frame.tick}`}>
          <div className="space-y-4 p-4">
            <Field label="fork at tick" hint={`t=${tick}`}>
              <input type="range" className="w-full accent-[#0a0a0a]" min={0} max={frame.tick} value={Math.min(tick, frame.tick)} onChange={(e) => setTick(Number(e.target.value))} />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="extra boats" hint={`+${mods.extra_boats}`}>
                <input type="range" className="w-full accent-[#0a0a0a]" min={0} max={3} value={mods.extra_boats} onChange={(e) => setMods({ ...mods, extra_boats: Number(e.target.value) })} />
              </Field>
              <Field label="extra ground teams" hint={`+${mods.extra_ground}`}>
                <input type="range" className="w-full accent-[#0a0a0a]" min={0} max={3} value={mods.extra_ground} onChange={(e) => setMods({ ...mods, extra_ground: Number(e.target.value) })} />
              </Field>
            </div>
            <div>
              <div className="label mb-1.5">bridges</div>
              {["BR1", "BR2", "BR3"].map((b) => (
                <div key={b} className="mb-1 flex items-center justify-between text-sm">
                  <span>{world.edges.find((e) => e.id === b)?.name}</span>
                  <Segmented size="sm" value={mods.edges[b] ?? "as-is"} onChange={(v) => { const e = { ...mods.edges }; if (v === "as-is") delete e[b]; else e[b] = v; setMods({ ...mods, edges: e }); }} options={[{ value: "as-is", label: "as is" }, { value: "open", label: "open" }, { value: "closed", label: "closed" }]} />
                </div>
              ))}
            </div>
            <div>
              <div className="label mb-1.5">shelter capacity change</div>
              {["S1", "S2", "S3"].map((s) => (
                <Field key={s} label={s} hint={`${mods.shelter_delta[s] > 0 ? "+" : ""}${mods.shelter_delta[s]}`}>
                  <input type="range" className="w-full accent-[#0a0a0a]" min={-30} max={60} step={5} value={mods.shelter_delta[s]} onChange={(e) => setMods({ ...mods, shelter_delta: { ...mods.shelter_delta, [s]: Number(e.target.value) } })} />
                </Field>
              ))}
            </div>
            <div className="grid grid-cols-3 gap-2">
              <Field label="policy">
                <select className={inputCls} value={mods.policy} onChange={(e) => setMods({ ...mods, policy: e.target.value })}>
                  <option value="">same</option>
                  {["balanced", "fastest", "urgency_first", "equity"].map((p) => (
                    <option key={p}>{p}</option>
                  ))}
                </select>
              </Field>
              <Field label="comm delay">
                <select className={inputCls} value={mods.comm_delay} onChange={(e) => setMods({ ...mods, comm_delay: e.target.value })}>
                  <option value="">same</option>
                  {[0, 1, 2, 4, 8].map((p) => (
                    <option key={p}>{p}</option>
                  ))}
                </select>
              </Field>
              <Field label="strategy">
                <select className={inputCls} value={mods.strategy} onChange={(e) => setMods({ ...mods, strategy: e.target.value })}>
                  <option value="">same</option>
                  {["decentralized", "message_passing", "centralized", "greedy"].map((p) => (
                    <option key={p} value={p}>
                      {STRATEGY_LABEL[p]}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <div className="flex flex-wrap gap-1">
              {changes.length ? changes.map((c) => <Badge key={c} tone="info" className="normal-case">{c}</Badge>) : <span className="text-xs text-mute">No changes — the branches will be identical (a useful sanity check).</span>}
            </div>
            <Button variant="solid" className="w-full" icon={<GitFork className="size-4" />} loading={busy} onClick={run}>
              Fork at t={tick} and run both futures
            </Button>
            {err && <div className="rounded-lg bg-crit-soft p-2 text-xs text-crit">{err}</div>}
          </div>
        </Panel>

        <div className="space-y-3">
          {!res ? (
            <Panel title="results">
              <Empty icon={<GitFork className="size-6" />} title="No counterfactual yet" body="Choose a fork tick and an alternative. Both futures are simulated to the end of the scenario with the same seeds and events." />
            </Panel>
          ) : (
            <>
              <div className="grid gap-3 md:grid-cols-2">
                {(["baseline", "alternative"] as const).map((k) => (
                  <Panel key={k} title={k === "baseline" ? "baseline (as decided)" : "alternative"} sub={k === "alternative" ? res.applied.join(" · ") || "no change" : `forked at t=${res.fork_tick}`} right={<span className="mono text-[11px]">t={(k === "baseline" ? fb : fa)?.tick}</span>}>
                    <div className="h-[300px]">{(k === "baseline" ? fb : fa) && <CityMap world={world} frame={(k === "baseline" ? fb : fa)!} compact transitionMs={150} />}</div>
                    <div className="mono flex justify-between border-t border-line px-3 py-1.5 text-[11px] text-mute">
                      <span>rescued {(k === "baseline" ? fb : fa)?.metrics.people_rescued}</span>
                      <span>waiting {(k === "baseline" ? fb : fa)?.metrics.unmet_people}</span>
                      <span>misses {(k === "baseline" ? fb : fa)?.metrics.deadline_misses}</span>
                    </div>
                  </Panel>
                ))}
              </div>
              <div className="panel flex items-center gap-3 px-3 py-2">
                <Button size="sm" variant="solid" icon={playing ? <Pause className="size-3.5" /> : <Play className="size-3.5" />} onClick={() => (i >= n - 1 ? (setI(0), setPlaying(true)) : setPlaying(!playing))}>
                  {playing ? "Pause" : "Play"}
                </Button>
                <input type="range" className="flex-1 accent-[#0a0a0a]" min={0} max={n - 1} value={i} onChange={(e) => { setPlaying(false); setI(Number(e.target.value)); }} />
                <span className="mono text-xs text-mute">synchronized · {res.elapsed_ms} ms compute</span>
              </div>
              <div className="grid gap-3 lg:grid-cols-[1.2fr_1fr]">
                <Panel title="measured outcome" sub={`t=${res.fork_tick} → t=${res.end_tick}`}>
                  <table className="w-full text-sm">
                    <thead className="label">
                      <tr className="border-b border-line">
                        <th className="px-4 py-2 text-left font-normal">metric</th>
                        <th className="px-2 text-right font-normal">baseline</th>
                        <th className="px-2 text-right font-normal">alternative</th>
                        <th className="px-4 text-right font-normal">Δ</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ROWS.map((r) => {
                        const a = res.baseline[r.k];
                        const b = res.alternative[r.k];
                        const delta = a !== null && b !== null && a !== undefined && b !== undefined ? b - a : null;
                        const good = delta === null || Math.abs(delta) < 1e-9 ? null : r.better === "lower" ? delta < 0 : delta > 0;
                        return (
                          <tr key={r.k} className="border-b border-line/60">
                            <td className="px-4 py-1.5 text-ink-2">{r.label}</td>
                            <td className="mono num px-2 text-right">{fmt(a, r.d ?? 1)}</td>
                            <td className="mono num px-2 text-right">{fmt(b, r.d ?? 1)}</td>
                            <td className={cx("mono num px-4 text-right font-medium", good === true && "text-ok", good === false && "text-crit", good === null && "text-faint")}>
                              {delta === null ? "—" : `${delta > 0 ? "+" : ""}${fmt(delta, r.d ?? 1)}`}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </Panel>
                <Panel title="decisions that diverged" sub={`${res.diverged_count} incidents assigned differently`}>
                  <div className="scroll-thin max-h-[360px] overflow-y-auto">
                    {res.diverged_decisions.length === 0 ? (
                      <Empty title="No divergence" body="Both branches made identical assignments." />
                    ) : (
                      res.diverged_decisions.map((d) => (
                        <div key={d.incident} className="border-b border-line/60 px-4 py-2 text-xs">
                          <div className="mono font-semibold">{d.incident}</div>
                          <div className="mono mt-0.5 grid grid-cols-2 gap-2 text-[11px]">
                            <div className="text-mute">base: {d.baseline.map(([t, r]) => `${r}@${t}`).join(", ") || "unassigned"}</div>
                            <div className="text-info">alt: {d.alternative.map(([t, r]) => `${r}@${t}`).join(", ") || "unassigned"}</div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </Panel>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
