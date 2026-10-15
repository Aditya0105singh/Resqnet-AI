import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, Crosshair, Layers as LayersIcon, MapPinPlus, MousePointer2, Scissors } from "lucide-react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useSim, type Layers } from "../store/sim";
import { CityMap, MapLegend } from "../components/CityMap";
import { ChaosMenu } from "../components/Chaos";
import { ActivityFeed } from "../components/Feed";
import { SelectionPanel } from "../components/SelectionPanel";
import { Approvals } from "../components/Approvals";
import { DisruptionCard } from "../components/DisruptionCard";
import { NewRunMenu, SimControls } from "../components/Shell";
import { Badge, Button, cx, Empty, inputCls, Panel, Segmented, Spinner, Stat } from "../components/ui";
import { clock, fmt, INCIDENT_TONE, isOpen, pct, statusLabel } from "../lib/format";

export default function Command() {
  const { world, frame, sim, layers, selection, setSelection, toggleLayer, inject, audit } = useSim();
  const [mode, setMode] = useState<"select" | "close-edge" | "new-incident">("select");
  const [filter, setFilter] = useState<"open" | "urgent" | "uncovered" | "all">("open");
  const [tab, setTab] = useState<"detail" | "feed" | "approvals">("feed");
  const [sos, setSos] = useState({ people: 4, urgency: 4 });
  const [showLayers, setShowLayers] = useState(false);
  const [moreKpis, setMoreKpis] = useState(false);
  const [mobileTab, setMobileTab] = useState<"map" | "requests" | "activity">("map");

  const incidents = useMemo(() => {
    if (!frame) return [];
    let xs = frame.incidents;
    if (filter === "open") xs = xs.filter(isOpen);
    if (filter === "urgent") xs = xs.filter((i) => isOpen(i) && i.urgency >= 4);
    if (filter === "uncovered") xs = xs.filter((i) => isOpen(i) && i.unassigned > 0);
    return [...xs].sort((a, b) => b.urgency - a.urgency || a.deadline - b.deadline);
  }, [frame, filter]);

  if (!world || !frame || !sim) return <Spinner label="Connecting to the simulation engine…" />;
  const pendingCount = (frame.proposals ?? []).filter((p) => p.status === "PENDING").length;
  const m = frame.metrics;

  return (
    <div className="flex flex-col gap-3 p-3 lg:h-[calc(100vh-88px)] lg:min-h-[720px]">
      <SimControls
        extra={
          <>
            <ChaosMenu />
            <NewRunMenu />
          </>
        }
      />
      <GettingStarted />
      <div className="lg:hidden">
        <Segmented
          value={mobileTab}
          onChange={setMobileTab}
          options={[
            { value: "map", label: "Map" },
            { value: "requests", label: `Requests · ${m.open_incidents}` },
            { value: "activity", label: pendingCount ? `Activity · ${pendingCount} to approve` : "Activity" },
          ]}
        />
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 lg:grid-cols-[300px_1fr_360px]">
        {/* incident queue */}
        <Panel
          title="rescue requests"
          sub={`${m.open_incidents} open · ${frame.incidents.filter((i) => isOpen(i) && i.unassigned > 0).length} still need a unit`}
          right={<Badge tone="neutral">{incidents.length}</Badge>}
          bodyClass="flex flex-col"
          className={cx("max-lg:h-[70vh]", mobileTab !== "requests" && "max-lg:hidden")}
        >
          <div className="border-b border-line px-3 py-2">
            <Segmented size="sm" value={filter} onChange={setFilter} options={[{ value: "open", label: "Open" }, { value: "urgent", label: "Urgent" }, { value: "uncovered", label: "No unit yet" }, { value: "all", label: "All" }]} />
          </div>
          <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
            {incidents.length === 0 ? (
              <Empty title="Nothing in this filter" />
            ) : (
              incidents.map((i) => {
                const late = isOpen(i) && i.first_pickup_tick === null && frame.tick > i.deadline;
                return (
                  <button
                    key={i.id}
                    onClick={() => {
                      setSelection({ type: "incident", id: i.id });
                      setTab("detail");
                    }}
                    title={`Location ${i.node} · report confidence ${fmt(i.confidence, 2)} · urgency ${i.urgency} of 5`}
                    className={cx("flex w-full items-start gap-3 border-b border-line/70 px-3.5 py-2.5 text-left hover:bg-wash", selection?.type === "incident" && selection.id === i.id && "bg-brand-soft")}
                  >
                    <span aria-label={`urgency ${i.urgency} of 5`} className="mono mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg text-[12px] font-semibold text-white" style={{ background: i.urgency >= 5 ? "#dc2626" : i.urgency >= 4 ? "#d97706" : i.urgency >= 3 ? "#0891b2" : "#a1a1aa" }}>
                      {i.urgency}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="mono text-[12.5px] font-semibold">{i.id}</span>
                        <Badge tone={INCIDENT_TONE[i.status]}>{statusLabel(i.status)}</Badge>
                        {late && <Badge tone="crit">late</Badge>}
                      </div>
                      <div className="mt-0.5 truncate text-[12.5px] text-ink-2">
                        {i.people} waiting{i.unassigned ? (i.unassigned >= i.people ? " · no unit yet" : ` · ${i.unassigned} not covered`) : ""}
                      </div>
                      {i.assigned.length > 0 && <div className="mt-0.5 text-[12px] text-brand">Unit {i.assigned.join(", ")} on the way</div>}
                    </div>
                    <span className={cx("shrink-0 text-[11px]", late ? "font-medium text-crit" : "text-mute")} title="Rescue deadline">
                      by {clock(i.deadline).slice(2)}
                    </span>
                  </button>
                );
              })
            )}
          </div>
        </Panel>

        {/* map */}
        <section className={cx("panel relative min-h-[420px] overflow-hidden", mobileTab !== "map" && "max-lg:hidden")}>
          <div className="absolute top-3 left-3 z-10 flex flex-wrap items-center gap-1.5">
            <div className="inline-flex rounded-full border border-line-2 bg-white/95 p-0.5 shadow-sm backdrop-blur">
              {(
                [
                  ["select", <MousePointer2 key="a" className="size-3.5" />, "Inspect"],
                  ["close-edge", <Scissors key="b" className="size-3.5" />, "Close road"],
                  ["new-incident", <MapPinPlus key="c" className="size-3.5" />, "Add SOS"],
                ] as const
              ).map(([k, icon, l]) => (
                <button key={k} onClick={() => setMode(k)} className={cx("flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium", mode === k ? "bg-ink text-white" : "text-ink-2 hover:bg-black/5")}>
                  {icon}
                  {l}
                </button>
              ))}
            </div>
            <Button size="sm" icon={<LayersIcon className="size-3.5" />} onClick={() => setShowLayers((v) => !v)} className="bg-white/95">
              Layers
            </Button>
            {mode === "new-incident" && (
              <div className="flex items-center gap-1 rounded-full border border-line-2 bg-white/95 px-2 py-0.5 text-xs shadow-sm">
                <Crosshair className="size-3.5 text-info" />
                people
                <input className={cx(inputCls, "h-6 w-12 px-1 text-xs")} type="number" min={1} max={40} value={sos.people} onChange={(e) => setSos({ ...sos, people: Number(e.target.value) })} />
                urgency
                <input className={cx(inputCls, "h-6 w-10 px-1 text-xs")} type="number" min={1} max={5} value={sos.urgency} onChange={(e) => setSos({ ...sos, urgency: Number(e.target.value) })} />
              </div>
            )}
          </div>
          {showLayers && (
            <div className="panel fade-in absolute top-12 left-3 z-10 grid w-56 grid-cols-2 gap-1 p-2">
              {(Object.keys(layers) as (keyof Layers)[]).map((k) => (
                <label key={k} className="flex items-center gap-1.5 rounded px-1.5 py-1 text-xs capitalize hover:bg-wash">
                  <input type="checkbox" checked={layers[k]} onChange={() => toggleLayer(k)} />
                  {k}
                </label>
              ))}
            </div>
          )}
          <div className="absolute top-[4.5rem] right-3 z-20">
            <DisruptionCard
              onInspect={(id) => {
                setSelection({ type: "incident", id });
                setTab("detail");
              }}
            />
          </div>
          <div className="absolute top-3 right-3 z-10 rounded-xl border border-line-2 bg-white/90 px-3 py-1.5 text-right shadow-sm backdrop-blur">
            <div className="label">river level</div>
            <div className="mono num text-sm font-semibold">{frame.river_level} m</div>
          </div>
          <CityMap
            world={world}
            frame={frame}
            layers={layers}
            selection={selection}
            mode={mode}
            transitionMs={Math.max(80, 1000 / (sim.speed || 1))}
            onSelect={(s) => {
              setSelection(s);
              setTab("detail");
              setMobileTab("activity");
            }}
            onEdgeClick={(id) => {
              const st = frame.edges[id];
              inject(st?.[2] ? "OPEN_EDGE" : "CLOSE_EDGE", { edge_id: id, reason: "operator closure" }, st?.[2] ? `${id} reopened` : `${id} closed`);
            }}
            onNodeClick={(node) => inject("NEW_INCIDENT", { node, people: sos.people, urgency: sos.urgency, source: "responder" }, `SOS at ${node}`)}
          />
          <div className="absolute bottom-3 left-3 z-10 hidden rounded-xl border border-line bg-white/90 px-3 py-1.5 backdrop-blur sm:block">
            <MapLegend />
          </div>
        </section>

        {/* right column */}
        <Panel
          className={cx("max-lg:h-[70vh]", mobileTab !== "activity" && "max-lg:hidden")}
          title={
            <Segmented
              size="sm"
              value={tab}
              onChange={setTab}
              options={[
                { value: "feed", label: "Activity" },
                { value: "detail", label: "Details" },
                { value: "approvals", label: pendingCount ? `Approvals · ${pendingCount}` : "Approvals" },
              ]}
            />
          }
          right={<span className="text-[11.5px] text-mute">{audit.length} events</span>}
          bodyClass="flex flex-col"
        >
          <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">{tab === "feed" ? <ActivityFeed /> : tab === "approvals" ? <Approvals /> : <SelectionPanel />}</div>
        </Panel>
      </div>

      {/* key numbers */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-[repeat(4,1fr)_1.5fr_auto]">
        <Kpi info="People delivered safely to a shelter so far." label="people rescued" value={m.people_rescued} hint={`${m.people_in_transit} on the way to shelter`} tone="ok" />
        <Kpi info="Everyone not yet at a shelter: people still waiting (including some not reported yet) plus people on board a boat or truck." label="not yet safe" value={m.unmet_people} hint={m.people_in_transit ? `${m.people_in_transit} on board · incl. not yet reported` : "incl. people not yet reported"} tone={m.unmet_people > 20 ? "warn" : undefined} />
        <Kpi info="Average minutes from a request being reported to the first unit picking people up." label="avg. time to reach people" value={fmt(m.mean_time_to_service)} unit="min" hint={`${m.deadline_misses} of ${m.urgent_incidents} urgent missed deadline`} tone={m.deadline_misses ? "crit" : undefined} />
        <Kpi info="Times any of the 7 safety rules was broken, e.g. a unit sent to two places or a shelter overfilled. It should always be 0." label="safety rules broken" value={m.route_violations + m.invariant_violations} hint={`${m.safety_rejections} unsafe plans blocked`} tone={m.route_violations + m.invariant_violations ? "crit" : "ok"} />
        <MiniChart />
        <button type="button" aria-expanded={moreKpis} onClick={() => setMoreKpis((v) => !v)} className="panel col-span-2 flex items-center justify-center gap-1 px-4 py-3 text-[13px] font-medium text-ink-2 hover:text-ink md:col-span-4 xl:col-span-1">
          {moreKpis ? "Fewer" : "More"} numbers <ChevronDown className={cx("size-4 transition", moreKpis && "rotate-180")} />
        </button>
        {moreKpis && (
          <div className="panel fade-in col-span-full grid grid-cols-2 gap-x-6 gap-y-4 px-4 py-3.5 md:grid-cols-5">
            <Stat info="Share of time units spent on missions." label="units busy" value={pct(m.utilisation)} hint={`${m.idle_with_demand_ticks} idle minutes while people waited`} />
            <Stat info="How evenly waiting time is shared between areas: 1.0 means every area waits equally; lower means some areas wait longer." label="fairness" value={fmt(m.fairness_jain, 2)} hint="1.0 = every area waits equally" tone="info" />
            <Stat info="Times a unit had to change its path, for example because a road flooded or a bridge closed." label="route changes" value={m.reroutes} hint="units re-planned their path" />
            <Stat info="Rescues handed to a different unit after a failure." label="reassignments" value={m.reassignments} hint={`${m.cancellations} missions cancelled`} />
            <Stat info="Times a unit reached a closed road and was stopped by the safety check before entering it." label="blocked moves" value={m.blocked_moves} hint="stopped at a closed road" />
          </div>
        )}
      </div>
    </div>
  );
}

function Kpi(props: { label: string; value: React.ReactNode; unit?: string; hint?: string; tone?: "crit" | "warn" | "ok" | "info"; info?: string }) {
  return (
    <div className="panel px-3.5 py-3">
      <Stat {...props} />
    </div>
  );
}

function MiniChart() {
  const frame = useSim((s) => s.frame);
  const [series, setSeries] = useState<{ tick: number; rescued: number; waiting: number }[]>([]);
  useEffect(() => {
    if (!frame) return;
    setSeries((prev) => {
      const base = prev.length && frame.tick < prev[prev.length - 1].tick ? [] : prev.filter((p) => p.tick !== frame.tick);
      return [...base, { tick: frame.tick, rescued: frame.metrics.people_rescued, waiting: frame.metrics.unmet_people }].slice(-400);
    });
  }, [frame]);
  return (
    <div className="panel col-span-2 px-3 pt-2 md:col-span-4 xl:col-span-1">
      <div className="label">rescued vs waiting over time</div>
      <div className="h-[52px]">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={series} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
            <XAxis dataKey="tick" hide />
            <YAxis hide />
            <Tooltip contentStyle={{ fontSize: 11, borderRadius: 8 }} labelFormatter={(t) => `minute ${t}`} />
            <Area type="monotone" dataKey="waiting" stroke="#d97706" fill="#fef3c7" strokeWidth={1.5} isAnimationActive={false} />
            <Area type="monotone" dataKey="rescued" stroke="#15803d" fill="#dcfce7" strokeWidth={1.5} isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

const GUIDE_KEY = "resqnet.guide.dismissed";

/** First-visit tips for the console; dismissed once per browser. */
function GettingStarted() {
  const [hidden, setHidden] = useState(() => {
    try {
      return localStorage.getItem(GUIDE_KEY) === "1";
    } catch {
      return false;
    }
  });
  if (hidden) return null;
  const close = () => {
    setHidden(true);
    try {
      localStorage.setItem(GUIDE_KEY, "1");
    } catch {
      /* storage unavailable */
    }
  };
  const steps = [
    ["Press Start", "The flood rises and rescue units start negotiating who goes where."],
    ["Simulate a failure", "Break a bridge, a boat or a shelter (top right) and watch the plan repair itself."],
    ["Click anything", "A request, unit or road shows its details and why each decision was made."],
    ["Ask AI", "Ask “why was this reassigned?” and get an answer that cites the records."],
  ];
  return (
    <div className="panel fade-in flex flex-col gap-3 border-brand/25 bg-brand-soft/40 px-4 py-3 md:flex-row md:items-center">
      <div className="shrink-0 text-sm font-semibold text-brand">New here? Four things to try</div>
      <ol className="grid flex-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {steps.map(([t, d], i) => (
          <li key={t} className="flex gap-2 text-[12.5px] leading-snug">
            <span className="grid size-5 shrink-0 place-items-center rounded-full bg-brand text-[11px] font-semibold text-white">{i + 1}</span>
            <span>
              <b className="font-medium text-ink">{t}.</b> <span className="text-ink-2">{d}</span>
            </span>
          </li>
        ))}
      </ol>
      <div className="flex shrink-0 items-center gap-2">
        <Link to="/demo" className="text-[13px] font-medium text-brand hover:underline">
          Or watch the guided demo
        </Link>
        <Button size="sm" variant="ghost" onClick={close} aria-label="Hide these tips">
          Got it
        </Button>
      </div>
    </div>
  );
}
