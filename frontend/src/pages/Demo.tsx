import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, Circle, Loader2, Play, PlayCircle } from "lucide-react";
import { api } from "../lib/api";
import { useSim } from "../store/sim";
import { CityMap } from "../components/CityMap";
import { Badge, Button, cx } from "../components/ui";

const HINDI_SOS = "हम लोग नदी के पास दूसरी मंज़िल पर फँसे हैं। यहाँ 5 लोग हैं, एक बुज़ुर्ग हैं। पानी बढ़ रहा है। जल्दी मदद भेजिए।";
// where the demo's dispatcher "confirms" the caller is: Manapuram Mahadeva Temple by the Periyar
// on the Aluva map, or Riverside on the synthetic fallback city
const PLACE = { aluva: { node: "N001", name: "Manapuram Mahadeva Temple, by the Periyar" }, riverbend: { node: "N43", name: "Riverside" } };

type Ctx = { sim: string; city: keyof typeof PLACE; proposal?: string; incident?: string; unit?: string; decision?: string; shelter?: string };
type Result = { ok: boolean; lines: ReactNode[] };
type Step = { title: string; say: string; run: (ctx: Ctx, tools: Tools) => Promise<Result> };
type Tools = { step: (n: number) => Promise<void>; openDecision: (id: string) => void };

const ev = (sim: string, type: string, params: Record<string, unknown>) => api.post<any>(`/api/simulations/${sim}/events`, { type, params });

const STEPS: Step[] = [
  {
    title: "A flood is unfolding",
    say: "A flood is rising in Aluva, Kerala, on real OpenStreetMap roads, bridges and the Periyar. Every boat, rescue team and shelter is an independent agent that negotiates rescues in real time, and every plan passes a safety check.",
    run: async (ctx, t) => {
      await t.step(6);
      const f = (await api.get<any>(`/api/simulations/${ctx.sim}`)).frame;
      const active = f.assignments.filter((a: any) => ["COMMITTED", "LOADED"].includes(a.status)).length;
      return { ok: true, lines: [`t=${f.tick}: ${f.incidents.length} incidents reported, ${active} active rescue commitments across ${f.resources.length} units (full fleet: 7 boats, 6 ground teams), ${f.metrics.invariant_violations} safety violations.`] };
    },
  },
  {
    title: "A citizen sends an SOS in Hindi",
    say: "The system reads the message and pulls out the facts: how many people, who is vulnerable, how urgent. “Near the river” is not a real location, so it does not guess. A human decides.",
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
    say: "The dispatcher calls back and learns they are at the Manappuram temple by the river, marks it on the map and approves. Approving re-checks safety against the situation right now.",
    run: async (ctx) => {
      if (!ctx.proposal) return { ok: false, lines: ["No pending SOS proposal (run step 2 first)."] };
      const place = PLACE[ctx.city];
      const r = await ev(ctx.sim, "APPROVE_PROPOSAL", { proposal_id: ctx.proposal, set: { node: place.node } });
      const m = (r.event.effects[0] as string).match(/I-\d{3}/);
      ctx.incident = m?.[0];
      return { ok: !!ctx.incident, lines: [`Placed at ${place.name}.`, r.event.effects[0]] };
    },
  },
  {
    title: "Agents negotiate the rescue",
    say: "Nearby units bid for the rescue using what they know about the roads. The best bid wins, a shelter reserves space, and the safety check approves it.",
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
      ctx.shelter = d.shelter ?? undefined;
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
    say: "Now three things fail at the same minute: the shelter our rescue is heading to fills up, a bridge collapses, and the team on its way to the temple breaks down. The rescue is re-negotiated with another unit, safely.",
    run: async (ctx, t) => {
      if (!ctx.unit) return { ok: false, lines: ["Run step 4 first."] };
      const before = (await api.get<any>(`/api/simulations/${ctx.sim}`)).frame;
      const world = useSim.getState().world;
      const bridge = (world?.edges ?? []).find((e) => e.kind === "bridge" && before.edges[e.id] && !before.edges[e.id][2]);
      const effects: string[] = [];
      const shelter = ctx.shelter ?? [...before.shelters].sort((a: any, b: any) => b.reserved - a.reserved)[0]?.id;
      if (shelter) effects.push(...(await ev(ctx.sim, "SHELTER_CAPACITY", { shelter_id: shelter, capacity: "occupancy", reason: "overflow" })).event.effects);
      if (bridge) effects.push(...(await ev(ctx.sim, "CLOSE_EDGE", { edge_id: bridge.id, reason: "bridge collapse" })).event.effects);
      effects.push(...(await ev(ctx.sim, "RESOURCE_FAILURE", { resource_id: ctx.unit, reason: "engine failure" })).event.effects);
      await t.step(3);
      const f = (await api.get<any>(`/api/simulations/${ctx.sim}`)).frame;
      const inc = f.incidents.find((i: any) => i.id === ctx.incident);
      const now = inc?.status === "RESCUED" ? "already rescued" : inc?.assigned?.length ? `now handled by ${inc.assigned.join(", ")}` : "waiting for the next round";
      return {
        ok: f.metrics.invariant_violations === 0,
        lines: [...effects.map((e, i) => <span key={i} className="block">{e}</span>), `Three minutes later: ${ctx.incident} is ${now}; ${f.metrics.reassignments} reassignment(s), ${f.metrics.invariant_violations} safety violations.`],
      };
    },
  },
  {
    title: "The crew sees its updated mission",
    say: "The crew of the unit that took over sees its new mission on a phone. Every tap is checked, and updates made without signal are synced safely when signal returns.",
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
    say: "Ask the AI assistant why something happened. It answers only from the run's records, cites every claim, and can only suggest actions for a human to approve.",
    run: async (ctx) => {
      const q = ctx.incident ? `Why was ${ctx.incident} reassigned?` : "Status";
      const a = await api.post<any>(`/api/simulations/${ctx.sim}/ask`, { question: q });
      return { ok: !a.warnings.length, lines: [<b key="q">{q}</b>, a.answer, `${a.citations.length} citation(s), ${a.warnings.length} grounding warning(s), engine ${a.engine}.`] };
    },
  },
  {
    title: "Every claim is measured",
    say: "Every claim is measured over 10 paired runs with 95% confidence ranges (benchmarks run on the synthetic test city, Riverbend). On a healthy network a central optimiser is as good or better. When it fails, the agents keep rescuing people.",
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
          "Benchmarks use the synthetic Riverbend city with the same seeds for every approach.",
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
    const geos = await api.get<{ geographies: { id: string }[] }>("/api/geographies").catch(() => ({ geographies: [] }));
    const city: Ctx["city"] = geos.geographies.some((g) => g.id === "aluva") ? "aluva" : "riverbend";
    await createSim("normal", "decentralized", { seed: 7, boats: 7, ground_units: 6, ...(city === "aluva" ? { geography: "aluva" } : {}) });
    const sim = useSim.getState().sim!;
    const c: Ctx = { sim: sim.id, city };
    setCtx(c);
    setRunning(null);
    return c;
  };
  const runAll = async () => {
    const c = ctx && done === 0 ? ctx : await start();
    for (let i = 0; i < STEPS.length; i++) if (!(await runStep(i, c))) break;
  };

  return (
    <div className="space-y-4 p-3 sm:p-4">
      <section className="rounded-2xl bg-[#0b2530] px-6 py-8 text-white sm:px-8">
        <p className="text-[13px] font-semibold text-cyan-300">Guided demo · about 3 minutes</p>
        <h1 className="mt-2 max-w-4xl font-display text-[26px] leading-tight font-semibold tracking-tight sm:text-[34px]">RESQNET doesn't just find a rescue route. It keeps rescue decisions coordinated, safe and explainable when everything changes.</h1>
        <p className="mt-3 max-w-3xl text-cyan-50/75">Eight live steps. Each button runs the real system, and what you see under each step is what it actually returned.</p>
        <div className="mt-6 flex flex-wrap items-center gap-3">
          <Button variant="outline" size="lg" icon={<PlayCircle className="size-5" />} loading={running !== null} onClick={runAll} className="border-0">
            Run the whole demo
          </Button>
          <Button size="lg" variant="ghost" disabled={running !== null} onClick={start} className="text-white hover:bg-white/10">
            Restart
          </Button>
          <div className="flex items-center gap-3">
            <div className="h-1.5 w-40 overflow-hidden rounded-full bg-white/15">
              <div className="h-full bg-cyan-300 transition-all" style={{ width: `${(done / STEPS.length) * 100}%` }} />
            </div>
            <span className="text-sm text-cyan-50/75">{done}/{STEPS.length} steps done</span>
          </div>
        </div>
      </section>
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <ol className="space-y-2">
          {STEPS.map((s, i) => {
            const r = results[i];
            const can = !!ctx && running === null && (i === 0 || !!results[i - 1]);
            return (
              <li key={s.title} className={cx("panel p-4 transition", running === i && "ring-2 ring-brand/40", !r && !can && "opacity-75")}>
                <div className="flex items-start gap-3">
                  <div className="mt-0.5">{running === i ? <Loader2 className="size-5 animate-spin text-info" /> : r ? <CheckCircle2 className={cx("size-5", r.ok ? "text-ok" : "text-warn")} /> : <Circle className="size-5 text-faint" />}</div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-[15px] font-semibold">
                        {i + 1}. {s.title}
                      </div>
                      <Button size="sm" variant={can && !r ? "primary" : "outline"} icon={<Play className="size-3.5" />} disabled={!can} onClick={() => ctx && runStep(i, ctx)}>
                        {r ? "Run again" : "Run step"}
                      </Button>
                    </div>
                    <p className="mt-1 text-[13.5px] leading-relaxed text-ink-2">{s.say}</p>
                    {r && (
                      <div className="mt-3 space-y-1 rounded-lg border border-line bg-wash p-3 text-[12.5px] leading-relaxed">
                        <div className="label mb-1">What the system returned</div>
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
            <div className="panel flex h-64 flex-col items-center justify-center gap-3 p-6 text-center text-sm text-mute">
              <PlayCircle className="size-8 text-faint" />
              Press “Run the whole demo” and the live map appears here.
            </div>
          )}
        </div>
      </div>
      <p className="text-[12px] text-mute">Research simulation on real Aluva roads from OpenStreetMap; the flood and SOS messages are simulated (fixed seed, full fleet). Assumptions, such as the coordinator outage leaving peer communication intact, are listed on the <Link className="underline" to="/research">evidence page</Link>.</p>
    </div>
  );
}
