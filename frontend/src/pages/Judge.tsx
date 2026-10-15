import { useState } from "react";
import { Link } from "react-router-dom";
import { useSim } from "../store/sim";
import { CityMap } from "../components/CityMap";
import { Button } from "../components/ui";

export default function Judge() {
  const { world, frame, sim, createSim, control, inject, openDecision } = useSim();
  const [working, setWorking] = useState(false);
  const [note, setNote] = useState("Choose a live experiment. Each action runs the actual simulation.");
  const act = async (work: () => Promise<void>) => {
    setWorking(true);
    try { await work(); } catch (e) { setNote((e as Error).message); }
    finally { setWorking(false); }
  };
  const start = (scenario: string) => act(async () => {
    if (sim?.status === "running") await control("pause");
    await createSim(scenario, "decentralized", {seed: 7});
    setNote("Run created with seed 7. Advance the clock to watch real assignments develop.");
  });
  const failBridge = () => act(async () => {
    if (!world) return;
    if (sim?.status === "running") await control("pause");
    const current = useSim.getState().frame;
    if (!current) return;
    const counts = world.edges.filter(e => e.kind === "bridge" && !current.edges[e.id]?.[2]).map(e => ({
      edge: e, count: current.resources.filter(r => {
        const path = [r.node, ...r.route];
        return r.assignment_id && path.some((n, i) => i > 0 && ((path[i-1] === e.u && n === e.v) || (path[i-1] === e.v && n === e.u)));
      }).length,
    })).sort((a,b) => b.count-a.count || a.edge.id.localeCompare(b.edge.id));
    const target = counts[0];
    if (!target?.count) { setNote("No active route crosses an open bridge yet. Advance five minutes and try again; no failure was injected."); return; }
    if (await inject("TRIPLE_FAILURE", {edge_id: target.edge.id}))
      setNote(`${target.edge.name}: ${target.count} active route(s) affected before injection. Rose dashed lines preserve the old routes for 15 simulated minutes; coloured lines show current plans. Inspect the decision or compare a different future.`);
  });
  return <div className="space-y-4 p-4">
    <section className="rounded-2xl bg-slate-950 p-6 text-white">
      <p className="text-xs uppercase tracking-[0.25em] text-cyan-300">RESQNET / live demonstration</p>
      <h1 className="my-3 text-3xl font-semibold">When the rescue plan breaks, who keeps coordinating?</h1>
      <p className="max-w-3xl text-slate-300">Test a bridge-dependent rescue mission, inspect the decisions, then measure what happens when central dispatch becomes unavailable.</p>
      <div className="mt-4 flex flex-wrap gap-3">
        <Button disabled={working} onClick={() => start("bridge_dependency")}>1. Start bridge mission</Button>
        <Button disabled={working || !frame || sim?.status === "running" || frame.finished} onClick={() => act(async () => { await control("step", 5); })}>2. Advance 5 minutes</Button>
        <Button disabled={working || !frame || frame.finished} onClick={failBridge}>3. Trigger live triple failure</Button>
        <Button disabled={working || !frame?.assignments.length} onClick={() => {
          const a = frame?.assignments[frame.assignments.length-1];
          if (a) openDecision(a.decision_id);
        }}>4. Explain a decision</Button>
      </div>
    </section>
    <p role="status" className="rounded-xl border border-cyan-200 bg-cyan-50 p-4 text-sm">{working ? "Running the live engine…" : note}</p>
    {world && frame && <>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {[ ["Mission minute", frame.tick], ["People rescued", frame.metrics.people_rescued], ["Active assignments", frame.assignments.filter(a => a.status === "COMMITTED" || a.status === "LOADED").length], ["Central dispatch", frame.coordinator?.available === false ? `Offline until ${frame.coordinator.restores_at}` : "Available"] ].map(([label,value]) =>
          <div key={label} className="panel p-4"><div className="text-xs text-mute">{label}</div><div className="mt-1 text-2xl font-semibold">{value}</div></div>)}
      </div>
      <div className="panel h-[55vh] min-h-[320px]"><CityMap world={world} frame={frame} /></div>
    </>}
    <div className="panel flex flex-wrap items-center gap-4 p-4">
      <Link className="underline" to="/decision-lab">5. Compare a what-if future</Link>
      <Button disabled={working} onClick={() => start("coordinator_outage")}>6. Load coordinator outage</Button>
      <Link className="underline" to="/arena">7. Measure all strategies in Arena</Link>
      <Link className="underline" to="/reports">Export evidence</Link>
    </div>
    <p className="text-sm text-mute">Outage assumption: central and greedy dispatch have no standby coordinator; peer communication and local safety stay available. Existing missions continue. Compare normal-operation results too. This experiment does not establish superiority under every failure model.</p>
  </div>;
}
