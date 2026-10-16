import { Link, NavLink, useLocation } from "react-router-dom";
import { Bot, ChevronDown, CircleAlert, CircleCheck, Info, Menu, Pause, Play, PlayCircle, RotateCcw, SkipForward, TriangleAlert, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useSim } from "../store/sim";
import { clock, STRATEGY_LABEL } from "../lib/format";
import { Button, cx, Modal, useDismiss } from "./ui";
import type { MapListing, Strategy } from "../types";

type NavItem = { to: string; label: string; desc?: string };
const PRIMARY: NavItem[] = [
  { to: "/live", label: "Live ops" },
  { to: "/command", label: "Live console" },
  { to: "/sos", label: "Citizen SOS" },
  { to: "/crew", label: "Crew app" },
];
const GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: "Labs",
    items: [
      { to: "/chaos", label: "Scenario & failure lab", desc: "Design a flood, then break bridges, boats and shelters" },
      { to: "/decision-lab", label: "What-if lab", desc: "Rewind, change one decision, compare two futures" },
      { to: "/judge", label: "Judge mode", desc: "A guided five-chapter story on the real map" },
      { to: "/agents", label: "Agent negotiation", desc: "Watch rescue units bid for every rescue" },
      { to: "/dispatch", label: "Rescue fleet", desc: "Every boat and team, and what it is doing" },
    ],
  },
  {
    label: "Results",
    items: [
      { to: "/arena", label: "Benchmarks", desc: "Agents vs a central control room, with statistics" },
      { to: "/safety", label: "Safety tests", desc: "Rules that can never be broken, and stress tests" },
      { to: "/audit", label: "Mission replay", desc: "Scrub through a run minute by minute" },
      { to: "/reports", label: "After-action report", desc: "What happened in this run and what it cost" },
      { to: "/research", label: "Evidence & docs", desc: "Requirements, tests, data sources and limits" },
    ],
  },
];

export function Logo() {
  return (
    <div className="flex items-center gap-2">
      <svg viewBox="0 0 32 32" className="size-7" aria-hidden>
        <rect width="32" height="32" rx="8" fill="#0a0a0a" />
        <path d="M6 20c3.3-4 6.7-4 10 0s6.7 4 10 0" stroke="#22d3ee" strokeWidth="2.6" fill="none" strokeLinecap="round" />
        <circle cx="16" cy="11" r="3.2" fill="#fff" />
      </svg>
      <span className="font-display text-[19px] font-semibold tracking-[-0.03em]">
        resqnet<span className="text-brand"> ai</span>
      </span>
    </div>
  );
}

const isActive = (path: string, to: string) => (to === "/" ? path === "/" : path === to || path.startsWith(to + "/"));

function NavGroup({ label, items }: { label: string; items: NavItem[] }) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  const ref = useDismiss<HTMLDivElement>(open, close);
  const loc = useLocation();
  useEffect(close, [loc.pathname, close]);
  const active = items.some((i) => isActive(loc.pathname, i.to));
  return (
    <div className="relative" ref={ref}>
      <button type="button" aria-expanded={open} aria-haspopup="menu" onClick={() => setOpen((o) => !o)} className={cx("flex items-center gap-1 rounded-lg px-3 py-2 text-[14px] font-medium transition", active ? "text-ink" : "text-ink-2 hover:bg-black/[0.04] hover:text-ink")}>
        {label}
        <ChevronDown className={cx("size-3.5 opacity-60 transition", open && "rotate-180")} />
        {active && <span className="absolute inset-x-3 -bottom-[9px] h-0.5 rounded-full bg-brand" />}
      </button>
      {open && (
        <div role="menu" className="panel fade-in absolute top-full left-0 z-40 mt-2 w-[340px] p-1.5">
          {items.map((i) => (
            <NavLink key={i.to} to={i.to} role="menuitem" className={cx("block rounded-lg px-3 py-2.5 transition", isActive(loc.pathname, i.to) ? "bg-brand-soft" : "hover:bg-black/[0.04]")}>
              <div className="text-sm font-medium text-ink">{i.label}</div>
              {i.desc && <div className="mt-0.5 text-[12.5px] text-mute">{i.desc}</div>}
            </NavLink>
          ))}
        </div>
      )}
    </div>
  );
}

export function TopBar() {
  const conn = useSim((s) => s.conn);
  const askOpen = useSim((s) => s.askOpen);
  const setAskOpen = useSim((s) => s.setAskOpen);
  const world = useSim((s) => s.world);
  const loc = useLocation();
  const [mobile, setMobile] = useState(false);
  useEffect(() => setMobile(false), [loc.pathname]);
  return (
    <div className="no-print sticky top-0 z-30">
      <div className="bg-[#0b2530] px-4 py-1 text-center text-[12px] text-cyan-50/85">
        Research simulation, not an emergency service. In a real emergency in India, call <b className="text-white">112</b>.
        {world?.map.real && <span className="hidden md:inline"> · {world.map.name}: real OpenStreetMap roads and Copernicus terrain; floods and incidents are simulated.</span>}
      </div>
      <header className="border-b border-line bg-white/90 backdrop-blur-md">
        <div className="mx-auto flex h-[60px] max-w-[1680px] items-center gap-2 px-4">
          <Link to="/" className="mr-3 shrink-0" aria-label="RESQNET AI home">
            <Logo />
          </Link>
          <nav aria-label="Main" className="hidden flex-1 items-center gap-0.5 lg:flex">
            {PRIMARY.map((n) => {
              const active = isActive(loc.pathname, n.to);
              return (
                <NavLink key={n.to} to={n.to} className={cx("relative rounded-lg px-3 py-2 text-[14px] font-medium transition", active ? "text-ink" : "text-ink-2 hover:bg-black/[0.04] hover:text-ink")}>
                  {n.label}
                  {active && <span className="absolute inset-x-3 -bottom-[9px] h-0.5 rounded-full bg-brand" />}
                </NavLink>
              );
            })}
            {GROUPS.map((g) => (
              <NavGroup key={g.label} {...g} />
            ))}
          </nav>
          <div className="ml-auto flex shrink-0 items-center gap-2">
            <span title={conn === "live" ? "Connected to the simulation engine" : `Engine ${conn}`} className={cx("hidden items-center gap-1.5 text-[12px] font-medium sm:inline-flex", conn === "live" ? "text-ok" : conn === "offline" ? "text-crit" : "text-warn")}>
              <span className={cx("size-2 rounded-full bg-current", conn !== "live" && "animate-pulse")} />
              {conn === "live" ? "Live" : conn === "offline" ? "Offline" : "Connecting"}
            </span>
            <Button size="sm" variant={askOpen ? "solid" : "outline"} icon={<Bot className="size-4" />} onClick={() => setAskOpen(!askOpen)} title="Ask the AI mission assistant about this run">
              <span className="hidden sm:inline">Ask AI</span>
            </Button>
            <Link to="/demo" className="hidden h-8 items-center gap-1.5 rounded-lg bg-brand px-3 text-[13px] font-medium text-white shadow-sm transition hover:bg-brand-2 sm:inline-flex">
              <PlayCircle className="size-4" /> Watch demo
            </Link>
            <button type="button" className="rounded-lg p-2 text-ink-2 hover:bg-black/5 lg:hidden" aria-label={mobile ? "Close menu" : "Open menu"} aria-expanded={mobile} onClick={() => setMobile((m) => !m)}>
              {mobile ? <X className="size-5" /> : <Menu className="size-5" />}
            </button>
          </div>
        </div>
        {mobile && (
          <nav aria-label="Mobile" className="fade-in max-h-[calc(100vh-90px)] overflow-y-auto border-t border-line bg-white px-4 pt-2 pb-5 lg:hidden">
            {[{ to: "/", label: "Home" }, { to: "/demo", label: "Watch demo" }, ...PRIMARY].map((n) => (
              <NavLink key={n.to} to={n.to} className={cx("block rounded-lg px-3 py-2.5 text-[15px] font-medium", isActive(loc.pathname, n.to) ? "bg-brand-soft text-ink" : "text-ink-2")}>
                {n.label}
              </NavLink>
            ))}
            {GROUPS.map((g) => (
              <div key={g.label} className="mt-3">
                <div className="label px-3 pb-1">{g.label}</div>
                {g.items.map((n) => (
                  <NavLink key={n.to} to={n.to} className={cx("block rounded-lg px-3 py-2 text-[15px]", isActive(loc.pathname, n.to) ? "bg-brand-soft text-ink" : "text-ink-2")}>
                    {n.label}
                  </NavLink>
                ))}
              </div>
            ))}
          </nav>
        )}
      </header>
    </div>
  );
}

export function Footer() {
  return (
    <footer className="no-print mt-10 border-t border-line bg-white">
      <div className="mx-auto grid max-w-[1200px] gap-8 px-5 py-10 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1fr]">
        <div>
          <Logo />
          <p className="mt-3 max-w-xs text-sm leading-relaxed text-mute">Flood-rescue coordination that stays safe and explainable when roads, boats, shelters and networks fail.</p>
        </div>
        {[
          { label: "Product", items: [{ to: "/demo", label: "Guided demo" }, ...PRIMARY] },
          GROUPS[0],
          GROUPS[1],
        ].map((g) => (
          <div key={g.label}>
            <div className="label mb-2">{g.label}</div>
            <ul className="space-y-1.5">
              {g.items.map((i) => (
                <li key={i.to}>
                  <Link to={i.to} className="text-sm text-ink-2 hover:text-brand">
                    {i.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="border-t border-line px-5 py-4 text-center text-[12.5px] text-mute">Research and education prototype. Floods, incidents and SOS messages are simulated. Map data © OpenStreetMap contributors where shown.</div>
    </footer>
  );
}

const SPEEDS = [0.5, 1, 2, 4, 8, 16];

export const SCENARIOS: { id: string; name: string; desc: string }[] = [
  { id: "kerala_2018", name: "Kerala 2018 flood replay", desc: "The river follows the real August 2018 flood; SOS arrivals follow the real rain. Best on a Kerala map." },
  { id: "normal", name: "Normal flood", desc: "The river rises steadily. A good first run." },
  { id: "triple_failure", name: "Triple failure", desc: "A bridge, a boat and a shelter fail at the same minute." },
  { id: "coordinator_outage", name: "Control room goes down", desc: "Central dispatch is offline for an hour." },
  { id: "contradictory", name: "Conflicting reports", desc: "Noisy, duplicated and false SOS messages." },
  { id: "viral_sos", name: "Forwarded SOS cascade", desc: "The same SOS is forwarded many times, plus rumours." },
  { id: "flash_flood", name: "Flash flood", desc: "Water rises three times faster than normal." },
  { id: "bridge_closure", name: "Bridge closure", desc: "A key bridge closes while units depend on it." },
  { id: "bridge_dependency", name: "Across the river", desc: "People on one bank, shelters on the other." },
  { id: "resource_shortage", name: "Too few units", desc: "Only 3 boats and 2 ground teams." },
  { id: "shelter_overflow", name: "Shelter overflow", desc: "A shelter loses most of its space." },
  { id: "network_partition", name: "Network split", desc: "Some units lose contact with the rest for 40 minutes." },
  { id: "lossy_network", name: "Bad radio network", desc: "Messages are delayed, lost or duplicated." },
];

export const STRATEGIES: { id: Strategy; name: string; desc: string }[] = [
  { id: "decentralized", name: "Multi-agent", desc: "Units and shelters negotiate rescues themselves. Recommended." },
  { id: "message_passing", name: "Agents over radio", desc: "Same, but every message travels over an unreliable network." },
  { id: "centralized", name: "Central optimiser", desc: "One optimiser assigns everything. The usual baseline." },
  { id: "greedy", name: "Nearest unit", desc: "Simple rule: send the closest free unit." },
];
export const strategyName = (s: string) => STRATEGY_LABEL[s] ?? s;

export function SimControls({ extra }: { extra?: React.ReactNode }) {
  const sim = useSim((s) => s.sim);
  const frame = useSim((s) => s.frame);
  const world = useSim((s) => s.world);
  const control = useSim((s) => s.control);
  const setSpeed = useSim((s) => s.setSpeed);
  const busy = useSim((s) => s.busy);
  if (!sim || !frame) return null;
  const running = sim.status === "running";
  const pctDone = Math.min(100, (frame.tick / sim.duration) * 100);
  const scen = SCENARIOS.find((x) => x.id === sim.scenario)?.name ?? sim.scenario_name;
  const status = running ? "Running" : frame.finished || sim.status === "finished" ? "Finished" : frame.tick === 0 ? "Ready" : "Paused";
  return (
    <div className="panel flex flex-wrap items-center gap-x-4 gap-y-3 px-3 py-2.5">
      <div className="flex items-center gap-1.5">
        {running ? (
          <Button variant="solid" icon={<Pause className="size-4" />} onClick={() => control("pause")} loading={busy.pause}>
            Pause
          </Button>
        ) : (
          <Button variant="primary" icon={<Play className="size-4" />} onClick={() => control("start")} disabled={frame.finished} loading={busy.start}>
            {frame.tick === 0 ? "Start" : "Resume"}
          </Button>
        )}
        <Button variant="ghost" icon={<SkipForward className="size-4" />} onClick={() => control("step", 1)} disabled={running || frame.finished} loading={busy.step} title="Advance one simulated minute" aria-label="Step">
          <span className="hidden sm:inline">Step</span>
        </Button>
        <Button variant="ghost" icon={<RotateCcw className="size-4" />} onClick={() => control("reset")} loading={busy.reset} title="Restart this run from the beginning" aria-label="Reset">
          <span className="hidden sm:inline">Reset</span>
        </Button>
      </div>
      <div className="flex min-w-[150px] items-center gap-3">
        <div>
          <div className="mono num text-[17px] leading-none font-semibold">{clock(frame.tick)}</div>
          <div className="mt-1 text-[11px] text-mute">
            minute {frame.tick} of {sim.duration}
          </div>
        </div>
        <div className="hidden h-1.5 w-24 overflow-hidden rounded-full bg-black/[0.07] sm:block" title={`${Math.round(pctDone)}% of the run`}>
          <div className="h-full bg-brand transition-all" style={{ width: `${pctDone}%` }} />
        </div>
      </div>
      <label className="flex items-center gap-1.5 text-[13px] text-mute">
        Speed
        <select aria-label="Speed" className="h-8 rounded-lg border border-line-2 bg-white px-2 text-[13px] text-ink" value={sim.speed} onChange={(e) => setSpeed(Number(e.target.value))}>
          {SPEEDS.map((s) => (
            <option key={s} value={s}>
              {s}×
            </option>
          ))}
        </select>
      </label>
      <div className="min-w-0 border-l border-line pl-4 max-md:border-0 max-md:pl-0">
        <div className="flex items-center gap-2 text-sm font-medium">
          <span className={cx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11.5px] font-semibold", running ? "bg-ok-soft text-ok" : status === "Finished" ? "bg-ink text-white" : "bg-black/[0.05] text-ink-2")}>
            {running && <span className="size-1.5 animate-pulse rounded-full bg-current" />}
            {status}
          </span>
          <span className="truncate">{scen}</span>
        </div>
        <div className="mt-0.5 truncate text-[12px] text-mute" title={`seed ${sim.seed} · state version ${frame.version}`}>
          {world?.name?.replace(" (synthetic)", "") ?? "City"} · {strategyName(sim.strategy)}
        </div>
      </div>
      <div className="ml-auto flex flex-wrap items-center gap-2">{extra}</div>
    </div>
  );
}

export function NewRunMenu() {
  const createSim = useSim((s) => s.createSim);
  const sim = useSim((s) => s.sim);
  const busy = useSim((s) => s.busy.create);
  const maps = useSim((s) => s.maps);
  const mapId = useSim((s) => s.mapId);
  const [open, setOpen] = useState(false);
  const [mapSel, setMapSel] = useState(mapId);
  useEffect(() => setMapSel(mapId), [mapId]);
  const [scenario, setScenario] = useState(sim?.scenario ?? "normal");
  const [strategy, setStrategy] = useState<Strategy>(sim?.strategy ?? "decentralized");
  const close = useCallback(() => setOpen(false), []);
  return (
    <>
      <Button size="sm" variant="solid" icon={<Play className="size-3.5" />} onClick={() => setOpen(true)}>
        New run
      </Button>
      <Modal
        open={open}
        onClose={close}
        title="Start a new run"
        sub="Pick a situation, a city and how rescue units are coordinated."
        width="max-w-3xl"
        footer={
          <>
            <Button variant="ghost" onClick={close}>
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={busy}
              onClick={async () => {
                await createSim(scenario, strategy, {}, mapSel).catch(() => {});
                try {
                  localStorage.setItem("resqnet.map", mapSel);
                } catch {
                  /* ignore */
                }
                setOpen(false);
              }}
            >
              Launch
            </Button>
          </>
        }
      >
        <div className="label mb-2">1 · Situation</div>
        <div className="grid gap-2 sm:grid-cols-2">
          {SCENARIOS.map((x) => (
            <button type="button" key={x.id} aria-pressed={scenario === x.id} onClick={() => setScenario(x.id)} className={cx("rounded-xl border px-3.5 py-2.5 text-left transition", scenario === x.id ? "border-brand bg-brand-soft ring-1 ring-brand" : "border-line-2 hover:border-ink/30")}>
              <div className="text-sm font-medium">{x.name}</div>
              <div className="mt-0.5 text-[12.5px] text-mute">{x.desc}</div>
            </button>
          ))}
        </div>
        <div className="label mt-5 mb-2">2 · City</div>
        <div className="grid gap-2 sm:grid-cols-2">
          {(maps.length ? maps : [{ id: "riverbend", name: "Riverbend (synthetic)", region: "", real: false, note: "" } as MapListing]).map((m) => (
            <button type="button" key={m.id} aria-pressed={mapSel === m.id} onClick={() => setMapSel(m.id)} className={cx("rounded-xl border px-3.5 py-2.5 text-left transition", mapSel === m.id ? "border-brand bg-brand-soft ring-1 ring-brand" : "border-line-2 hover:border-ink/30")}>
              <div className="text-sm font-medium">{m.name.replace(" (synthetic)", "")}</div>
              <div className="mt-0.5 text-[12.5px] text-mute">{m.real ? `Real roads, bridges and river${m.population ? ` · about ${Math.round(m.population / 1000)}k residents` : ""}` : "Made-up city for tests and benchmarks"}</div>
            </button>
          ))}
        </div>
        <div className="label mt-5 mb-2">3 · Coordination</div>
        <div className="grid gap-2 sm:grid-cols-2">
          {STRATEGIES.map((x) => (
            <button type="button" key={x.id} aria-pressed={strategy === x.id} onClick={() => setStrategy(x.id)} className={cx("rounded-xl border px-3.5 py-2.5 text-left transition", strategy === x.id ? "border-brand bg-brand-soft ring-1 ring-brand" : "border-line-2 hover:border-ink/30")}>
              <div className="text-sm font-medium">{x.name}</div>
              <div className="mt-0.5 text-[12.5px] text-mute">{x.desc}</div>
            </button>
          ))}
        </div>
      </Modal>
    </>
  );
}

export function Toasts() {
  const toasts = useSim((s) => s.toasts);
  const dismiss = useSim((s) => s.dismiss);
  return (
    <div className="no-print pointer-events-none fixed right-4 bottom-4 z-50 flex w-[380px] max-w-[calc(100vw-2rem)] flex-col gap-2" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className="panel fade-in pointer-events-auto flex gap-2.5 p-3">
          <div className="pt-0.5">
            {t.kind === "ok" ? <CircleCheck className="size-4 text-ok" /> : t.kind === "warn" ? <TriangleAlert className="size-4 text-warn" /> : t.kind === "crit" ? <CircleAlert className="size-4 text-crit" /> : <Info className="size-4 text-info" />}
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium first-letter:uppercase">{t.title}</div>
            {t.body && <div className="mt-0.5 text-xs leading-relaxed text-mute">{t.body}</div>}
          </div>
          <button aria-label="Dismiss" onClick={() => dismiss(t.id)} className="text-faint hover:text-ink">
            <X className="size-4" />
          </button>
        </div>
      ))}
    </div>
  );
}
