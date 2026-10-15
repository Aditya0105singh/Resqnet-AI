import { Fragment, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bot, ChevronDown, ChevronRight, Send, ShieldAlert, X } from "lucide-react";
import { api } from "../lib/api";
import { useSim } from "../store/sim";
import { Badge, Button, cx } from "./ui";

type Citation = { id: string; kind: string; exists: boolean; from_tools: boolean };
type Answer = { question: string; answer: string; citations: Citation[]; tool_calls: { tool: string; input: Record<string, unknown>; ok: boolean }[]; engine: string; warnings: string[]; tick: number; elapsed_ms: number; queued_proposals: string[] };
type Turn = { q: string; a?: Answer; error?: string };

const SUGGESTED = ["Status", "Which shelters can accept 5 more people?", "Which neighbourhoods have the longest waiting times?", "What happens if B2 becomes unavailable?"];

/** Renders an answer, turning [ID] citations into links and **x** into bold. */
function Rich({ text, cites, onCite }: { text: string; cites: Citation[]; onCite: (c: Citation) => void }) {
  const byId = Object.fromEntries(cites.map((c) => [c.id, c]));
  return (
    <>
      {text.split("\n").map((line, li) => (
        <p key={li} className={cx("leading-relaxed", line.startsWith("- ") && "pl-3")}>
          {line.split(/(\[[A-Z]{1,3}-?\d{1,5}\]|\*\*[^*]+\*\*)/g).map((part, i) => {
            const m = part.match(/^\[([A-Z]{1,3}-?\d{1,5})\]$/);
            if (m && byId[m[1]]) {
              const c = byId[m[1]];
              return (
                <button key={i} onClick={() => onCite(c)} title={c.exists ? `${c.kind} ${c.id}` : `${c.id} does not exist`} className={cx("mono mx-0.5 rounded px-1 text-[11.5px] underline-offset-2 hover:underline", c.exists ? "bg-info/10 text-info" : "bg-crit/10 text-crit line-through")}>
                  {c.id}
                </button>
              );
            }
            if (part.startsWith("**") && part.endsWith("**")) return <b key={i}>{part.slice(2, -2)}</b>;
            return <Fragment key={i}>{part}</Fragment>;
          })}
        </p>
      ))}
    </>
  );
}

function AnswerCard({ a, onCite }: { a: Answer; onCite: (c: Citation) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="space-y-2 rounded-lg border border-line bg-white p-3 text-[13px]">
      <Rich text={a.answer} cites={a.citations} onCite={onCite} />
      {a.queued_proposals.length > 0 && (
        <div className="rounded-md bg-info/[0.06] px-2.5 py-1.5 text-[12px]">
          Queued for your approval: <b className="mono">{a.queued_proposals.join(", ")}</b>. Open the Approve tab on Command. Nothing has changed yet.
        </div>
      )}
      {a.warnings.length > 0 && (
        <ul className="space-y-0.5 rounded-md bg-warn/[0.08] px-2.5 py-1.5 text-[11.5px]">
          {a.warnings.map((w, i) => (
            <li key={i} className="flex gap-1.5">
              <ShieldAlert className="mt-0.5 size-3 shrink-0 text-warn" />
              {w}
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap items-center gap-1.5 text-[10.5px] text-mute">
        <Badge tone={a.engine.startsWith("llm") ? "info" : "neutral"}>{a.engine.startsWith("llm") ? "Claude" : a.engine.startsWith("rules (") ? "offline rules (Claude unavailable)" : "offline rules"}</Badge>
        <span className="mono">
          t={a.tick} · {a.citations.length} citation(s) · {a.elapsed_ms} ms
        </span>
        {a.tool_calls.length > 0 && (
          <button className="ml-auto flex items-center gap-0.5 hover:text-ink" onClick={() => setOpen(!open)}>
            {open ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}
            {a.tool_calls.length} tool call(s)
          </button>
        )}
      </div>
      {open && (
        <ul className="mono space-y-0.5 text-[10.5px] text-mute">
          {a.tool_calls.map((t, i) => (
            <li key={i}>
              {t.ok ? "✓" : "✗"} {t.tool}({JSON.stringify(t.input)})
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Mission Commander drawer: questions are answered from this run's records only. */
export function CommanderDrawer() {
  const open = useSim((s) => s.askOpen);
  const setOpen = useSim((s) => s.setAskOpen);
  const sim = useSim((s) => s.sim);
  const openDecision = useSim((s) => s.openDecision);
  const setSelection = useSim((s) => s.setSelection);
  const nav = useNavigate();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth" }), [turns.length, busy]);
  useEffect(() => setTurns([]), [sim?.id]);

  const send = async (question: string) => {
    if (!sim || !question.trim() || busy) return;
    setQ("");
    setTurns((t) => [...t, { q: question }]);
    setBusy(true);
    try {
      const a = await api.post<Answer>(`/api/simulations/${sim.id}/ask`, { question });
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, a } : x)));
    } catch (e) {
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, error: (e as Error).message } : x)));
    } finally {
      setBusy(false);
    }
  };
  const onCite = (c: Citation) => {
    if (!c.exists) return;
    if (c.kind === "decision") return openDecision(c.id);
    const type = c.kind === "incident" ? "incident" : c.kind === "unit" ? "resource" : c.kind === "shelter" ? "shelter" : null;
    if (type) {
      setSelection({ type, id: c.id });
      nav("/command");
    } else if (c.kind === "proposal") nav("/command");
  };

  if (!open) return null;
  return (
    <aside aria-label="Mission Commander" className="no-print fixed inset-y-0 right-0 z-40 flex w-full max-w-[440px] flex-col border-l border-line bg-paper shadow-2xl">
      <header className="flex items-center gap-2 border-b border-line px-4 py-3">
        <Bot className="size-4" />
        <div className="flex-1">
          <div className="text-[14px] font-semibold">Mission Commander</div>
          <div className="text-[11px] text-mute">Answers from this run's records, with citations. It can suggest actions but cannot take them.</div>
        </div>
        <button aria-label="Close" onClick={() => setOpen(false)} className="rounded p-1 hover:bg-black/5">
          <X className="size-4" />
        </button>
      </header>
      <div className="scroll-thin flex-1 space-y-3 overflow-y-auto p-4">
        {turns.length === 0 && (
          <div className="space-y-2">
            <p className="text-[13px] text-mute">Ask about incidents, units, shelters, decisions or what-if scenarios. Try:</p>
            <div className="flex flex-wrap gap-1.5">
              {SUGGESTED.map((s) => (
                <button key={s} onClick={() => send(s)} className="rounded-full border border-line-2 bg-white px-2.5 py-1 text-left text-[12px] hover:border-ink">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {turns.map((t, i) => (
          <div key={i} className="space-y-1.5">
            <div className="ml-auto w-fit max-w-[85%] rounded-lg bg-ink px-3 py-1.5 text-[13px] text-white">{t.q}</div>
            {t.a && <AnswerCard a={t.a} onCite={onCite} />}
            {t.error && <div className="rounded-lg bg-crit/[0.06] px-3 py-2 text-[12.5px] text-crit">{t.error}</div>}
          </div>
        ))}
        {busy && <div className="mono text-[11px] text-mute">reading the run's records…</div>}
        <div ref={end} />
      </div>
      <form
        className="flex gap-2 border-t border-line p-3"
        onSubmit={(e) => {
          e.preventDefault();
          send(q);
        }}
      >
        <input aria-label="Question" className="h-9 min-w-0 flex-1 rounded-lg border border-line-2 bg-white px-2.5 text-sm outline-none focus:border-info" value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. Why was I-004 reassigned?" />
        <Button variant="solid" icon={<Send className="size-4" />} disabled={!q.trim() || busy || !sim} type="submit">
          Ask
        </Button>
      </form>
    </aside>
  );
}
