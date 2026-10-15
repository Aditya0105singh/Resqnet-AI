import { useEffect, useRef, useState } from "react";
import { Swords } from "lucide-react";
import { Bar, BarChart, CartesianGrid, ErrorBar, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../lib/api";
import { useSim } from "../store/sim";
import { Badge, Button, cx, Empty, Field, inputCls, PageHeader, Panel } from "../components/ui";
import { fmt, STRATEGY_LABEL } from "../lib/format";

const STRATS = ["decentralized", "centralized", "greedy"];
const COLORS: Record<string, string> = { decentralized: "#0891b2", centralized: "#0a0a0a", greedy: "#a1a1aa" };
const METRICS: { k: string; label: string; better: "lower" | "higher"; d?: number }[] = [
  { k: "mean_time_to_service", label: "Mean time to service (min)", better: "lower" },
  { k: "deadline_misses", label: "Urgent deadline misses", better: "lower" },
  { k: "unmet_people", label: "People not delivered", better: "lower" },
  { k: "idle_with_demand_ticks", label: "Idle ticks while demand open", better: "lower" },
  { k: "fairness_jain", label: "Fairness (Jain index)", better: "higher", d: 3 },
  { k: "route_violations", label: "Route violations", better: "lower" },
  { k: "reassignments", label: "Reassignments", better: "lower" },
  { k: "negotiation_messages", label: "Coordination messages", better: "lower", d: 0 },
  { k: "compute_ms", label: "Coordination compute (ms)", better: "lower" },
  { k: "mean_recovery_time", label: "Mean recovery time (min)", better: "lower" },
];

export default function Arena() {
  const sim = useSim((s) => s.sim);
  const toast = useSim((s) => s.toast);
  const [scenario, setScenario] = useState("triple_failure");
  const [strategies, setStrategies] = useState<string[]>(STRATS);
  const [seedStart, setSeedStart] = useState(1);
  const [nSeeds, setNSeeds] = useState(6);
  const [job, setJob] = useState<any>(null);
  const poll = useRef<ReturnType<typeof setInterval>>();

  useEffect(() => () => clearInterval(poll.current), []);
  useEffect(() => {
    if (sim) setScenario(sim.scenario);
  }, [sim?.scenario]); // eslint-disable-line react-hooks/exhaustive-deps

  const start = async () => {
    try {
      const j = await api.post<any>("/api/benchmarks", { scenario, strategies, seeds: Array.from({ length: nSeeds }, (_, i) => seedStart + i), overrides: { map: useSim.getState().mapId } });
      setJob(j);
      clearInterval(poll.current);
      poll.current = setInterval(async () => {
        const r = await api.get<any>(`/api/benchmarks/${j.id}`);
        setJob(r);
        if (r.status !== "running") clearInterval(poll.current);
        if (r.status === "error") toast({ kind: "crit", title: "Benchmark failed", body: r.error });
      }, 600);
    } catch (e) {
      toast({ kind: "crit", title: "Could not start benchmark", body: (e as Error).message });
    }
  };

  const res = job?.status === "done" ? job.result : null;
  return (
    <div className="space-y-3 p-3">
      <PageHeader
        eyebrow="strategy arena"
        title="Multi-agent negotiation vs a fair centralised optimiser"
        sub="Every strategy runs the same scenario, seeds, incident arrivals and failure schedule, with the same safety shield, shelter agents and cost function. They differ only in information access and coordination mechanism. Nothing is hard-coded: if the centralised baseline wins, this page says so."
      />
      <Panel title="experiment">
        <div className="flex flex-wrap items-end gap-4 p-4">
          <Field label="scenario">
            <select className={cx(inputCls, "w-56")} value={scenario} onChange={(e) => setScenario(e.target.value)}>
              {["coordinator_outage", "bridge_dependency", "normal", "contradictory", "triple_failure", "flash_flood", "bridge_closure", "resource_shortage", "shelter_overflow"].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </Field>
          <Field label="first seed">
            <input className={cx(inputCls, "w-24")} type="number" value={seedStart} onChange={(e) => setSeedStart(Number(e.target.value))} />
          </Field>
          <Field label="seeded runs" hint={String(nSeeds)}>
            <input type="range" className="w-40 accent-[#0a0a0a]" min={1} max={20} value={nSeeds} onChange={(e) => setNSeeds(Number(e.target.value))} />
          </Field>
          <div>
            <div className="label mb-1">strategies</div>
            <div className="flex gap-1.5">
              {STRATS.map((s) => (
                <label key={s} className={cx("flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm", strategies.includes(s) ? "border-ink bg-ink text-white" : "border-line-2 bg-white")}>
                  <input type="checkbox" className="hidden" checked={strategies.includes(s)} onChange={() => setStrategies((x) => (x.includes(s) ? x.filter((y) => y !== s) : [...x, s]))} />
                  <span className="size-2 rounded-full" style={{ background: COLORS[s] }} />
                  {STRATEGY_LABEL[s]}
                </label>
              ))}
            </div>
          </div>
          <Button variant="solid" icon={<Swords className="size-4" />} disabled={!strategies.length} loading={job?.status === "running"} onClick={start} className="ml-auto">
            Run {strategies.length * nSeeds} simulations
          </Button>
        </div>
        {job?.status === "running" && (
          <div className="px-4 pb-4">
            <div className="h-1.5 overflow-hidden rounded-full bg-black/[0.06]">
              <div className="h-full bg-info transition-all" style={{ width: `${(job.progress ?? 0) * 100}%` }} />
            </div>
            <div className="mono mt-1 text-[11px] text-mute">{Math.round((job.progress ?? 0) * 100)}% · each run is a full 180-tick simulation</div>
          </div>
        )}
      </Panel>

      {!res ? (
        <Panel title="results">
          <Empty icon={<Swords className="size-6" />} title={job?.status === "running" ? "Running…" : "No benchmark yet"} body="Results report means, standard deviations, per-seed values and paired differences." />
        </Panel>
      ) : (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            {METRICS.map((m) => {
              const data = res.strategies.map((s: string) => ({ s: STRATEGY_LABEL[s], key: s, mean: res.summary[s][m.k].mean ?? 0, std: res.summary[s][m.k].std ?? 0 }));
              const vals = data.map((d: any) => d.mean);
              const best = m.better === "lower" ? Math.min(...vals) : Math.max(...vals);
              const winners = data.filter((d: any) => d.mean === best);
              return (
                <Panel key={m.k} title={m.label} right={winners.length === 1 && vals.some((v: number) => v !== best) ? <Badge tone="ok">{winners[0].s}</Badge> : <Badge>tie</Badge>}>
                  <div className="h-40 px-1 pt-2">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={data} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
                        <CartesianGrid vertical={false} stroke="#efefec" />
                        <XAxis dataKey="s" tick={{ fontSize: 10, fontFamily: "JetBrains Mono" }} axisLine={false} tickLine={false} />
                        <YAxis tick={{ fontSize: 10, fontFamily: "JetBrains Mono" }} axisLine={false} tickLine={false} />
                        <Tooltip contentStyle={{ fontSize: 11, borderRadius: 8 }} formatter={(v: number, _n, p: any) => [`${fmt(v, m.d ?? 2)} ± ${fmt(p.payload.std, 2)}`, "mean ± sd"]} />
                        <Bar dataKey="mean" radius={[4, 4, 0, 0]} isAnimationActive={false} shape={(props: any) => <rect x={props.x} y={props.y} width={props.width} height={props.height} rx={4} fill={COLORS[props.payload.key]} />}>
                          <ErrorBar dataKey="std" width={6} stroke="#71717a" />
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </Panel>
              );
            })}
          </div>
          {Object.keys(res.paired_decentralized_minus_centralized ?? {}).length > 0 && (
            <Panel title="paired difference · multi-agent − centralised (same seed)" sub="Negative is better for time, misses, unmet, idle and messages; positive is better for fairness. ±sd across seeds.">
              <div className="grid gap-3 p-4 sm:grid-cols-3 lg:grid-cols-6">
                {Object.entries(res.paired_decentralized_minus_centralized).map(([k, v]: [string, any]) => (
                  <div key={k}>
                    <div className="label">{k.replace(/_/g, " ")}</div>
                    <div className="mono num mt-1 text-lg font-semibold">
                      {v.mean === null ? "—" : `${v.mean > 0 ? "+" : ""}${fmt(v.mean, 2)}`}
                      <span className="ml-1 text-xs font-normal text-mute">±{fmt(v.std, 2)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </Panel>
          )}
          <Panel title="individual runs" sub={`${res.runs.length} runs · scenario ${res.scenario}`}>
            <div className="scroll-thin max-h-[420px] overflow-auto">
              <table className="w-full text-[12.5px]">
                <thead className="label sticky top-0 bg-white">
                  <tr className="border-b border-line">
                    {["seed", "strategy", "mean tts", "misses", "unmet", "idle w/ demand", "fairness", "reassign", "messages", "violations", "wall ms"].map((h) => (
                      <th key={h} className="px-3 py-2 text-left font-normal">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {res.runs.map((r: any, i: number) => (
                    <tr key={i} className="mono border-b border-line/60">
                      <td className="px-3 py-1">{r.seed}</td>
                      <td className="px-3">
                        <span className="mr-1.5 inline-block size-2 rounded-full" style={{ background: COLORS[r.strategy] }} />
                        {STRATEGY_LABEL[r.strategy]}
                      </td>
                      <td className="px-3">{fmt(r.mean_time_to_service)}</td>
                      <td className="px-3">{r.deadline_misses}</td>
                      <td className="px-3">{r.unmet_people}</td>
                      <td className="px-3">{r.idle_with_demand_ticks}</td>
                      <td className="px-3">{fmt(r.fairness_jain, 3)}</td>
                      <td className="px-3">{r.reassignments}</td>
                      <td className="px-3">{r.negotiation_messages}</td>
                      <td className={cx("px-3", r.route_violations ? "text-crit" : "text-ok")}>{r.route_violations}</td>
                      <td className="px-3 text-mute">{r.wall_ms}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </>
      )}
    </div>
  );
}
