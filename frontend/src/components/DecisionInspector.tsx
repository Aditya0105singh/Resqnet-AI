import { useEffect, useState } from "react";
import { Check, ChevronRight, FileSearch, Scale, ShieldCheck, X } from "lucide-react";
import { api } from "../lib/api";
import { useSim } from "../store/sim";
import type { Decision } from "../types";
import { fmt } from "../lib/format";
import { Badge, cx, Spinner } from "./ui";

const OUTCOME_TONE: Record<string, string> = { COMMITTED: "ok", SAFETY_REJECTED: "crit", NO_SHELTER: "warn", UNMATCHED: "neutral", INFEASIBLE: "crit" };

/** Investigation-style inspector for one structured decision record. Every line is
 * rendered from the record produced by the engine — nothing is generated here. */
export function DecisionInspector() {
  const id = useSim((s) => s.decisionId);
  const sim = useSim((s) => s.sim);
  const open = useSim((s) => s.openDecision);
  const [d, setD] = useState<Decision | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!id || !sim) return;
    setD(null);
    setErr(null);
    api
      .get<Decision>(`/api/simulations/${sim.id}/decisions/${id}`)
      .then(setD)
      .catch((e) => setErr(e.message));
  }, [id, sim]);

  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && open(null);
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open]);

  if (!id) return null;
  return (
    <div className="no-print fixed inset-0 z-40 flex justify-end bg-black/15 backdrop-blur-[1px]" onClick={() => open(null)}>
      <aside className="fade-in scroll-thin h-full w-full max-w-[640px] overflow-y-auto border-l border-line bg-paper shadow-2xl" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Decision inspector">
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-line bg-paper/90 px-5 py-3 backdrop-blur">
          <div>
            <div className="label">decision inspector</div>
            <div className="font-display text-lg font-semibold tracking-tight">
              {id} {d && <span className="text-mute">· {d.incident_id}</span>}
            </div>
          </div>
          <button aria-label="Close" className="rounded-full p-1.5 hover:bg-black/5" onClick={() => open(null)}>
            <X className="size-5" />
          </button>
        </div>
        {err && <div className="m-5 rounded-lg bg-crit-soft p-3 text-sm text-crit">{err}</div>}
        {!d && !err && <Spinner label="Loading decision record…" />}
        {d && <DecisionBody d={d} />}
      </aside>
    </div>
  );
}

function Card({ icon, title, meta, status, children }: { icon: React.ReactNode; title: string; meta?: React.ReactNode; status?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="panel p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="grid size-8 place-items-center rounded-lg border border-line bg-wash text-ink-2">{icon}</div>
          <div>
            <div className="text-[14px] font-semibold">{title}</div>
            {meta && <div className="text-xs text-mute">{meta}</div>}
          </div>
        </div>
        {status}
      </div>
      <div className="mt-3">{children}</div>
    </div>
  );
}

export function DecisionBody({ d }: { d: Decision }) {
  const feasible = d.candidates.filter((c) => c.feasible);
  const maxCost = Math.max(0.01, ...feasible.map((c) => c.cost ?? 0));
  const passed = d.safety_checks.filter((c) => c.passed).length;
  return (
    <div className="space-y-3 p-5">
      <div className="panel overflow-hidden">
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <div className="flex items-center gap-2">
            <Badge tone={OUTCOME_TONE[d.outcome] ?? "neutral"} dot>
              {d.outcome.replace(/_/g, " ")}
            </Badge>
            <span className="mono text-[11px] text-mute">
              t={d.tick} · {d.round_id} · state v{d.state_version} · {d.strategy}
            </span>
          </div>
          {d.assignment && <Badge tone={d.assignment.status === "CANCELLED" ? "crit" : "neutral"}>{d.assignment.id} {d.assignment.status.toLowerCase()}</Badge>}
        </div>
        <div className="p-4">
          <div className="label mb-1">outcome</div>
          <p className="text-[14px] leading-relaxed text-ink">{d.explanation}</p>
          {d.assignment?.cancel_reason && <p className="mt-2 rounded-lg bg-crit-soft/60 px-3 py-2 text-xs text-crit">Later cancelled: {d.assignment.cancel_reason}</p>}
        </div>
      </div>

      <Card icon={<FileSearch className="size-4" />} title="Evidence and reasoning" meta={`${d.evidence.length} linked report${d.evidence.length === 1 ? "" : "s"} · confidence ${fmt(d.incident.confidence, 2)} (heuristic, uncalibrated)`} status={<Badge tone={d.incident.eligibility.startsWith("E1") ? "ok" : "warn"}>{d.incident.eligibility.split(" ")[0]}</Badge>}>
        <div className="mb-2 text-xs text-mute">{d.incident.eligibility}</div>
        <div className="grid grid-cols-4 gap-2 rounded-lg bg-wash p-2.5 text-xs">
          <Mini k="urgency" v={d.incident.urgency} />
          <Mini k="people" v={`${d.incident.unassigned}/${d.incident.people}`} />
          <Mini k="deadline" v={`t=${d.incident.deadline}`} />
          <Mini k="version" v={`v${d.incident.known_version ?? d.incident.version}`} />
        </div>
        <ul className="mt-2 divide-y divide-line">
          {d.evidence.map((e) => (
            <li key={e.id} className="flex items-center gap-2 py-1.5 text-xs">
              <span className="mono w-16 shrink-0 text-mute">{e.id}</span>
              <Badge tone={e.claim === "PRESENT" ? "info" : "crit"}>{e.claim === "PRESENT" ? "present" : "no victims"}</Badge>
              <span className="text-ink-2">{e.source}</span>
              <span className="mono text-faint">r={e.reliability}</span>
              <span className="ml-auto truncate text-mute">
                {e.people ?? "?"} ppl · u{e.urgency ?? "?"} · t={e.tick}
              </span>
            </li>
          ))}
        </ul>
      </Card>

      <Card icon={<Scale className="size-4" />} title="Candidate bids" meta={`${feasible.length} feasible of ${d.candidates.length} units · C = ${d.weights.T}·T + ${d.weights.R}·R + ${d.weights.U}·U + ${d.weights.F}·F`}>
        <div className="space-y-1.5">
          {d.candidates.map((c) => {
            const chosen = d.selected?.resource_id === c.resource_id && d.outcome === "COMMITTED";
            return (
              <div key={c.resource_id} className={cx("rounded-lg border px-2.5 py-1.5", chosen ? "border-ok/40 bg-ok-soft/40" : "border-line")}>
                <div className="flex items-center gap-2 text-xs">
                  <span className="mono w-8 font-semibold">{c.resource_id}</span>
                  {c.feasible ? (
                    <>
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-black/[0.06]">
                        <div className={cx("h-full rounded-full", chosen ? "bg-ok" : "bg-ink/70")} style={{ width: `${((c.cost ?? 0) / maxCost) * 100}%` }} />
                      </div>
                      <span className="mono num w-12 text-right">{fmt(c.cost, 3)}</span>
                      <span className="mono num w-24 text-right text-mute">
                        {fmt(c.eta_pickup)}′ / {fmt(c.eta_total)}′
                      </span>
                      {chosen && <Check className="size-3.5 text-ok" />}
                    </>
                  ) : (
                    <span className="text-mute">{c.reason}</span>
                  )}
                </div>
                {c.feasible && c.components && (
                  <div className="mono mt-1 flex gap-3 pl-10 text-[10.5px] text-faint">
                    {Object.entries(c.components).map(([k, v]) => (
                      <span key={k}>
                        {k}={fmt(v, 2)}
                      </span>
                    ))}
                    {c.shelter && <span>→ {c.shelter}</span>}
                    {c.knowledge && c.knowledge !== "truth" && <span className="text-warn">{c.knowledge}</span>}
                  </div>
                )}
              </div>
            );
          })}
        </div>
        {d.rejections.length > 0 && (
          <div className="mt-3">
            <div className="label mb-1">negotiation rejections</div>
            {d.rejections.map((r, i) => (
              <div key={i} className="flex items-center gap-1.5 text-xs text-ink-2">
                <ChevronRight className="size-3 text-faint" />
                <span className="mono">{r.resource}</span> {r.reason}
              </div>
            ))}
          </div>
        )}
        {d.shelter_log.length > 0 && (
          <div className="mt-3">
            <div className="label mb-1">shelter reservations</div>
            {d.shelter_log.map((s, i) => (
              <div key={i} className="flex items-center gap-1.5 text-xs">
                <Badge tone={s.accepted ? "ok" : "crit"}>{s.accepted ? "accept" : "reject"}</Badge>
                <span className="text-ink-2">{s.reason}</span>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card icon={<ShieldCheck className="size-4" />} title="Verification" meta={d.safety_checks.length ? `${passed}/${d.safety_checks.length} safety checks passed` : "No commit attempted in this round"} status={d.safety_checks.length ? <Badge tone={passed === d.safety_checks.length ? "ok" : "crit"}>{passed === d.safety_checks.length ? "passed" : "blocked"}</Badge> : undefined}>
        {d.safety_checks.length === 0 ? (
          <div className="text-xs text-mute">The shield runs only when a matched proposal reaches commit.</div>
        ) : (
          <ul className="space-y-1">
            {d.safety_checks.map((c) => (
              <li key={c.name} className="flex items-start gap-2 text-xs">
                <span className={cx("mt-0.5 grid size-3.5 shrink-0 place-items-center rounded-full", c.passed ? "bg-ok text-white" : "bg-crit text-white")}>{c.passed ? <Check className="size-2.5" /> : <X className="size-2.5" />}</span>
                <span className="font-medium text-ink-2">{c.name}</span>
                <span className="mono ml-auto text-right text-[10.5px] text-mute">{c.detail}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {d.what_would_change && (
        <div className="panel border-dashed p-4">
          <div className="label mb-1">what would change this decision</div>
          <p className="text-[13.5px] leading-relaxed text-ink-2">{d.what_would_change}</p>
        </div>
      )}
    </div>
  );
}

function Mini({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div>
      <div className="label text-[9.5px]">{k}</div>
      <div className="mono num mt-0.5 font-medium">{v}</div>
    </div>
  );
}
