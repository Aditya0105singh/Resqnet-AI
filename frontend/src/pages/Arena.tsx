import { useEffect, useRef, useState } from "react";
import { FlaskConical, Swords } from "lucide-react";
import { Bar, BarChart, CartesianGrid, ErrorBar, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../lib/api";
import { useSim } from "../store/sim";
import { Badge, Button, cx, Empty, Field, inputCls, PageHeader, Panel, Segmented, Spinner } from "../components/ui";
import { fmt, STRATEGY_LABEL } from "../lib/format";

const STRATS = ["decentralized", "message_passing", "centralized", "greedy"];
// categorical slots 1–4 of the validated reference palette (passes CVD + lightness checks;
// two hues are below 3:1 on the surface, so every chart also carries text labels + a table)
const COLORS: Record<string, string> = { decentralized: "#2a78d6", message_passing: "#eb6834", centralized: "#1baf7a", greedy: "#eda100" };

type Agg = { mean: number | null; std: number | null; median?: number | null; q1?: number | null; q3?: number | null; ci_low?: number | null; ci_high?: number | null; n: number; significant?: boolean; n_negative?: number; n_positive?: number };
type MetricDef = { k: string; label: string; better: "lower" | "higher"; d?: number };

const QUALITY_METRICS: MetricDef[] = [
  { k: "service_rate", label: "Service rate (delivered ÷ needing rescue)", better: "higher", d: 3 },
  { k: "mean_time_to_service", label: "Mean time to service (min)", better: "lower", d: 1 },
  { k: "unmet_people", label: "People not delivered", better: "lower", d: 1 },
  { k: "deadline_misses", label: "Urgent deadline misses", better: "lower", d: 1 },
  { k: "fairness_jain", label: "Fairness (Jain index)", better: "higher", d: 3 },
  { k: "negotiation_messages", label: "Coordination messages", better: "lower", d: 0 },
];
const RESILIENCE_METRICS: MetricDef[] = [
  ...QUALITY_METRICS.slice(0, 3),
  { k: "outage_uncovered_people_minutes", label: "Uncovered people·min during outage", better: "lower", d: 0 },
  { k: "commitments_during_outage", label: "New commitments during outage", better: "higher", d: 1 },
  { k: "mean_recovery_time", label: "Recovery after broken commitments (min)", better: "lower", d: 1 },
];
const RUN_METRICS: MetricDef[] = [
  ...QUALITY_METRICS,
  { k: "idle_with_demand_ticks", label: "Idle ticks while demand open", better: "lower", d: 0 },
  { k: "route_violations", label: "Route violations", better: "lower", d: 0 },
  { k: "mean_recovery_time", label: "Mean recovery time (min)", better: "lower", d: 1 },
  { k: "compute_ms", label: "Coordination compute (ms)", better: "lower", d: 0 },
];
const PAIR_LABEL = (p: string) => p.split("-").map((s) => STRATEGY_LABEL[s] ?? s).join(" − ");

const ciText = (a: Agg | undefined, d = 2) => (!a || a.mean === null ? "—" : a.ci_low != null ? `${fmt(a.mean, d)} [${fmt(a.ci_low, d)}, ${fmt(a.ci_high!, d)}]` : `${fmt(a.mean, d)} (n=${a.n}, no CI)`);
// no whisker when there is no CI or it has zero width (all seeds equal)
const errOf = (a: Agg) => (a.ci_low != null && a.ci_high != null && a.mean != null && a.ci_high > a.ci_low ? [a.mean - a.ci_low, a.ci_high - a.mean] : undefined);

function MetricBars({ m, strategies, summary }: { m: MetricDef; strategies: string[]; summary: Record<string, Record<string, Agg>> }) {
  if (strategies.every((s) => summary[s]?.[m.k]?.mean == null))
    return (
      <Panel title={m.label}>
        <div className="flex h-44 items-center justify-center px-6 text-center text-[13px] text-mute">Not applicable here: no run in this scenario produced this measurement.</div>
      </Panel>
    );
  const data = strategies.map((s) => ({ s: STRATEGY_LABEL[s], key: s, mean: summary[s]?.[m.k]?.mean ?? 0, err: errOf(summary[s]?.[m.k] ?? ({ n: 0 } as Agg)), agg: summary[s]?.[m.k] }));
  return (
    <Panel title={m.label} right={<span className="mono text-[10px] text-mute">{m.better} is better · bars 95% CI</span>}>
      <div className="h-44 px-1 pt-2">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 6, right: 8, left: -14, bottom: 0 }} barCategoryGap="22%">
            <CartesianGrid vertical={false} stroke="#efefec" />
            <XAxis dataKey="s" tick={{ fontSize: 10, fontFamily: "JetBrains Mono", fill: "#52525b" }} axisLine={false} tickLine={false} interval={0} />
            <YAxis tick={{ fontSize: 10, fontFamily: "JetBrains Mono", fill: "#71717a" }} axisLine={false} tickLine={false} />
            <Tooltip cursor={{ fill: "rgba(0,0,0,0.04)" }} contentStyle={{ fontSize: 11, borderRadius: 8 }} formatter={(_v: number, _n, p: any) => [ciText(p.payload.agg, m.d ?? 2), "mean [95% CI]"]} />
            <Bar dataKey="mean" isAnimationActive={false} shape={(props: any) => <rect x={props.x} y={props.y} width={props.width} height={Math.max(0, props.height)} rx={4} fill={COLORS[props.payload.key]} />}>
              <ErrorBar dataKey="err" width={6} stroke="#3f3f46" strokeWidth={1.2} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}

function StatsTable({ metrics, strategies, summary }: { metrics: MetricDef[]; strategies: string[]; summary: Record<string, Record<string, Agg>> }) {
  return (
    <div className="scroll-thin overflow-x-auto">
      <table className="w-full text-[12px]">
        <thead className="label">
          <tr className="border-b border-line">
            <th className="px-3 py-2 text-left font-normal">strategy</th>
            {metrics.map((m) => (
              <th key={m.k} className="px-3 py-2 text-left font-normal">
                {m.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {strategies.map((s) => (
            <tr key={s} className="mono border-b border-line/60">
              <td className="whitespace-nowrap px-3 py-1.5">
                <span className="mr-1.5 inline-block size-2 rounded-full" style={{ background: COLORS[s] }} />
                {STRATEGY_LABEL[s]}
              </td>
              {metrics.map((m) => {
                const a = summary[s]?.[m.k];
                return (
                  <td key={m.k} className="whitespace-nowrap px-3">
                    {ciText(a, m.d ?? 2)}
                    {a?.median != null && <div className="text-[10.5px] text-mute">median {fmt(a.median, m.d ?? 2)}</div>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Findings({ paired, keys }: { paired: Record<string, Record<string, Agg>>; keys: MetricDef[] }) {
  const sig: { pair: string; m: MetricDef; a: Agg }[] = [];
  for (const [pair, metrics] of Object.entries(paired ?? {})) for (const m of keys) if (metrics[m.k]?.significant) sig.push({ pair, m, a: metrics[m.k] });
  return (
    <Panel title="what the data supports" sub="Paired by seed (same incidents, reports and failures). Listed only when the 95% CI of the per-seed difference excludes zero.">
      {sig.length === 0 ? (
        <div className="p-4 text-sm text-mute">No significant difference on these metrics: every paired CI includes zero.</div>
      ) : (
        <ul className="divide-y divide-line/70">
          {sig.map(({ pair, m, a }, i) => {
            const [x, y] = pair.split("-");
            const good = m.better === "lower" ? a.mean! < 0 : a.mean! > 0;
            // seeds on which the strategy named in the badge did better
            const winnerSeeds = (m.better === "lower") === good ? a.n_negative : a.n_positive;
            return (
              <li key={i} className="flex flex-wrap items-baseline gap-x-2 px-4 py-2 text-[13px]">
                <Badge tone={good ? "ok" : "warn"}>{good ? `${STRATEGY_LABEL[x]} better` : `${STRATEGY_LABEL[y]} better`}</Badge>
                <span>{m.label}</span>
                <span className="mono text-mute">
                  {PAIR_LABEL(pair)} = {a.mean! > 0 ? "+" : ""}
                  {fmt(a.mean!, m.d ?? 2)} [{fmt(a.ci_low!, m.d ?? 2)}, {fmt(a.ci_high!, m.d ?? 2)}] · better on {winnerSeeds}/{a.n} seeds
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

function SweepChart({ sw }: { sw: any }) {
  const n = sw.strategies.length;
  const step = sw.values.length > 1 ? sw.values[1] - sw.values[0] : 1;
  // dodge each strategy a little along x so overlapping CI whiskers stay readable
  const series = sw.strategies.map((st: string, i: number) => ({
    st,
    data: sw.values.map((v: number) => {
      const p = sw.points.find((q: any) => q.value === v && q.strategy === st);
      return { x: n > 1 ? v + (i - (n - 1) / 2) * step * 0.07 : v, v, y: p?.service_rate.mean, err: p ? errOf(p.service_rate) : undefined, agg: p?.service_rate };
    }),
  }));
  const lo = Math.min(...sw.points.map((p: any) => p.service_rate.ci_low ?? p.service_rate.mean));
  const hi = Math.max(...sw.points.map((p: any) => p.service_rate.ci_high ?? p.service_rate.mean));
  const domain = [Math.floor(lo * 20) / 20, Math.min(1, Math.ceil(hi * 20) / 20)];
  return (
    <Panel title={sw.title} sub={`${sw.question} Base scenario ${sw.base}. Service rate, mean with 95% CI${n > 1 ? "; strategies offset slightly along x" : ""}.`}>
      <div className="h-64 px-2 pt-2">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart margin={{ top: 8, right: 16, left: -10, bottom: 4 }}>
            <CartesianGrid vertical={false} stroke="#efefec" />
            <XAxis type="number" dataKey="x" domain={[sw.values[0] - step * 0.3, sw.values[sw.values.length - 1] + step * 0.3]} ticks={sw.values} tick={{ fontSize: 10, fontFamily: "JetBrains Mono", fill: "#52525b" }} axisLine={false} tickLine={false} label={{ value: sw.param, position: "insideBottomRight", offset: -2, fontSize: 10, fill: "#71717a" }} />
            <YAxis type="number" domain={domain} tickCount={5} tickFormatter={(v: number) => v.toFixed(2)} tick={{ fontSize: 10, fontFamily: "JetBrains Mono", fill: "#71717a" }} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={{ fontSize: 11, borderRadius: 8 }} formatter={(_v: number, name: string, p: any) => [ciText(p.payload.agg, 3), STRATEGY_LABEL[name] ?? name]} labelFormatter={() => ""} />
            {n > 1 && <Legend formatter={(v: string) => <span className="text-[11px] text-ink">{STRATEGY_LABEL[v] ?? v}</span>} />}
            {series.map(({ st, data }: any) => (
              <Line key={st} name={st} data={data} dataKey="y" stroke={COLORS[st]} strokeWidth={2} dot={{ r: 4, strokeWidth: 2, stroke: "#fff", fill: COLORS[st] }} isAnimationActive={false}>
                <ErrorBar dataKey="err" width={4} stroke={COLORS[st]} strokeWidth={1.2} direction="y" />
              </Line>
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}

const ABLATION_LABEL: Record<string, MetricDef> = {
  false_alarm_visits: { k: "false_alarm_visits", label: "Trips to non-existent victims", better: "lower", d: 1 },
  service_rate: { k: "service_rate", label: "Service rate", better: "higher", d: 3 },
  mean_time_to_service: { k: "mean_time_to_service", label: "Mean time to service (min)", better: "lower", d: 1 },
  deadline_misses: { k: "deadline_misses", label: "Urgent misses", better: "lower", d: 1 },
};

function AblationPanel({ ab }: { ab: any }) {
  const [[off], [on]] = ab.variants;
  return (
    <Panel title={ab.title} sub={`${ab.question} Base scenario ${ab.base}; same seeds, only ${ab.param} changes. Cells: ${off} → ${on}, paired Δ with 95% CI.`}>
      <div className="scroll-thin overflow-x-auto">
        <table className="w-full text-[12px]">
          <thead className="label">
            <tr className="border-b border-line">
              <th className="px-3 py-2 text-left font-normal">strategy</th>
              {ab.keys.map((k: string) => (
                <th key={k} className="px-3 py-2 text-left font-normal">
                  {ABLATION_LABEL[k]?.label ?? k} <span className="normal-case text-mute">({ABLATION_LABEL[k]?.better} is better)</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ab.strategies.map((st: string) => (
              <tr key={st} className="mono border-b border-line/60">
                <td className="whitespace-nowrap px-3 py-2">
                  <span className="mr-1.5 inline-block size-2 rounded-full" style={{ background: COLORS[st] }} />
                  {STRATEGY_LABEL[st]}
                </td>
                {ab.keys.map((k: string) => {
                  const m = ABLATION_LABEL[k] ?? { k, label: k, better: "lower", d: 2 };
                  const a = ab.results[st].summary[off][k];
                  const b = ab.results[st].summary[on][k];
                  const d: Agg = ab.results[st].paired[k];
                  const good = d.mean != null && (m.better === "lower" ? d.mean < 0 : d.mean > 0);
                  return (
                    <td key={k} className="whitespace-nowrap px-3 py-2">
                      {fmt(a.mean, m.d)} → {fmt(b.mean, m.d)}
                      <div className="flex items-center gap-1.5 text-[10.5px] text-mute">
                        Δ {d.mean != null && d.mean > 0 ? "+" : ""}
                        {fmt(d.mean, m.d)}
                        {d.ci_low != null && ` [${fmt(d.ci_low, m.d)}, ${fmt(d.ci_high!, m.d)}]`}
                        {d.significant && <Badge tone={good ? "ok" : "warn"}>{good ? "better" : "worse"}</Badge>}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function Published() {
  const [ev, setEv] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [suite, setSuite] = useState<"quality" | "resilience">("resilience");
  const [scenario, setScenario] = useState<string>("");
  useEffect(() => {
    api.get<any>("/api/evaluation").then(setEv).catch((e) => setErr((e as Error).message));
  }, []);
  const s = ev?.suites?.[suite];
  useEffect(() => {
    if (s && !s.scenarios[scenario]) setScenario(Object.keys(s.scenarios)[0]);
  }, [suite, ev]); // eslint-disable-line react-hooks/exhaustive-deps
  if (err) return <Panel title="published results"><Empty icon={<FlaskConical className="size-6" />} title="No published evaluation" body={err} /></Panel>;
  if (!ev || !s) return <Spinner label="Loading published results…" />;
  const res = s.scenarios[scenario];
  const metrics = suite === "quality" ? QUALITY_METRICS : RESILIENCE_METRICS;
  return (
    <>
      <Panel
        title={s.title}
        sub={`${s.question} ${ev.seeds.length} paired seeds per cell · generated ${ev.generated.slice(0, 10)} · reproduce with python scripts/run_benchmarks.py ${ev.seeds.length}; raw rows in data/evaluation/benchmarks/`}
        right={<Segmented size="sm" value={suite} onChange={setSuite} options={[{ value: "quality", label: "Optimisation quality" }, { value: "resilience", label: "Failure resilience" }]} />}
      >
        <div className="flex flex-wrap items-center gap-1.5 px-4 pb-3">
          {Object.keys(s.scenarios).map((k) => (
            <button key={k} onClick={() => setScenario(k)} className={cx("mono rounded-full border px-3 py-1 text-[12px]", k === scenario ? "border-ink bg-ink text-white" : "border-line-2 bg-white hover:border-ink")}>
              {k}
            </button>
          ))}
        </div>
        {res && <p className="px-4 pb-4 text-[13px] text-mute">{res.description}</p>}
      </Panel>
      {res && (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {metrics.map((m) => (
              <MetricBars key={m.k} m={m} strategies={res.strategies} summary={res.summary} />
            ))}
          </div>
          <Findings paired={res.paired} keys={metrics} />
          <Panel title="table view" sub="mean [95% bootstrap CI], median below">
            <StatsTable metrics={metrics} strategies={res.strategies} summary={res.summary} />
          </Panel>
        </>
      )}
      <div className="grid gap-3 lg:grid-cols-2">
        {Object.values(ev.sweeps ?? {}).map((sw: any) => (
          <SweepChart key={sw.param} sw={sw} />
        ))}
      </div>
      {Object.values(ev.ablations ?? {}).map((ab: any) => (
        <AblationPanel key={ab.param} ab={ab} />
      ))}
    </>
  );
}

function RunOwn() {
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
      const j = await api.post<any>("/api/benchmarks", { scenario, strategies, seeds: Array.from({ length: nSeeds }, (_, i) => seedStart + i) });
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
    <>
      <Panel title="experiment">
        <div className="flex flex-wrap items-end gap-4 p-4">
          <Field label="scenario">
            <select className={cx(inputCls, "w-56")} value={scenario} onChange={(e) => setScenario(e.target.value)}>
              {["coordinator_outage", "network_partition", "lossy_network", "bridge_dependency", "normal", "contradictory", "triple_failure", "flash_flood", "bridge_closure", "resource_shortage", "shelter_overflow"].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </Field>
          <Field label="first seed">
            <input className={cx(inputCls, "w-24")} type="number" value={seedStart} onChange={(e) => setSeedStart(Number(e.target.value))} />
          </Field>
          <Field label="seeded runs" hint={`${nSeeds}${nSeeds < 5 ? " · no CI below 5" : ""}`}>
            <input type="range" className="w-40 accent-[#0a0a0a]" min={1} max={20} value={nSeeds} onChange={(e) => setNSeeds(Number(e.target.value))} />
          </Field>
          <div>
            <div className="label mb-1">strategies</div>
            <div className="flex flex-wrap gap-1.5">
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
          <Empty icon={<Swords className="size-6" />} title={job?.status === "running" ? "Running…" : "No benchmark yet"} body="Results report means with 95% bootstrap CIs (5+ seeds), medians, per-seed values and paired differences." />
        </Panel>
      ) : (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {RUN_METRICS.map((m) => (
              <MetricBars key={m.k} m={m} strategies={res.strategies} summary={res.summary} />
            ))}
          </div>
          <Findings paired={res.paired} keys={RUN_METRICS} />
          <Panel title="individual runs" sub={`${res.runs.length} runs · scenario ${res.scenario}`}>
            <div className="scroll-thin max-h-[420px] overflow-auto">
              <table className="w-full text-[12.5px]">
                <thead className="label sticky top-0 bg-white">
                  <tr className="border-b border-line">
                    {["seed", "strategy", "service", "mean tts", "misses", "unmet", "idle w/ demand", "fairness", "reassign", "messages", "violations", "wall ms"].map((h) => (
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
                      <td className="px-3">{fmt(r.service_rate, 3)}</td>
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
    </>
  );
}

export default function Arena() {
  const [tab, setTab] = useState<"published" | "run">("published");
  return (
    <div className="space-y-3 p-3">
      <PageHeader
        eyebrow="Results"
        title="Benchmarks: agents vs a central optimiser"
        sub="Every approach faces exactly the same floods, incidents and failures. We report averages with 95% confidence ranges, including where the central optimiser wins."
        right={<Segmented value={tab} onChange={setTab} options={[{ value: "published", label: "Published results" }, { value: "run", label: "Run your own" }]} />}
      />
      {tab === "published" ? <Published /> : <RunOwn />}
    </div>
  );
}
