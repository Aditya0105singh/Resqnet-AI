import { useMemo, useState } from "react";
import { useSim } from "../store/sim";
import type { AuditRecord, StaticWorld } from "../types";
import { clock } from "../lib/format";
import { cx, Empty } from "./ui";

const SEV: Record<string, string> = { info: "bg-faint", warn: "bg-warn", critical: "bg-crit", ok: "bg-ok" };
const CATS: [string, string][] = [
  ["all", "All"],
  ["assignment", "Missions"],
  ["event", "Events"],
  ["cancel", "Cancelled"],
  ["reroute", "Route changes"],
  ["shelter", "Shelters"],
  ["safety", "Safety"],
  ["incident", "Requests"],
];
const CAT_LABEL: Record<string, string> = { event: "Event", assignment: "Mission", cancel: "Cancelled", reroute: "Route change", shelter: "Shelter", safety: "Safety", incident: "Request" };

type Row = AuditRecord & { count?: number; areas?: string[] };

/** Plain-language wording for engine records: road ids become road or area names, node ids become
 * area names. The underlying audit record is unchanged (and still shown on hover). */
export function useHumanizer(world: StaticWorld | null) {
  return useMemo(() => {
    if (!world) return (m: string) => m;
    const nb = Object.fromEntries(world.neighbourhoods.map((z) => [z.id, z.name.replace(" (synthetic)", "")]));
    const nodeArea = Object.fromEntries(world.nodes.map((n) => [n.id, nb[n.neighbourhood] ?? n.neighbourhood]));
    const edge = Object.fromEntries(world.edges.map((e) => [e.id, e.name || `a road in ${nodeArea[e.u] ?? "town"}`]));
    return (m: string) =>
      m
        .replace(/\bE-(N\d+)-(N\d+)\b/g, (id) => edge[id] ?? id)
        .replace(/\bat (N\d{2,3})\b/g, (_s, n) => (nodeArea[n] ? `in ${nodeArea[n]}` : `at ${n}`))
        .replace(/^([A-Z][A-Z_]{3,}) \((?:user|system|scenario|dispatcher|crew)\): /, "")
        .replace(/\[[A-Z][A-Z_]{3,}\] /g, "")
        .replace(/Recovered from EV-\d+ \((\w+)\) in (\d+) min/g, (_s, t, n) => `Everyone affected by the ${t.toLowerCase().replace(/_/g, " ")} has a unit again (after ${n} min)`)
        .replace(/commitment to \['([^']+)'\] released/g, "its mission to $1 was released")
        .replace(/; 0 active commitments route through it/g, "; no active mission was using it")
        .replace(/; (\d+) active commitments? routes? through it/g, "; $1 active mission(s) were using it")
        .replace(/revoked (\d+) reservations? \([^)]*\)/g, (_s, n) => (n === "0" ? "no reserved places affected" : `${n} reserved place(s) cancelled`))
        .replace(/revoked 0 reservations/g, "no reserved places affected")
        .replace(/\bimpassable for ground units\b/g, "flooded: closed to road teams")
        .replace(/\bpassable again for ground units\b/g, "open again for road teams")
        .replace(/^(.)/, (c) => c.toUpperCase());
  }, [world]);
}

const FLOOD = /impassable for ground units \(flood/;

export function ActivityFeed({ limit = 140, compact }: { limit?: number; compact?: boolean }) {
  const audit = useSim((s) => s.audit);
  const world = useSim((s) => s.world);
  const setSelection = useSim((s) => s.setSelection);
  const openDecision = useSim((s) => s.openDecision);
  const [cat, setCat] = useState("all");
  const human = useHumanizer(world);
  const rows = useMemo(() => {
    const xs = audit.filter((a) => cat === "all" || a.category === cat).slice(-limit * 2);
    // group the many per-road flood closures of one minute into a single row
    const out: Row[] = [];
    for (const a of xs) {
      const last = out[out.length - 1];
      if (last && FLOOD.test(a.message) && FLOOD.test(last.message) && last.tick === a.tick) {
        last.count = (last.count ?? 1) + 1;
        const area = human(a.message).split(":")[0];
        if (!last.areas!.includes(area)) last.areas!.push(area);
        continue;
      }
      out.push(FLOOD.test(a.message) ? { ...a, count: 1, areas: [human(a.message).split(":")[0]] } : a);
    }
    return out.slice(-limit).reverse();
  }, [audit, cat, limit, human]);
  return (
    <div className="flex h-full min-h-0 flex-col">
      {!compact && (
        <div className="scroll-thin flex gap-1 overflow-x-auto border-b border-line px-3 py-2">
          {CATS.map(([c, l]) => (
            <button key={c} type="button" onClick={() => setCat(c)} className={cx("shrink-0 rounded-md px-2 py-1 text-[12px] font-medium", cat === c ? "bg-ink text-white" : "text-mute hover:bg-black/[0.05]")}>
              {l}
            </button>
          ))}
        </div>
      )}
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
        {rows.length === 0 ? (
          <Empty title="No activity yet" body="Press Start: rescue missions, route changes and safety decisions appear here as they happen." />
        ) : (
          <ul className="divide-y divide-line/70">
            {rows.map((a) => (
              <FeedRow key={a.id} a={a} human={human} onRef={(k, v) => (k === "decision" ? openDecision(v) : setSelection({ type: k as any, id: v }))} />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function FeedRow({ a, human, onRef }: { a: Row; human: (m: string) => string; onRef: (k: string, v: string) => void }) {
  const refs = Object.entries(a.refs).filter(([k, v]) => typeof v === "string" && ["incident", "resource", "shelter", "decision"].includes(k)) as [string, string][];
  const text = a.count && a.count > 1 ? `Flooding closed ${a.count} roads to road teams: ${a.areas!.slice(0, 3).join(", ")}${a.areas!.length > 3 ? ` and ${a.areas!.length - 3} more` : ""}` : human(a.message);
  return (
    <li className="fade-in flex gap-2.5 px-3.5 py-2.5" title={a.message}>
      <span className={cx("mt-1.5 size-2 shrink-0 rounded-full", SEV[a.severity])} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-[11px] text-mute">
          <span className="mono">{clock(a.tick)}</span>
          <span className="font-medium">{CAT_LABEL[a.category] ?? a.category}</span>
        </div>
        <div className={cx("mt-0.5 text-[13px] leading-snug", a.severity === "critical" ? "text-crit" : "text-ink")}>{text}</div>
        {refs.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {refs.map(([k, v]) => (
              <button key={k} type="button" onClick={() => onRef(k, v)} className={cx("rounded-md border px-1.5 py-0.5 text-[11px]", k === "decision" ? "border-brand/30 bg-brand-soft text-brand hover:border-brand" : "border-line text-mute hover:border-brand hover:text-brand")}>
                {k === "decision" ? "Why? " : ""}
                {k === "decision" ? "" : v}
              </button>
            ))}
          </div>
        )}
      </div>
    </li>
  );
}
