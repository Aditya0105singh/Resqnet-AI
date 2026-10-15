import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Crosshair, ShieldCheck } from "lucide-react";
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import { api } from "../lib/api";
import { useSim } from "../store/sim";
import { Badge, Button, cx, Empty, Field, inputCls, PageHeader, Panel } from "../components/ui";
import { fmt, STRATEGY_LABEL } from "../lib/format";

const CATS = ["bridge", "boat", "ground", "shelter", "surge", "blackout"];

const RULE_TEXT: Record<string, string> = {
  S1: "No unit is sent to two places at once",
  S2: "No shelter takes more people than it has space for",
  S3: "Boats stay on water, teams stay on dry roads, closed roads are never used",
  S4: "No unit carries more people than its seats",
  S5: "No decision is made on out-of-date information",
  S6: "Shelter space must be reserved before people are sent",
  S7: "Only working, reachable units get missions",
};

export default function Safety() {
  const { sim, frame, createSim, toast } = useSim();
  const nav = useNavigate();
  const [log, setLog] = useState<any>(null);
  const [form, setForm] = useState({ scenario: "normal", strategy: "decentralized", n_failures: 3, categories: ["bridge", "boat", "shelter"], trials: 16, seed: 42 });
  const [job, setJob] = useState<any>(null);
  const poll = useRef<ReturnType<typeof setInterval>>();

  useEffect(() => {
    if (!sim) return;
    api.get<any>(`/api/simulations/${sim.id}/safety`).then(setLog).catch(() => {});
  }, [sim?.id, frame?.metrics.safety_rejections, frame?.metrics.blocked_moves, frame?.tick]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => clearInterval(poll.current), []);

  const run = async () => {
    try {
      const j = await api.post<any>("/api/adversarial", form);
      setJob(j);
      clearInterval(poll.current);
      poll.current = setInterval(async () => {
        const r = await api.get<any>(`/api/adversarial/${j.id}`);
        setJob(r);
        if (r.status !== "running") clearInterval(poll.current);
      }, 600);
    } catch (e) {
      toast({ kind: "crit", title: "Search failed to start", body: (e as Error).message });
    }
  };
  const openScenario = async (w: any) => {
    await createSim(job.request.scenario, job.request.strategy, { schedule: w.failures.map((f: any) => ({ tick: f.tick, type: f.type, params: f.params })) }).catch(() => {});
    nav("/command");
  };

  const res = job?.status === "done" ? job.result : null;
  const m = frame?.metrics;
  return (
    <div className="space-y-3 p-3">
      <PageHeader
        eyebrow="Results"
        title="Safety tests"
        sub="Every plan and every move is checked against seven safety rules before it happens. Below, a stress test hunts for the failure combinations that hurt most."
      />
      <div className="grid gap-3 lg:grid-cols-4">
        {[
          ["unsafe moves made", m?.route_violations ?? 0, "a unit travelled where it must not"],
          ["safety rules broken", m?.invariant_violations ?? 0, "checked across the whole city every minute"],
          ["unsafe plans blocked", m?.safety_rejections ?? 0, "plans stopped before they happened"],
          ["moves stopped", m?.blocked_moves ?? 0, "a unit found a closed road and halted"],
        ].map(([k, v, h]) => (
          <div key={k as string} className="panel px-4 py-3">
            <div className="label">{k}</div>
            <div className={cx("mono num mt-1 text-2xl font-semibold", (k as string).includes("violations") ? ((v as number) ? "text-crit" : "text-ok") : "")}>{v}</div>
            <div className="text-[11px] text-mute">{h}</div>
          </div>
        ))}
      </div>
      <div className="grid gap-3 xl:grid-cols-[360px_1fr]">
        <Panel title="the seven safety rules">
          <ul className="space-y-2 p-4 text-sm">
            {(log?.invariants ?? []).map((i: string) => (
              <li key={i} className="flex items-start gap-2">
                <ShieldCheck className="mt-0.5 size-4 shrink-0 text-ok" />
                <span>
                  {RULE_TEXT[i.slice(0, 2)] ?? i} <span className="mono text-[11px] text-faint">{i.slice(0, 2)}</span>
                </span>
              </li>
            ))}
          </ul>
          <p className="px-4 pb-4 text-xs leading-relaxed text-mute">Checked before every plan is accepted, before every unit enters a road, and across the whole city every minute. The same checks apply to every coordination approach.</p>
        </Panel>
        <Panel title="blocked actions" sub="Unsafe plans and moves that were stopped, newest first">
          <div className="scroll-thin max-h-[360px] overflow-y-auto">
            {!log?.log?.length ? (
              <Empty icon={<ShieldCheck className="size-5" />} title="Nothing rejected yet" body="Inject a bridge closure or flood surge — units that discover a closed edge are stopped by the movement gate and logged here." />
            ) : (
              <table className="w-full text-[12px]">
                <tbody>
                  {log.log.map((r: any, i: number) => (
                    <tr key={i} className="border-b border-line/60 align-top">
                      <td className="mono px-3 py-1.5 text-faint">t={r.tick}</td>
                      <td className="px-2">
                        <Badge tone={r.type === "MOVEMENT_BLOCKED" ? "warn" : "crit"}>{(r.code ?? r.type).replace(/_/g, " ").toLowerCase()}</Badge>
                      </td>
                      <td className="mono px-2">{r.resource}</td>
                      <td className="px-3 text-ink-2">{r.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </Panel>
      </div>

      <Panel title="stress test" sub="Tries many random combinations of failures and ranks the ones that hurt most. A search, not a proof.">
        <div className="flex flex-wrap items-end gap-4 border-b border-line p-4">
          <Field label="scenario">
            <select className={cx(inputCls, "w-44")} value={form.scenario} onChange={(e) => setForm({ ...form, scenario: e.target.value })}>
              {["normal", "contradictory", "flash_flood", "resource_shortage"].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </Field>
          <Field label="strategy">
            <select className={cx(inputCls, "w-40")} value={form.strategy} onChange={(e) => setForm({ ...form, strategy: e.target.value })}>
              {["decentralized", "message_passing", "centralized", "greedy"].map((s) => (
                <option key={s} value={s}>
                  {STRATEGY_LABEL[s]}
                </option>
              ))}
            </select>
          </Field>
          <Field label="failures per trial" hint={String(form.n_failures)}>
            <input type="range" className="w-32 accent-[#0a0a0a]" min={1} max={5} value={form.n_failures} onChange={(e) => setForm({ ...form, n_failures: Number(e.target.value) })} />
          </Field>
          <Field label="trials" hint={String(form.trials)}>
            <input type="range" className="w-32 accent-[#0a0a0a]" min={4} max={40} value={form.trials} onChange={(e) => setForm({ ...form, trials: Number(e.target.value) })} />
          </Field>
          <Field label="search seed">
            <input className={cx(inputCls, "w-20")} type="number" value={form.seed} onChange={(e) => setForm({ ...form, seed: Number(e.target.value) })} />
          </Field>
          <div>
            <div className="label mb-1">failure categories</div>
            <div className="flex flex-wrap gap-1">
              {CATS.map((c) => (
                <button key={c} onClick={() => setForm({ ...form, categories: form.categories.includes(c) ? form.categories.filter((x) => x !== c) : [...form.categories, c] })} className={cx("rounded-full border px-2.5 py-1 text-xs", form.categories.includes(c) ? "border-ink bg-ink text-white" : "border-line-2")}>
                  {c}
                </button>
              ))}
            </div>
          </div>
          <Button variant="danger" icon={<Crosshair className="size-4" />} className="ml-auto" disabled={!form.categories.length} loading={job?.status === "running"} onClick={run}>
            Find weakest scenario
          </Button>
        </div>
        {job?.status === "running" && (
          <div className="p-4">
            <div className="h-1.5 overflow-hidden rounded-full bg-black/[0.06]">
              <div className="h-full bg-crit transition-all" style={{ width: `${(job.progress ?? 0) * 100}%` }} />
            </div>
          </div>
        )}
        {job?.status === "error" && <div className="p-4 text-sm text-crit">{job.error}</div>}
        {!res ? (
          job?.status !== "running" && <Empty title="No search run yet" body="Each trial is a complete simulation with the sampled failures scheduled in." />
        ) : (
          <div className="grid gap-3 p-4 xl:grid-cols-[1fr_420px]">
            <div className="space-y-2">
              <div className="text-xs text-mute">
                {res.search_space_note} Score = {res.score_formula}. Baseline without injected failures: {res.baseline.unmet_people} unmet, {res.baseline.deadline_misses} misses, mean TTS {fmt(res.baseline.mean_time_to_service)} min.
              </div>
              {res.worst.map((w: any, idx: number) => (
                <div key={w.trial} className="rounded-xl border border-line p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-display text-sm font-semibold">#{idx + 1} · trial {w.trial}</span>
                    <Badge tone="crit">score {w.score}</Badge>
                    <span className="mono text-xs text-mute">
                      unmet {w.metrics.unmet_people} · misses {w.metrics.deadline_misses} · TTS {fmt(w.metrics.mean_time_to_service)} · recovery {fmt(w.metrics.mean_recovery_time)} · violations {w.metrics.route_violations}
                    </span>
                    <Button size="sm" className="ml-auto" onClick={() => openScenario(w)}>
                      Open in simulator
                    </Button>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {w.failures.map((f: any, i: number) => (
                      <span key={i} className="mono rounded-md border border-line bg-wash px-2 py-0.5 text-[11px]">
                        t={f.tick} {f.type.replace(/_/g, " ").toLowerCase()} {Object.values(f.params).filter((v) => typeof v === "string" && !(v as string).includes(":")).join(" ")}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <div className="h-80">
              <div className="label mb-1">all trials · unmet people vs deadline misses</div>
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 10, right: 10, bottom: 20, left: -10 }}>
                  <CartesianGrid stroke="#efefec" />
                  <XAxis type="number" dataKey="unmet" name="unmet" tick={{ fontSize: 10 }} label={{ value: "unmet people", position: "bottom", fontSize: 10 }} />
                  <YAxis type="number" dataKey="misses" name="misses" tick={{ fontSize: 10 }} allowDecimals={false} />
                  <ZAxis type="number" dataKey="score" range={[40, 200]} />
                  <Tooltip contentStyle={{ fontSize: 11 }} />
                  <Scatter data={res.all_scores} fill="#dc2626" fillOpacity={0.55} />
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </Panel>
    </div>
  );
}
