import { useEffect, useMemo, useState } from "react";
import { BadgeCheck, ChevronLeft, ChevronRight, Pause, Play, RefreshCw } from "lucide-react";
import { api } from "../lib/api";
import { useSim } from "../store/sim";
import { CityMap } from "../components/CityMap";
import { Badge, Button, cx, Empty, PageHeader, Panel, Segmented, Spinner } from "../components/ui";
import { clock, fmt } from "../lib/format";
import type { AuditRecord, Decision, Frame } from "../types";

const CATS = ["event", "assignment", "cancel", "reroute", "shelter", "safety", "incident"];

export default function Replay() {
  const { sim, world, openDecision } = useSim();
  const [frames, setFrames] = useState<Record<number, Frame>>({});
  const [ticks, setTicks] = useState<number[]>([]);
  const [hashes, setHashes] = useState<Record<number, string>>({});
  const [audit, setAudit] = useState<AuditRecord[]>([]);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(4);
  const [cats, setCats] = useState<string[]>(["event", "cancel", "reroute", "shelter", "safety"]);
  const [verify, setVerify] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    if (!sim) return;
    setLoading(true);
    try {
      const [f, a, d] = await Promise.all([
        api.get<{ ticks: number[]; frames: Frame[]; hashes: Record<number, string> }>(`/api/simulations/${sim.id}/frames`),
        api.get<{ audit: AuditRecord[] }>(`/api/simulations/${sim.id}/audit?limit=5000`),
        api.get<{ decisions: Decision[] }>(`/api/simulations/${sim.id}/decisions?limit=2000`),
      ]);
      const map: Record<number, Frame> = {};
      f.ticks.forEach((tk, i) => (map[tk] = f.frames[i]));
      setFrames(map);
      setTicks(f.ticks);
      setHashes(f.hashes);
      setAudit(a.audit);
      setDecisions(d.decisions);
      setT((cur) => (cur && f.ticks.includes(cur) ? cur : f.ticks[f.ticks.length - 1] ?? 0));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    load();
  }, [sim?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!playing) return;
    const max = ticks[ticks.length - 1] ?? 0;
    const id = setInterval(() => setT((x) => (x >= max ? (setPlaying(false), x) : x + 1)), 1000 / speed);
    return () => clearInterval(id);
  }, [playing, speed, ticks]);

  const f = frames[t];
  const prev = frames[t - 1];
  const max = ticks[ticks.length - 1] ?? 0;
  const marks = useMemo(() => audit.filter((a) => a.severity === "critical" && a.category === "event"), [audit]);
  const rows = useMemo(() => audit.filter((a) => cats.includes(a.category)), [audit, cats]);
  const atTick = useMemo(() => audit.filter((a) => a.tick === t), [audit, t]);
  const decAtTick = useMemo(() => decisions.filter((d) => d.tick === t), [decisions, t]);
  const diff = useMemo(() => {
    if (!f || !prev) return { added: [], changed: [] as { id: string; from: string; to: string; reason: string }[] };
    const pm = Object.fromEntries(prev.assignments.map((a) => [a.id, a]));
    const added = f.assignments.filter((a) => !pm[a.id]);
    const changed = f.assignments.filter((a) => pm[a.id] && (pm[a.id].status !== a.status || pm[a.id].shelter_id !== a.shelter_id || pm[a.id].reroutes !== a.reroutes)).map((a) => ({ id: a.id, from: `${pm[a.id].status}/${pm[a.id].shelter_id}/r${pm[a.id].reroutes}`, to: `${a.status}/${a.shelter_id}/r${a.reroutes}`, reason: a.cancel_reason }));
    return { added, changed };
  }, [f, prev]);

  if (!sim || !world) return <Spinner />;
  return (
    <div className="space-y-3 p-3">
      <PageHeader
        eyebrow="mission replay & decision audit"
        title="Scrub through what actually happened"
        sub="Frames are the engine's own recorded state per tick. Verification rebuilds the whole run from (scenario, seed, strategy, injected-event log) and compares state hashes tick by tick."
        right={
          <>
            <Button size="sm" icon={<RefreshCw className="size-3.5" />} loading={loading} onClick={load}>
              Reload history
            </Button>
            <Button
              size="sm"
              variant="solid"
              icon={<BadgeCheck className="size-3.5" />}
              onClick={async () => {
                setVerify({ running: true });
                setVerify(await api.get<any>(`/api/simulations/${sim.id}/replay/verify`).catch((e) => ({ error: e.message })));
              }}
              loading={verify?.running}
            >
              Verify deterministic replay
            </Button>
          </>
        }
      />
      {verify && !verify.running && (
        <div className={cx("panel fade-in flex flex-wrap items-center gap-3 px-4 py-3 text-sm", verify.identical ? "border-ok/30" : "border-crit/30")}>
          {verify.error ? (
            <span className="text-crit">{verify.error}</span>
          ) : (
            <>
              <Badge tone={verify.identical ? "ok" : "crit"} dot>
                {verify.identical ? "identical" : "mismatch"}
              </Badge>
              <span>
                Rebuilt {verify.ticks_compared} ticks from the event log in {verify.elapsed_ms} ms — {verify.identical ? "every state hash matches." : `mismatching ticks: ${verify.mismatches.join(", ")}`}
              </span>
              <span className="mono ml-auto text-xs text-mute">
                final {verify.final_hash} / replay {verify.replay_final_hash}
              </span>
            </>
          )}
        </div>
      )}
      {ticks.length === 0 ? (
        <Panel title="replay">
          <Empty title="No recorded history" body="Run the simulation for a few ticks, then reload history." />
        </Panel>
      ) : (
        <>
          <div className="panel px-4 py-3">
            <div className="flex flex-wrap items-center gap-3">
              <Button size="sm" variant="ghost" icon={<ChevronLeft className="size-4" />} onClick={() => setT((x) => Math.max(0, x - 1))} />
              <Button size="sm" variant="solid" icon={playing ? <Pause className="size-3.5" /> : <Play className="size-3.5" />} onClick={() => (t >= max ? (setT(0), setPlaying(true)) : setPlaying(!playing))}>
                {playing ? "Pause" : "Play"}
              </Button>
              <Button size="sm" variant="ghost" icon={<ChevronRight className="size-4" />} onClick={() => setT((x) => Math.min(max, x + 1))} />
              <Segmented size="sm" value={speed} onChange={setSpeed} options={[1, 4, 10, 25].map((s) => ({ value: s, label: `${s}×` }))} />
              <span className="mono text-sm font-semibold">{clock(t)}</span>
              <span className="mono text-xs text-mute">
                t={t}/{max} · state v{f?.version} · hash {hashes[t]}
              </span>
            </div>
            <div className="relative mt-3">
              <input type="range" className="w-full accent-[#0a0a0a]" min={0} max={max} value={t} onChange={(e) => { setPlaying(false); setT(Number(e.target.value)); }} />
              <div className="pointer-events-none absolute inset-x-0 -top-1 h-2">
                {marks.map((m) => (
                  <span key={m.id} title={m.message} className="absolute h-2 w-0.5 rounded bg-crit" style={{ left: `${(m.tick / Math.max(1, max)) * 100}%` }} />
                ))}
              </div>
            </div>
          </div>
          <div className="grid gap-3 xl:grid-cols-[1fr_420px]">
            <Panel title={`world state at t=${t}`} sub={f ? `${f.metrics.people_rescued} rescued · ${f.metrics.unmet_people} waiting · ${f.metrics.active_assignments} active commitments` : undefined}>
              <div className="h-[520px]">{f && <CityMap world={world} frame={f} transitionMs={playing ? 1000 / speed : 0} />}</div>
            </Panel>
            <div className="space-y-3">
              <Panel title={`changes at t=${t}`} sub="Before/after against t−1">
                <div className="scroll-thin max-h-[250px] space-y-1 overflow-y-auto p-3 text-xs">
                  {diff.added.length === 0 && diff.changed.length === 0 && atTick.length === 0 && <div className="text-mute">No state transitions recorded at this tick.</div>}
                  {diff.added.map((a) => (
                    <div key={a.id} className="flex items-center gap-1.5">
                      <Badge tone="ok">new</Badge>
                      <span className="mono">{a.id}</span> {a.resource_id} → {a.incident_id} → {a.shelter_id}
                      <button className="ml-auto text-info hover:underline" onClick={() => openDecision(a.decision_id)}>
                        why?
                      </button>
                    </div>
                  ))}
                  {diff.changed.map((c) => (
                    <div key={c.id}>
                      <Badge tone="warn">changed</Badge> <span className="mono">{c.id}</span> <span className="mono text-mute">{c.from} → {c.to}</span>
                      {c.reason && <div className="pl-2 text-crit">{c.reason}</div>}
                    </div>
                  ))}
                  {decAtTick.map((d) => (
                    <button key={d.id} onClick={() => openDecision(d.id)} className="mono block text-left text-[11px] text-info hover:underline">
                      {d.id} · {d.incident_id} · {d.outcome.toLowerCase()}
                    </button>
                  ))}
                </div>
              </Panel>
              <Panel title="event log" right={<span className="mono text-[10.5px] text-faint">{rows.length}</span>}>
                <div className="flex flex-wrap gap-1 border-b border-line px-3 py-2">
                  {CATS.map((c) => (
                    <button key={c} onClick={() => setCats((x) => (x.includes(c) ? x.filter((y) => y !== c) : [...x, c]))} className={cx("mono rounded-full px-2 py-0.5 text-[10.5px] uppercase", cats.includes(c) ? "bg-ink text-white" : "text-mute hover:bg-black/5")}>
                      {c}
                    </button>
                  ))}
                </div>
                <div className="scroll-thin max-h-[300px] overflow-y-auto">
                  {rows.map((a) => (
                    <button key={a.id} onClick={() => { setPlaying(false); setT(a.tick); }} className={cx("flex w-full gap-2 border-b border-line/50 px-3 py-1.5 text-left text-[12px] hover:bg-wash", a.tick === t && "bg-info-soft/50")}>
                      <span className="mono w-10 shrink-0 text-faint">t={a.tick}</span>
                      <span className={cx(a.severity === "critical" ? "text-crit" : a.severity === "ok" ? "text-ok" : "text-ink-2")}>{a.message}</span>
                    </button>
                  ))}
                </div>
              </Panel>
            </div>
          </div>
          {f && (
            <div className="grid grid-cols-2 gap-3 md:grid-cols-6">
              {[
                ["rescued", f.metrics.people_rescued],
                ["waiting", f.metrics.unmet_people],
                ["mean tts", fmt(f.metrics.mean_time_to_service)],
                ["misses", f.metrics.deadline_misses],
                ["reroutes", f.metrics.reroutes],
                ["fairness", fmt(f.metrics.fairness_jain, 2)],
              ].map(([k, v]) => (
                <div key={k as string} className="panel px-3 py-2">
                  <div className="label">{k}</div>
                  <div className="mono num mt-0.5 text-lg font-semibold">{v}</div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
