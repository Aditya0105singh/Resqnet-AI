import { useSim } from "../store/sim";

const fmtTime = (iso: string) => {
  const d = new Date(iso);
  return `${d.getDate()} ${d.toLocaleString("en-GB", { month: "short" })} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
};

/** River level, plus — when the run replays a real flood — the real clock time, GloFAS discharge and a sparkline. */
export function RiverCard() {
  const frame = useSim((s) => s.frame);
  const sim = useSim((s) => s.sim);
  if (!frame) return null;
  const ev = sim?.flood_event;
  const q = ev?.discharge;
  let spark: React.ReactNode = null;
  if (ev && q && q.length > 1) {
    const w = 132;
    const h = 30;
    const lo = Math.min(...q);
    const hi = Math.max(...q);
    const x = (i: number) => (i / (q.length - 1)) * w;
    const y = (v: number) => h - 3 - ((v - lo) / Math.max(1e-9, hi - lo)) * (h - 8);
    const t = Math.min(frame.tick, q.length - 1);
    const path = q.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join("");
    spark = (
      <svg viewBox={`0 0 ${w} ${h}`} className="mt-1.5 block w-[132px]" role="img" aria-label="River discharge replay">
        <path d={`${path}L${w} ${h}L0 ${h}Z`} fill="#0891b2" opacity={0.12} />
        <path d={path} fill="none" stroke="#0891b2" strokeWidth={1.4} />
        <line x1={x(t)} x2={x(t)} y1={0} y2={h} stroke="#0a0a0a" strokeWidth={1} />
        <circle cx={x(t)} cy={y(q[t])} r={2.6} fill="#0a0a0a" />
      </svg>
    );
  }
  return (
    <div className="rounded-xl border border-line-2 bg-white/90 px-3 py-1.5 text-right shadow-sm backdrop-blur">
      <div className="label">river level</div>
      <div className="mono num text-sm font-semibold">{frame.river_level} m</div>
      {ev && frame.flood_real_time && (
        <>
          <div className="mono mt-1 text-[10.5px] leading-tight text-mute">
            {fmtTime(frame.flood_real_time)} · 2018
            <br />
            {Math.round(frame.flood_discharge ?? 0).toLocaleString()} m³/s
          </div>
          {spark}
          <div className="mono mt-0.5 text-[9.5px] text-faint" title={ev.note}>
            GloFAS replay · {ev.real_hours_per_tick.toFixed(2)} h/tick
          </div>
        </>
      )}
    </div>
  );
}
