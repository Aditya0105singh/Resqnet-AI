import { CircleCheck, Loader2, ShieldCheck, TriangleAlert, X } from "lucide-react";
import { useSim } from "../store/sim";
import { clock } from "../lib/format";
import { useHumanizer } from "./Feed";
import { cx } from "./ui";

/** "What just happened": the latest injected failure, what it broke, and, live, who took over each
 * affected rescue. Everything shown comes from the engine's response and the current frame. */
export function DisruptionCard({ onInspect }: { onInspect?: (incident: string) => void }) {
  const d = useSim((s) => s.disruption);
  const frame = useSim((s) => s.frame);
  const world = useSim((s) => s.world);
  const clear = useSim((s) => s.clearDisruption);
  const audit = useSim((s) => s.audit);
  const human = useHumanizer(world);
  if (!d || !frame) return null;
  const inc = Object.fromEntries(frame.incidents.map((i) => [i.id, i]));
  const rows = d.affected.map((a) => {
    const i = inc[a.incident];
    if (!i) return { ...a, state: "gone" as const, now: [] as string[] };
    if (i.status === "RESCUED") return { ...a, state: "rescued" as const, now: i.assigned };
    if (i.assigned.length === 0) return { ...a, state: "waiting" as const, now: [] };
    const same = i.assigned.every((u) => a.before.includes(u)) && a.before.every((u) => i.assigned.includes(u));
    return { ...a, state: same ? ("kept" as const) : ("moved" as const), now: i.assigned };
  });
  const covered = rows.filter((r) => r.state !== "waiting").length;
  const reShelter = audit.filter((a) => a.tick >= d.tick && a.category === "shelter" && /shelter renegotiated/.test(a.message)).length;
  const viol = frame.metrics.invariant_violations + frame.metrics.route_violations;
  return (
    <div role="status" aria-live="polite" className="panel fade-in w-[min(360px,calc(100vw-3rem))] overflow-hidden">
      <div className="flex items-start gap-2.5 border-b border-line bg-warn-soft/50 px-3.5 py-2.5">
        <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warn" />
        <div className="min-w-0 flex-1">
          <div className="text-[13.5px] font-semibold first-letter:uppercase">{d.label}</div>
          <div className="text-[11.5px] text-mute">at {clock(d.tick)} · now {clock(frame.tick)}</div>
        </div>
        <button type="button" aria-label="Close" onClick={clear} className="rounded p-0.5 text-mute hover:bg-black/5 hover:text-ink">
          <X className="size-4" />
        </button>
      </div>
      <div className="space-y-3 px-3.5 py-3 text-[12.5px]">
        <div>
          <div className="label mb-1">what broke</div>
          <ul className="space-y-1 text-ink-2">
            {d.effects.slice(0, 4).map((e, i) => (
              <li key={i} className="leading-snug">
                {human(e.replace(/^\[[A-Z_]+\]\s*/, ""))}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <div className="label mb-1">rescues affected · {rows.length ? `${covered} of ${rows.length} covered again` : "none"}</div>
          {rows.length === 0 ? (
            <p className="text-ink-2">No rescue was depending on it, so nothing had to be re-planned.</p>
          ) : (
            <ul className="space-y-1">
              {rows.map((r) => (
                <li key={r.incident}>
                  <button type="button" onClick={() => onInspect?.(r.incident)} className="flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left hover:bg-black/[0.04]">
                    <span className="mono font-semibold">{r.incident}</span>
                    <span className="mono text-mute">{r.before.join(", ") || "—"}</span>
                    <span className="text-mute">→</span>
                    <span className={cx("flex items-center gap-1 font-medium", r.state === "waiting" ? "text-warn" : "text-ok")}>
                      {r.state === "waiting" ? <Loader2 className="size-3.5 animate-spin" /> : <CircleCheck className="size-3.5" />}
                      {r.state === "waiting" ? "re-negotiating…" : r.state === "rescued" ? "rescued" : r.state === "kept" ? `still ${r.now.join(", ")}` : r.state === "gone" ? "closed" : `now ${r.now.join(", ")}`}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {reShelter > 0 && <p className="mt-1 text-ink-2">{reShelter} mission(s) were sent to another shelter with free space.</p>}
          {rows.some((r) => r.state === "waiting") && frame.tick === d.tick && <p className="mt-1 text-[11.5px] text-mute">Press Start or Step: units re-negotiate on the next minute.</p>}
        </div>
        <div className={cx("flex items-center gap-1.5 font-medium", viol ? "text-crit" : "text-ok")}>
          <ShieldCheck className="size-4" /> {viol} safety rules broken
        </div>
      </div>
    </div>
  );
}
