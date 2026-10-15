import { useState } from "react";
import { Check, ChevronDown, ChevronRight, Inbox, X } from "lucide-react";
import { useSim } from "../store/sim";
import type { Proposal } from "../types";
import { fmt } from "../lib/format";
import { Badge, Button, cx, Empty } from "./ui";

const STATUS_TONE: Record<string, string> = { PENDING: "info", APPROVED: "ok", REJECTED: "crit", EXPIRED: "neutral" };

export function describe(p: Proposal) {
  const x = p.params as Record<string, string>;
  switch (p.action) {
    case "MANUAL_ASSIGN":
      return `Send ${x.resource_id} to ${x.incident_id}`;
    case "CANCEL_ASSIGNMENT":
      return `Cancel mission ${x.assignment_id}`;
    case "REQUEST_REASSIGN":
      return `Release ${x.resource_id} for reassignment`;
    case "RESOLVE_DISPUTE":
      return `${x.decision} disputed ${x.incident_id}`;
    default:
      return p.action;
  }
}

function ProposalCard({ p }: { p: Proposal }) {
  const inject = useSim((s) => s.inject);
  const [open, setOpen] = useState(false);
  const pending = p.status === "PENDING";
  const failed = p.preview.checks.filter((c) => !c.passed);
  return (
    <div className={cx("rounded-lg border p-3", pending ? (p.preview.ok ? "border-info/40 bg-info/[0.03]" : "border-crit/30 bg-crit/[0.03]") : "border-line bg-white")}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-[13.5px] font-medium">{describe(p)}</div>
          <div className="mono mt-0.5 text-[10.5px] text-mute">
            {p.id} · proposed by {p.source} at t={p.tick}
            {pending ? ` · expires t=${p.expires}` : p.decided_by ? ` · ${p.status.toLowerCase()} by ${p.decided_by} at t=${p.decided_tick}` : ""}
          </div>
        </div>
        <Badge tone={STATUS_TONE[p.status]}>{p.status.toLowerCase()}</Badge>
      </div>
      {p.rationale && <p className="mt-2 text-[12px] leading-relaxed text-ink/80">{p.rationale}</p>}
      {pending && (
        <div className="mt-2 rounded-md bg-black/[0.03] px-2.5 py-2 text-[12px]">
          <div className="flex items-center gap-1.5">
            <Badge tone={p.preview.ok ? "ok" : "crit"}>{p.preview.ok ? "preview passes" : "preview fails"}</Badge>
            <span className="mono text-[10.5px] text-mute">checked on a copy at t={p.preview.tick}</span>
          </div>
          {p.preview.plan && (
            <div className="mono mt-1.5 text-[11.5px]">
              pickup {fmt(p.preview.plan.eta_pickup)} min · {fmt(p.preview.plan.eta_total)} min to {p.preview.plan.shelter} · {p.preview.plan.people} people · cost {fmt(p.preview.plan.cost, 3)}
            </div>
          )}
          {!p.preview.ok && <div className="mt-1.5 text-crit">{p.preview.summary}</div>}
          {p.preview.checks.length > 0 && (
            <button className="mt-1.5 flex items-center gap-1 text-[11px] text-mute hover:text-ink" onClick={() => setOpen(!open)}>
              {open ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}
              safety checks: {p.preview.checks.length - failed.length}/{p.preview.checks.length} pass
            </button>
          )}
          {open && (
            <ul className="mono mt-1 space-y-0.5 text-[10.5px]">
              {p.preview.checks.map((c, i) => (
                <li key={i} className={c.passed ? "text-mute" : "text-crit"}>
                  {c.passed ? "✓" : "✗"} {c.name}: {c.detail}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {!pending && p.outcome && <p className="mono mt-2 text-[11px] text-mute">{p.outcome}</p>}
      {pending && (
        <div className="mt-2.5 flex gap-1.5">
          <Button size="sm" variant="solid" icon={<Check className="size-3.5" />} disabled={!p.preview.ok} onClick={() => inject("APPROVE_PROPOSAL", { proposal_id: p.id }, `${p.id} approved`)}>
            Approve
          </Button>
          <Button size="sm" variant="ghost" icon={<X className="size-3.5" />} onClick={() => inject("REJECT_PROPOSAL", { proposal_id: p.id, reason: "rejected by dispatcher" }, `${p.id} rejected`)}>
            Reject
          </Button>
        </div>
      )}
    </div>
  );
}

/** Proposed actions waiting for a human decision. Nothing here changes the world until approved. */
export function Approvals() {
  const proposals = useSim((s) => s.frame?.proposals ?? []);
  if (!proposals.length)
    return (
      <Empty
        icon={<Inbox className="size-5" />}
        title="No proposals waiting"
        body="Suggestions from the recommender, SOS intake or an assistant appear here. Each is previewed against the safety shield and only changes the world when a dispatcher approves it. Select an incident and use Suggest unit to try it."
      />
    );
  const pending = proposals.filter((p) => p.status === "PENDING");
  const recent = proposals.filter((p) => p.status !== "PENDING").reverse();
  return (
    <div className="space-y-2 p-3">
      {pending.map((p) => (
        <ProposalCard key={p.id} p={p} />
      ))}
      {recent.length > 0 && <div className="label px-1 pt-2">recent decisions</div>}
      {recent.map((p) => (
        <ProposalCard key={p.id} p={p} />
      ))}
    </div>
  );
}
