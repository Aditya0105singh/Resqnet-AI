import { useEffect, useMemo, useState } from "react";
import { Background, MarkerType, ReactFlow, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { RefreshCw } from "lucide-react";
import { api } from "../lib/api";
import { useSim } from "../store/sim";
import { SimControls } from "../components/Shell";
import { Badge, Button, cx, Empty, inputCls, PageHeader, Panel, Spinner } from "../components/ui";
import type { Decision, Message, RoundSummary } from "../types";
import { fmt } from "../lib/format";

const TYPE_STYLE: Record<string, { color: string; tone: string; width?: number; dash?: string }> = {
  REQUEST: { color: "#a1a1aa", tone: "neutral" },
  OFFER: { color: "#a1a1aa", tone: "neutral" },
  STATUS: { color: "#d4d4d8", tone: "neutral", dash: "3 3" },
  BID: { color: "#71717a", tone: "neutral", dash: "4 3" },
  DIRECTIVE: { color: "#0a0a0a", tone: "ink", width: 1.6 },
  PROVISIONAL_ACCEPT: { color: "#0891b2", tone: "info" },
  REJECT: { color: "#dc2626", tone: "crit", dash: "2 3" },
  RESERVE: { color: "#22d3ee", tone: "info" },
  ACCEPT_RESERVATION: { color: "#0891b2", tone: "info", width: 1.6 },
  REJECT_RESERVATION: { color: "#dc2626", tone: "crit" },
  SAFETY_REJECT: { color: "#dc2626", tone: "crit", width: 2.5 },
  COMMIT: { color: "#15803d", tone: "ok", width: 2.6 },
  RENEGOTIATE: { color: "#d97706", tone: "warn" },
  PROPOSE: { color: "#0891b2", tone: "info" },
  CONFIRM: { color: "#15803d", tone: "ok", width: 1.6 },
  DECLINE: { color: "#dc2626", tone: "crit", dash: "2 3" },
  EXPIRE: { color: "#d97706", tone: "warn", dash: "2 3" },
  WITHDRAW: { color: "#a1a1aa", tone: "neutral", dash: "3 3" },
  CANCEL_RESERVATION: { color: "#a1a1aa", tone: "neutral", dash: "3 3" },
  LOST: { color: "#dc2626", tone: "crit", dash: "1 4" },
};

interface RoundDetail extends RoundSummary {
  messages: Message[];
  decisions: Decision[];
}

export default function Agents() {
  const sim = useSim((s) => s.sim);
  const frame = useSim((s) => s.frame);
  const rounds = useSim((s) => s.rounds);
  const inject = useSim((s) => s.inject);
  const openDecision = useSim((s) => s.openDecision);
  const [list, setList] = useState<RoundSummary[]>([]);
  const [rid, setRid] = useState<string | null>(null);
  const [detail, setDetail] = useState<RoundDetail | null>(null);
  const [agents, setAgents] = useState<any>(null);
  const [onlyCommits, setOnlyCommits] = useState(true);
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [policy, setPolicy] = useState<string>(sim?.config.policy ?? "balanced");

  const refresh = () => {
    if (!sim) return;
    api.get<{ rounds: RoundSummary[] }>(`/api/simulations/${sim.id}/negotiations?limit=200`).then((r) => setList(r.rounds)).catch(() => {});
    api.get<any>(`/api/simulations/${sim.id}/agents`).then(setAgents).catch(() => {});
  };
  useEffect(refresh, [sim?.id, rounds.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const shown = useMemo(() => list.filter((r) => !onlyCommits || r.commits.length || r.rejections), [list, onlyCommits]);
  useEffect(() => {
    if (!rid && shown.length) setRid(shown[0].id);
  }, [shown, rid]);
  useEffect(() => {
    if (!rid || !sim) return;
    setDetail(null);
    api.get<RoundDetail>(`/api/simulations/${sim.id}/negotiations/${rid}`).then(setDetail).catch(() => setDetail(null));
  }, [rid, sim]);

  const graph = useMemo(() => (detail ? buildGraph(detail) : { nodes: [], edges: [] }), [detail]);
  const msgs = useMemo(() => (detail ? detail.messages.filter((m) => typeFilter === "all" || m.type === typeFilter) : []), [detail, typeFilter]);

  if (!sim || !frame) return <Spinner />;
  return (
    <div className="space-y-3 p-3">
      <SimControls />
      <PageHeader
        eyebrow="Labs"
        title="How rescue units negotiate"
        sub="Each rescue request is offered to nearby units. They bid using what they know, the best bid wins, a shelter confirms space, and a safety check approves it. Every message below is real."
        right={
          <>
            <label className="text-[13px] text-mute" htmlFor="policy">Priority</label>
            <select id="policy" className="h-8 rounded-lg border border-line-2 bg-white px-2 text-[13px]" value={policy} onChange={(e) => { const v = e.target.value; inject("SET_POLICY", { policy: v }, `Policy → ${v}`).then((ok) => ok && setPolicy(v)); }}>
              {[["balanced", "Balanced"], ["fastest", "Fastest pickup"], ["urgency_first", "Most urgent first"], ["equity", "Fair across areas"]].map(([p, l]) => (
                <option key={p} value={p}>
                  {l}
                </option>
              ))}
            </select>
            <Button size="sm" variant="solid" icon={<RefreshCw className="size-3.5" />} onClick={() => inject("SET_POLICY", { policy, renegotiate: true }, "Forced renegotiation")}>
              Re-negotiate now
            </Button>
          </>
        }
      />
      {detail && <RoundStory d={detail} />}
      <div className="grid gap-3 xl:grid-cols-[300px_1fr_420px]">
        <Panel title="negotiation rounds" sub={`${list.length} rounds · ${frame.metrics.negotiation_messages} messages`} right={<label className="flex items-center gap-1 text-xs text-mute"><input type="checkbox" checked={onlyCommits} onChange={(e) => setOnlyCommits(e.target.checked)} />only with results</label>} className={list.length ? "h-[640px]" : "h-[320px]"}>
          <div className="scroll-thin h-full overflow-y-auto">
            {shown.length === 0 ? (
              <Empty title="No negotiation yet" body="Press Start (top left) and units will begin bidding for rescues." />
            ) : (
              shown.map((r) => (
                <button key={r.id} onClick={() => setRid(r.id)} className={cx("block w-full border-b border-line/70 px-3 py-2 text-left hover:bg-wash", rid === r.id && "bg-info-soft/50")}>
                  <div className="flex items-center gap-1.5">
                    <span className="mono text-[12px] font-semibold">{r.id}</span>
                    <span className="mono text-[10.5px] text-mute">t={r.tick}</span>
                    <span className="ml-auto flex gap-1">
                      {r.commits.length > 0 && <Badge tone="ok">{r.commits.length} agreed</Badge>}
                      {r.rejections > 0 && <Badge tone="crit">{r.rejections} turned down</Badge>}
                    </span>
                  </div>
                  <div className="mt-0.5 truncate text-[11px] text-mute">
                    {r.trigger} · {r.message_count} msgs · {r.iterations} it · {fmt(r.duration_ms, 1)} ms
                  </div>
                </button>
              ))
            )}
          </div>
        </Panel>

        <Panel title={detail ? `${detail.id} · message graph` : "message graph"} sub={detail ? `${detail.strategy} · ${detail.incidents.length} requests × ${detail.resources.length} agents` : undefined} className={list.length ? "h-[640px]" : "h-[320px]"}>
          {!detail ? (
            <Spinner label="Select a round" />
          ) : (
            <div className="h-full">
              <ReactFlow nodes={graph.nodes} edges={graph.edges} fitView fitViewOptions={{ padding: 0.15 }} nodesDraggable proOptions={{ hideAttribution: true }} minZoom={0.3}>
                <Background gap={18} color="#e7e7e4" />
              </ReactFlow>
            </div>
          )}
        </Panel>

        <Panel title="what happened" sub={detail ? `${detail.messages.length} messages · ${detail.commits.length} commits` : undefined} className={list.length ? "h-[640px]" : "h-[320px]"} right={detail && <select className="mono rounded border border-line px-1 text-[11px]" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}><option value="all">all</option>{Object.keys(TYPE_STYLE).map((t) => <option key={t}>{t}</option>)}</select>}>
          <div className="scroll-thin h-full overflow-y-auto">
            {detail?.decisions?.length ? (
              <div className="flex flex-wrap gap-1 border-b border-line p-2">
                {detail.decisions.map((d) => (
                  <button key={d.id} onClick={() => openDecision(d.id)} className="mono rounded-md border border-line px-1.5 py-0.5 text-[10.5px] hover:border-info">
                    {d.incident_id}: <span className={d.outcome === "COMMITTED" ? "text-ok" : d.outcome === "UNMATCHED" ? "text-mute" : "text-crit"}>{d.outcome.toLowerCase()}</span>
                  </button>
                ))}
              </div>
            ) : null}
            <ol className="relative">
              {msgs.map((m) => {
                const st = TYPE_STYLE[m.type] ?? TYPE_STYLE.REQUEST;
                return (
                  <li key={m.seq} className="flex gap-2 border-b border-line/50 px-3 py-1.5">
                    <span className="mono w-6 shrink-0 pt-0.5 text-right text-[10px] text-faint">{m.seq}</span>
                    <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full" style={{ background: st.color }} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge tone={st.tone}>{m.type.replace(/_/g, " ").toLowerCase()}</Badge>
                        <span className="mono text-[11.5px]">
                          {m.from} <span className="text-faint">→</span> {m.to}
                        </span>
                      </div>
                      {(m.reason || Object.keys(m.payload).length > 0) && (
                        <div className="mono mt-0.5 text-[10.5px] leading-relaxed text-mute">
                          {m.reason && <span className="text-ink-2">{m.reason} </span>}
                          {Object.entries(m.payload)
                            .filter(([k]) => k !== "reason")
                            .map(([k, v]) => `${k}=${v}`)
                            .join(" · ")}
                        </div>
                      )}
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>
        </Panel>
      </div>

      {agents && (
        <div className="grid gap-3 lg:grid-cols-3">
          <Panel title="rescue agents · local knowledge" sub={agents.resources[0]?.information}>
            <div className="divide-y divide-line">
              {agents.resources.map((r: any) => (
                <div key={r.id} className="flex items-center gap-2 px-4 py-2 text-xs">
                  <span className="mono w-8 font-semibold">{r.id}</span>
                  <span className="text-mute">{r.bids_submitted} bids · {r.commits} commits</span>
                  <span className="ml-auto flex gap-1">
                    {r.belief_mismatch_edges.length > 0 && <Badge tone="warn" className="normal-case">{r.belief_mismatch_edges.length} stale edges</Badge>}
                    {r.discovered_closures.length > 0 && <Badge tone="info">{r.discovered_closures.length} discovered</Badge>}
                    {r.blackout_until && <Badge tone="crit">no comms</Badge>}
                  </span>
                </div>
              ))}
            </div>
          </Panel>
          <Panel title="shelter agents · capacity offers">
            <div className="divide-y divide-line">
              {agents.shelters.map((s: any) => (
                <div key={s.id} className="px-4 py-2 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="mono font-semibold">{s.id}</span>
                    <span className="truncate text-mute">{s.name}</span>
                    <Badge tone={s.free <= 0 ? "crit" : "ok"} className="ml-auto">{s.free} free</Badge>
                  </div>
                  <div className="mono mt-0.5 text-[10.5px] text-mute">
                    {s.occupancy}/{s.capacity} occupied · {s.reserved} reserved · {s.accepts} accepted · {s.rejects} refused
                  </div>
                </div>
              ))}
            </div>
          </Panel>
          <Panel title="route agent · network validity">
            <div className="space-y-2 p-4 text-xs">
              <div>
                <span className="text-mute">Closed for ground units: </span>
                <span className="mono">{agents.route_agent.closed_for_ground.length} edges</span>
              </div>
              <div>
                <span className="text-mute">Flooded roads navigable by boat: </span>
                <span className="mono">{agents.route_agent.navigable_flooded_roads.length}</span>
              </div>
              {agents.route_agent.bridges.map((b: any) => (
                <div key={b.id} className="flex items-center gap-2">
                  <span className="mono w-10">{b.id}</span>
                  <span>{b.name}</span>
                  <Badge tone={b.ground_ok ? "ok" : "crit"} className="ml-auto">{b.ground_ok ? "open" : "closed"}</Badge>
                </div>
              ))}
              {agents.route_agent.manual_closures.map((c: any) => (
                <div key={c.id} className="text-crit">
                  {c.name || c.id}: {c.reason}
                </div>
              ))}
            </div>
          </Panel>
        </div>
      )}
    </div>
  );
}

function buildGraph(d: RoundDetail): { nodes: Node[]; edges: Edge[] } {
  const ids = new Set<string>();
  for (const m of d.messages) {
    if (m.from !== "broadcast") ids.add(m.from);
    if (m.to !== "broadcast" && m.to !== "shelters") ids.add(m.to);
  }
  d.incidents.forEach((i) => ids.add(i));
  const col = (id: string) => (id.startsWith("I-") ? 0 : id.startsWith("S") && /^S\d/.test(id) ? 2 : /^(coordination|coordinator|safety-shield|operator)$/.test(id) ? 3 : 1);
  const buckets: Record<number, string[]> = { 0: [], 1: [], 2: [], 3: [] };
  [...ids].sort().forEach((id) => buckets[col(id)].push(id));
  const nodes: Node[] = [];
  const X = [0, 300, 600, 300];
  for (const [c, list] of Object.entries(buckets)) {
    list.forEach((id, i) => {
      const cc = Number(c);
      const y = cc === 3 ? -110 - i * 0 : i * 74;
      const x = cc === 3 ? X[cc] + (i - (list.length - 1) / 2) * 170 : X[cc];
      const committed = d.matching.some((m) => m.incident === id || m.resource === id);
      nodes.push({
        id,
        position: { x, y },
        data: { label: id },
        style: {
          fontFamily: "JetBrains Mono",
          fontSize: 12,
          padding: "6px 10px",
          borderRadius: cc === 1 ? 999 : 10,
          border: `1px solid ${cc === 3 ? "#0a0a0a" : committed ? "#15803d" : "#d9d9d5"}`,
          background: cc === 3 ? "#0a0a0a" : cc === 0 ? "#fff7ed" : cc === 2 ? "#ecfeff" : "#fff",
          color: cc === 3 ? "#fff" : "#0a0a0a",
          width: 130,
          textAlign: "center",
        },
      });
    });
  }
  const agg = new Map<string, { m: Message; n: number }>();
  for (const m of d.messages) {
    if (m.to === "broadcast" || m.to === "shelters" || m.type === "STATUS" || m.type === "OFFER" || m.type === "REQUEST") continue;
    const k = `${m.from}|${m.to}|${m.type}`;
    const cur = agg.get(k);
    agg.set(k, { m, n: (cur?.n ?? 0) + 1 });
  }
  const edges: Edge[] = [...agg.entries()].map(([k, { m, n }]) => {
    const st = TYPE_STYLE[m.type] ?? TYPE_STYLE.REQUEST;
    const label = m.type === "BID" ? `bid ${m.payload.cost}` : m.type === "COMMIT" ? "COMMIT" : m.type.replace(/_/g, " ").toLowerCase() + (n > 1 ? ` ×${n}` : "");
    return {
      id: k,
      source: m.from,
      target: m.to,
      label,
      animated: m.type === "COMMIT",
      labelStyle: { fontFamily: "JetBrains Mono", fontSize: 9.5, fill: st.color },
      labelBgStyle: { fill: "#fff", fillOpacity: 0.9 },
      style: { stroke: st.color, strokeWidth: st.width ?? 1.2, strokeDasharray: st.dash },
      markerEnd: { type: MarkerType.ArrowClosed, color: st.color, width: 14, height: 14 },
    };
  });
  return { nodes, edges };
}

/** One negotiation round told in plain words, built only from that round's messages. */
function RoundStory({ d }: { d: RoundDetail }) {
  const count = (t: string) => d.messages.filter((m) => m.type === t).length;
  const bids = count("BID") + count("PROPOSE");
  const rejected = d.messages.filter((m) => ["REJECT", "DECLINE", "REJECT_RESERVATION", "SAFETY_REJECT"].includes(m.type));
  const reasons = Object.entries(
    rejected.reduce<Record<string, number>>((acc, m) => {
      const r = (m.reason || m.type.toLowerCase().replace(/_/g, " ")).split(/[;:(]/)[0].trim();
      acc[r] = (acc[r] ?? 0) + 1;
      return acc;
    }, {}),
  )
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3);
  const deals = d.matching.length ? d.matching : d.commits.map((c) => ({ resource: "", incident: c, cost: 0, pass: 0 }));
  const safety = count("SAFETY_REJECT");
  return (
    <section className="panel mb-3 px-4 py-3.5">
      <div className="label mb-1.5">
        round {d.id} at minute {d.tick}, in plain words
      </div>
      <p className="text-[14px] leading-relaxed text-ink">
        {d.incidents.length} rescue request{d.incidents.length === 1 ? " was" : "s were"} offered to {d.resources.length} available unit{d.resources.length === 1 ? "" : "s"}. They made {bids} bid{bids === 1 ? "" : "s"} based on what each one knew about the roads.{" "}
        {deals.length ? (
          <>
            <b className="font-medium">{deals.length} rescue{deals.length === 1 ? " was" : "s were"} agreed</b>
            {d.matching.length ? <>: {d.matching.map((m) => `${m.resource} → ${m.incident}`).join(", ")}</> : null}, each with shelter space reserved and a safety check passed.{" "}
          </>
        ) : (
          "No rescue was agreed this round. "
        )}
        {rejected.length ? (
          <>
            {rejected.length} offer{rejected.length === 1 ? " was" : "s were"} turned down
            {reasons.length ? <> (mostly: {reasons.map(([r, n]) => `${r}${n > 1 ? ` ×${n}` : ""}`).join("; ")})</> : null}.{" "}
          </>
        ) : null}
        {safety ? <span className="text-crit">The safety check blocked {safety} unsafe plan{safety === 1 ? "" : "s"}.</span> : <span className="text-ok">No unsafe plan reached the safety check.</span>}
      </p>
    </section>
  );
}
