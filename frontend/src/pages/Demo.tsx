import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, Circle, Loader2, Play, PlayCircle } from "lucide-react";
import { api } from "../lib/api";
import { useSim } from "../store/sim";
import { CityMap } from "../components/CityMap";
import { Badge, Button, cx } from "../components/ui";

const HINDI_SOS = "हम लोग नदी के पास दूसरी मंज़िल पर फँसे हैं। यहाँ 5 लोग हैं, एक बुज़ुर्ग हैं। पानी बढ़ रहा है। जल्दी मदद भेजिए।";
const PLACE_AT = "N43"; // Riverside, where the demo's dispatcher "confirms" the caller is

type Ctx = { sim: string; proposal?: string; incident?: string; unit?: string; decision?: string };
type Result = { ok: boolean; lines: ReactNode[] };
type Step = { title: string; say: string; run: (ctx: Ctx, tools: Tools) => Promise<Result> };
type Tools = { step: (n: number) => Promise<void>; openDecision: (id: string) => void };

const ev = (sim: string, type: string, params: Record<string, unknown>) => api.post<any>(`/api/simulations/${sim}/events`, { type, params });

const STEPS: Step[] = [
  {
    title: "A flood is unfolding",
    say: "This is a synthetic city. Boats, ground teams and shelters are independent agents negotiating rescues in real time, under a safety shield.",
    run: async (ctx, t) => {
      await t.step(6);
      const f = (await api.get<any>(`/api/simulations/${ctx.sim}`)).frame;
      const active = f.assignments.filter((a: any) => ["COMMITTED", "LOADED"].includes(a.status)).length;
      return { ok: true, lines: [`t=${f.tick}: ${f.incidents.length} incidents reported, ${active} active rescue commitments across ${f.resources.length} units (full fleet: 7 boats, 6 ground teams), ${f.metrics.invariant_violations} safety violations.`] };
    },
  },
  {
    title: "A citizen sends an SOS in Hindi",
    say: "Rules (or Claude, opt-in) extract only evidence. Urgency comes from a fixed rule, and the location “near the river” is not invented: it goes to a human.",
    run: async (ctx) => {
      const r = await api.post<any>(`/api/simulations/${ctx.sim}/sos`, { text: HINDI_SOS });
      const x = r.extraction;
      ctx.proposal = r.routed === "queued_for_dispatcher" ? r.ref : undefined;
      return {
        ok: !!ctx.proposal,
        lines: [
          <span key="t" className="italic">“{HINDI_SOS}”</span>,
          `Understood: ${x.people_count} people, needs ${x.special_needs.join(", ") || "none"}, danger signs ${x.urgency_evidence.map((e: string) => e.replace(/_/g, " ")).join(", ")} → urgency ${x.urgency}/5.`,
          `Location: ${x.location.status === "none" ? "not recognised, so nothing is guessed" : x.location.status}. Queued for the dispatcher as ${r.ref}.`,
        ],
      };
    },
  },
  {
    title: "The dispatcher places it and approves",
    say: "Nothing reaches the agents until a human confirms the location. Approval re-runs every safety check against the current state.",
    run: async (ctx) => {
      if (!ctx.proposal) return { ok: false, lines: ["No pending SOS proposal (run step 2 first)."] };
      const r = await ev(ctx.sim, "APPROVE_PROPOSAL", { proposal_id: ctx.proposal, set: { node: PLACE_AT } });
      const m = (r.event.effects[0] as string).match(/I-\d{3}/);
      ctx.incident = m?.[0];
      return { ok: !!ctx.incident, lines: [r.event.effects[0]] };
    },
  },
  {
    title: "Agents negotiate the rescue",
    say: "Units bid on the request with their own, possibly stale, view of the roads. The cheapest feasible bid wins, a shelter reserves seats, and the shield validates the commit.",
    run: async (ctx, t) => {
      if (!ctx.incident) return { ok: false, lines: ["Run step 3 first."] };
      let decs: any[] = [];
      for (let i = 0; i < 15; i++) {
        await t.step(1);
        decs = (await api.get<any>(`/api/simulations/${ctx.sim}/decisions?incident=${ctx.incident}&limit=10`)).decisions;
        if (decs.some((d) => d.outcome === "COMMITTED")) break;
      }
      const d = [...decs].reverse().find((x) => x.outcome === "COMMITTED") ?? decs[decs.length - 1];
      if (!d) return { ok: false, lines: [`No decision for ${ctx.incident} yet; advance the clock and retry.`] };
      ctx.decision = d.id;
      ctx.unit = d.selected?.resource_id;
      const feasible = d.candidates.filter((c: any) => c.feasible).length;
      return {
        ok: d.outcome === "COMMITTED",
        lines: [
          `${d.id}: ${d.outcome.toLowerCase()}, with ${ctx.unit ?? "no unit"} chosen from ${feasible} feasible bid(s), cost ${d.selected?.cost ?? "?"}, shelter ${d.shelter ?? "?"}.`,
          <button key="b" className="text-info underline" onClick={() => t.openDecision(d.id)}>Open the decision record</button>,
        ],
      };
    },
  },
  {
    title: "Break it three ways at once",
    say: "A live bridge collapses, a committed boat fails and a busy shelter overflows, all chosen from the live state. Affected commitments are cancelled and renegotiated.",
    run: async (ctx, t) => {
      const r = await ev(ctx.sim, "TRIPLE_FAILURE", {});
      await t.step(2);
      const f = (await api.get<any>(`/api/simulations/${ctx.sim}`)).frame;
      return { ok: true, lines: [...(r.event.effects as string[]).map((e, i) => <span key={i} className="block">{e}</span>), `Two minutes later: ${f.metrics.reassignments} reassignment(s), ${f.metrics.invariant_violations} safety violations.`] };
    },
  },
  {
    title: "The crew sees its updated mission",
    say: "Each unit's crew works from a phone app. Every tap is a validated, idempotent engine event, and updates queued without signal are reconciled when it returns.",
    run: async (ctx) => {
      const f = (await api.get<any>(`/api/simulations/${ctx.sim}`)).frame;
      const live = f.resources.filter((r: any) => r.assignment_id && r.status !== "DISABLED");
      const unit = live.find((r: any) => r.id === ctx.unit) ?? live[0];
      if (!unit) return { ok: false, lines: ["No unit has a mission right now."] };
      const v = await api.get<any>(`/api/simulations/${ctx.sim}/crew/${unit.id}`);
      return {
        ok: !!v.mission,
        lines: [
          `${unit.id}: mission ${v.mission.assignment} to ${v.mission.incident.id} (${v.mission.incident.people_waiting} waiting), then ${v.mission.shelter.name}. ${v.mission.route.blocked.length} blocked segment(s) on the route.`,
          <a key="a" className="text-info underline" href={`/crew/${unit.id}`} target="_blank" rel="noreferrer">Open {unit.id}'s crew app on a phone</a>,
        ],
      };
    },
  },
  {
    title: "Ask the Mission Commander",
    say: "It answers only from the run's records, cites every claim, and can only propose actions, which a dispatcher must approve.",
    run: async (ctx) => {
      const q = ctx.incident ? `Why was ${ctx.incident} reassigned?` : "Status";
      const a = await api.post<any>(`/api/simulations/${ctx.sim}/ask`, { question: q });
      return { ok: !a.warnings.length, lines: [<b key="q">{q}</b>, a.answer, `${a.citations.length} citation(s), ${a.warnings.length} grounding warning(s), engine ${a.engine}.`] };
    },
  },
  {
    title: "Every claim is measured",
    say: "Ten paired seeds per cell, 95% confidence intervals. On a healthy network the central optimiser is as good or better; when the coordinator fails, the agents keep serving.",
    run: async () => {
      const ev10 = await api.get<any>("/api/evaluation");
      const p = ev10.suites.resilience.scenarios.coordinator_outage.paired["decentralized-centralized"];
      const q = ev10.suites.quality.scenarios.normal.paired["decentralized-centralized"];
      const ci = (x: any, d = 3) => `${x.mean > 0 ? "+" : ""}${x.mean.toFixed(d)} [${x.ci_low.toFixed(d)}, ${x.ci_high.toFixed(d)}]`;
      return {
        ok: true,
        lines: [
          `Coordinator outage, multi-agent − centralised: service rate ${ci(p.service_rate)}, mean time to service ${ci(p.mean_time_to_service, 1)} min.`,
          `Healthy network, same comparison: mean time to service ${ci(q.mean_time_to_service, 1)} min (centralised is faster).`,
          <span key="l">
            <Link className="text-info underline" to="/arena">Arena</Link> · <Link className="text-info underline" to="/research">Evidence & assumptions</Link>
          </span>,
        ],
      };
    },
  },
];

/** Guided judge demonstration: every step runs the real engine and shows what it returned. */
export default function Demo() {
  const { world, frame, createSim, control, openDecision } = useSim();
  const [ctx, setCtx] = useState<Ctx | null>(null);
  const [results, setResults] = useState<(Result | null)[]>(STEPS.map(() => null));
  const [running, setRunning] = useState<number | null>(null);
  const done = results.filter(Boolean).length;

  const tools: Tools = { step: async (n) => void (await control("step", n)), openDecision };

  const runStep = async (i: number, c: Ctx) => {
    setRunning(i);
    try {
      const r = await STEPS[i].run(c, tools);
      setResults((x) => x.map((y, j) => (j === i ? r : y)));
      setCtx({ ...c });
      return r.ok;
    } catch (e) {
      setResults((x) => x.map((y, j) => (j === i ? { ok: false, lines: [(e as Error).message] } : y)));
      return false;
    } finally {
      setRunning(null);
    }
  };
  const start = async () => {
    setRunning(-1);
    setResults(STEPS.map(() => null));
    // full fleet (the scenario's maximum) so the demo SOS is served within minutes; the
    // default fleet is busier and an urgent SOS can wait 15–30 min, which Arena reports
    await createSim("normal", "decentralized", { seed: 7, boats: 7, ground_units: 6 });
    const sim = useSim.getState().sim!;
    const c = { sim: sim.id };
    setCtx(c);
    setRunning(null);
    return c;
  };
  const runAll = async () => {
    const c = ctx && done === 0 ? ctx : await start();
    for (let i = 0; i < STEPS.length; i++) if (!(await runStep(i, c))) break;
  };

  return (
    <div className="space-y-3 p-3">
      <section className="rounded-2xl bg-slate-950 p-6 text-white">
        <p className="text-xs uppercase tracking-[0.25em] text-cyan-300">RESQNET · guided demonstration</p>
        <h1 className="my-2 text-3xl font-semibold">It doesn't just find a rescue route. It keeps rescue decisions coordinated, safe and explainable when the situation changes.</h1>
        <p className="max-w-3xl text-slate-300">Eight steps, about three minutes. Every button runs the real engine; what appears under each step is what the system actually returned on this run.</p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="solid" icon={<PlayCircle className="size-4" />} loading={running !== null} onClick={runAll}>
            Run the whole demo
          </Button>
          <Button disabled={running !== null} onClick={start}>
            New run (seed 7, full fleet)
          </Button>
          <span className="self-center text-sm text-slate-400">{done}/{STEPS.length} steps done</span>
        </div>
      </section>
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <ol className="space-y-2">
          {STEPS.map((s, i) => {
            const r = results[i];
            const can = !!ctx && running === null && (i === 0 || !!results[i - 1]);
            return (
              <li key={s.title} className={cx("panel p-4", running === i && "ring-2 ring-info/40")}>
                <div className="flex items-start gap-3">
                  <div className="mt-0.5">{running === i ? <Loader2 className="size-5 animate-spin text-info" /> : r ? <CheckCircle2 className={cx("size-5", r.ok ? "text-ok" : "text-warn")} /> : <Circle className="size-5 text-faint" />}</div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-[15px] font-semibold">
                        {i + 1}. {s.title}
                      </div>
                      <Button size="sm" icon={<Play className="size-3.5" />} disabled={!can} onClick={() => ctx && runStep(i, ctx)}>
                        {r ? "Run again" : "Do it"}
                      </Button>
                    </div>
                    <p className="mt-1 text-[12.5px] text-mute">
                      <Badge>say</Badge> {s.say}
                    </p>
                    {r && (
                      <div className="mt-2 space-y-1 rounded-lg bg-black/[0.03] p-2.5 text-[12.5px] leading-relaxed">
                        {r.lines.map((l, j) => (
                          <div key={j}>{l}</div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
        <div className="xl:sticky xl:top-24 xl:h-[calc(100vh-120px)]">
          {world && frame && ctx ? (
            <div className="panel h-[60vh] min-h-[360px] xl:h-full">
              <CityMap world={world} frame={frame} />
            </div>
          ) : (
            <div className="panel flex h-64 items-center justify-center p-6 text-center text-sm text-mute">Start the demo to load a fresh run (seed 7, full fleet). The live map appears here.</div>
          )}
        </div>
      </div>
      <p className="text-[12px] text-mute">Research and education simulation in a synthetic city. Assumptions, such as the coordinator outage leaving peer communication intact, are listed on the <Link className="underline" to="/research">evidence page</Link>.</p>
    </div>
  );
}
