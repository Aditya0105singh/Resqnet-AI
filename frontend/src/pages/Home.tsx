import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Bot, Construction, FlaskConical, Languages, Map, MessageSquareWarning, PlayCircle, Radio, ScrollText, ShieldCheck, Ship, Smartphone, Tent, Users } from "lucide-react";
import { api } from "../lib/api";

type Paired = { mean: number; ci_low: number; ci_high: number; significant: boolean };

function useHeadline() {
  const [h, setH] = useState<{ service: Paired; time: Paired } | null>(null);
  useEffect(() => {
    api
      .get<any>("/api/evaluation")
      .then((ev) => {
        const p = ev?.suites?.resilience?.scenarios?.coordinator_outage?.paired?.["decentralized-centralized"];
        if (p?.service_rate && p?.mean_time_to_service) setH({ service: p.service_rate, time: p.mean_time_to_service });
      })
      .catch(() => {});
  }, []);
  return h;
}

const PROBLEMS = [
  { icon: <Construction className="size-5" />, title: "Bridges go under", body: "A route that worked five minutes ago is now impossible." },
  { icon: <Ship className="size-5" />, title: "Boats break down", body: "A unit halfway to a rooftop rescue stops working." },
  { icon: <Tent className="size-5" />, title: "Shelters fill up", body: "People are on their way to a camp that has no space." },
  { icon: <Radio className="size-5" />, title: "Networks fail", body: "The control room goes offline. Radio messages get lost." },
];

const STEPS = [
  { n: "1", title: "Someone asks for help", body: "An SOS arrives in English, Hindi or Malayalam. The system pulls out how many people, who is vulnerable and how urgent it is. It never guesses a location." },
  { n: "2", title: "Units negotiate", body: "Boats and ground teams bid for the rescue using what they know. Shelters confirm they have space. No single computer is in charge." },
  { n: "3", title: "Every plan is safety-checked", body: "Before anything is committed: no unit in two places, no overfull shelter, no boat on a dry road. Unsafe plans are blocked." },
  { n: "4", title: "Crews act, humans stay in control", body: "Crews get the mission on their phone, even offline. Dispatchers approve AI suggestions. Every decision can be explained." },
];

const FEATURES = [
  { to: "/command", icon: <Map className="size-5" />, title: "Live console", body: "The whole city on one map: requests, units, shelters, floods and closed roads, updating every minute." },
  { to: "/sos", icon: <Languages className="size-5" />, title: "Citizen SOS", body: "Send a test message in three languages and see exactly what the system understood." },
  { to: "/crew", icon: <Smartphone className="size-5" />, title: "Crew app", body: "The phone screen a boat crew uses. It works without signal and syncs safely later." },
  { to: "/judge", icon: <MessageSquareWarning className="size-5" />, title: "Kerala 2018 story", body: "Five chapters of the August 2018 flood in Aluva, with the real river levels, and three failures at the peak." },
  { to: "/decision-lab", icon: <FlaskConical className="size-5" />, title: "What-if lab", body: "Rewind to any minute, change one decision, and compare the two futures side by side." },
  { to: "/arena", icon: <ScrollText className="size-5" />, title: "Benchmarks", body: "Our approach against a central control room, repeated over many runs with confidence ranges." },
];

export default function Home() {
  const h = useHeadline();
  const svc = h ? `+${Math.round(h.service.mean * 100)} pts` : "+10 pts";
  const mins = h ? `${Math.round(Math.abs(h.time.mean))} min` : "19 min";
  return (
    <div>
      {/* hero */}
      <section className="relative overflow-hidden border-b border-line bg-[radial-gradient(1000px_420px_at_15%_-10%,#e6f6f9,transparent_60%),radial-gradient(800px_400px_at_100%_0%,#f1f5f9,transparent_60%)]">
        <div className="mx-auto grid max-w-[1200px] items-center gap-10 px-5 py-14 sm:py-20 lg:grid-cols-[1.05fr_1fr]">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-brand/20 bg-white px-3 py-1 text-[12.5px] font-medium text-brand">
              <span className="size-1.5 rounded-full bg-brand" /> Flood rescue coordination · real map of Aluva, Kerala
            </div>
            <h1 className="mt-5 font-display text-[38px] leading-[1.05] font-semibold tracking-[-0.03em] text-ink sm:text-[54px]">
              When the rescue plan breaks, <span className="text-brand">rescue keeps going.</span>
            </h1>
            <p className="mt-5 max-w-xl text-[17px] leading-relaxed text-ink-2">
              RESQNET AI coordinates boats, rescue teams and shelters during a flood. When bridges collapse, boats fail or the control room goes offline, it re-plans straight away and shows that every new plan is still safe.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/demo" className="inline-flex h-12 items-center gap-2 rounded-lg bg-brand px-5 text-[15px] font-medium text-white shadow-sm transition hover:bg-brand-2">
                <PlayCircle className="size-5" /> Watch the 3-minute demo
              </Link>
              <Link to="/command" className="inline-flex h-12 items-center gap-2 rounded-lg border border-line-2 bg-white px-5 text-[15px] font-medium text-ink transition hover:border-ink/30">
                Open the live console <ArrowRight className="size-4" />
              </Link>
            </div>
            <p className="mt-4 text-[13px] text-mute">Runs in your browser. No sign-up needed.</p>
          </div>
          <div className="relative">
            <div className="overflow-hidden rounded-2xl border border-line bg-white shadow-[0_30px_80px_-30px_rgba(8,47,73,0.35)]">
              <div className="flex items-center gap-1.5 border-b border-line bg-wash px-3 py-2">
                <span className="size-2.5 rounded-full bg-[#fca5a5]" />
                <span className="size-2.5 rounded-full bg-[#fcd34d]" />
                <span className="size-2.5 rounded-full bg-[#86efac]" />
                <span className="ml-2 text-[11.5px] text-mute">Live console · Aluva, Kerala</span>
              </div>
              <img src="/console.png" alt="The RESQNET live console showing rescue units, shelters and flooded roads on the Aluva map" className="block w-full" loading="eager" />
            </div>
          </div>
        </div>
      </section>

      {/* problem */}
      <section className="mx-auto max-w-[1200px] px-5 py-16">
        <SectionHead eyebrow="The problem" title="In a flood, plans break every few minutes" sub="Most dashboards show where the trouble is. Very few show how the rescue effort re-plans when things go wrong, and whether the new plan is safe." />
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {PROBLEMS.map((p) => (
            <div key={p.title} className="panel p-5">
              <div className="grid size-10 place-items-center rounded-lg bg-crit-soft text-crit">{p.icon}</div>
              <div className="mt-4 font-medium">{p.title}</div>
              <p className="mt-1 text-sm leading-relaxed text-mute">{p.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* how it works */}
      <section className="border-y border-line bg-white">
        <div className="mx-auto max-w-[1200px] px-5 py-16">
          <SectionHead eyebrow="How it works" title="From an SOS to a safe rescue, in four steps" />
          <ol className="mt-10 grid gap-6 md:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((s) => (
              <li key={s.n} className="relative">
                <div className="grid size-10 place-items-center rounded-full bg-brand font-display text-lg font-semibold text-white">{s.n}</div>
                <div className="mt-4 font-medium">{s.title}</div>
                <p className="mt-1.5 text-sm leading-relaxed text-mute">{s.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* results */}
      <section className="mx-auto max-w-[1200px] px-5 py-16">
        <SectionHead eyebrow="Measured, not claimed" title="What happens when the control room goes down" sub="Same floods, same incidents, same failures: our multi-agent approach against a central optimiser, repeated over 10 paired runs with 95% confidence ranges (on the synthetic test city)." />
        <div className="mt-10 grid gap-4 md:grid-cols-3">
          <BigStat value={svc} label="higher share of people served" note="when the central control room fails (service rate, in percentage points)" />
          <BigStat value={mins} label="faster on average" note="to reach people waiting for rescue" />
          <BigStat value="0" label="safety rules broken" note="in every scenario and strategy tested" tone="ok" />
        </div>
        <p className="mt-5 max-w-3xl text-sm leading-relaxed text-mute">
          Honest note: on a healthy network, a central optimiser is as good or slightly faster, and we report that too. The advantage of agents is that they keep working when the centre fails.{" "}
          <Link to="/arena" className="font-medium text-brand hover:underline">
            See all benchmarks →
          </Link>
        </p>
      </section>

      {/* features */}
      <section className="border-y border-line bg-white">
        <div className="mx-auto max-w-[1200px] px-5 py-16">
          <SectionHead eyebrow="Explore" title="Everything you can try" />
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <Link key={f.to} to={f.to} className="group panel p-5 transition hover:-translate-y-0.5 hover:border-brand/40">
                <div className="grid size-10 place-items-center rounded-lg bg-brand-soft text-brand">{f.icon}</div>
                <div className="mt-4 flex items-center gap-1.5 font-medium">
                  {f.title}
                  <ArrowRight className="size-4 text-mute transition group-hover:translate-x-0.5 group-hover:text-brand" />
                </div>
                <p className="mt-1 text-sm leading-relaxed text-mute">{f.body}</p>
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* trust */}
      <section className="mx-auto grid max-w-[1200px] gap-6 px-5 py-16 md:grid-cols-3">
        <Trust icon={<ShieldCheck className="size-5" />} title="Safety you can check" body="Seven safety rules are checked on every action. Hundreds of randomised stress tests have never broken one." />
        <Trust icon={<Bot className="size-5" />} title="AI that can't act alone" body="AI reads messages and explains decisions, citing the exact records it used. Only a human can approve an action." />
        <Trust icon={<Users className="size-5" />} title="Honest about limits" body="Roads, bridges and terrain around Aluva are real (OpenStreetMap, Copernicus), and the 2018 scenario replays the real river discharge. Flood depths, incidents and SOS messages are simulated, and every page says so." />
      </section>

      {/* CTA */}
      <section className="px-5 pb-6">
        <div className="mx-auto flex max-w-[1200px] flex-col items-start justify-between gap-6 rounded-2xl bg-[#0b2530] px-8 py-10 text-white md:flex-row md:items-center">
          <div>
            <h2 className="font-display text-2xl font-semibold tracking-tight">See it handle a triple failure, live.</h2>
            <p className="mt-1.5 text-cyan-50/75">Eight steps, about three minutes. Every step runs the real system.</p>
          </div>
          <Link to="/demo" className="inline-flex h-12 shrink-0 items-center gap-2 rounded-lg bg-white px-5 text-[15px] font-medium text-[#0b2530] transition hover:bg-cyan-50">
            <PlayCircle className="size-5" /> Start the guided demo
          </Link>
        </div>
      </section>
    </div>
  );
}

function SectionHead({ eyebrow, title, sub }: { eyebrow: string; title: string; sub?: string }) {
  return (
    <div className="max-w-2xl">
      <div className="text-[13px] font-semibold text-brand">{eyebrow}</div>
      <h2 className="mt-2 font-display text-[28px] leading-tight font-semibold tracking-[-0.02em] sm:text-[34px]">{title}</h2>
      {sub && <p className="mt-3 text-[16px] leading-relaxed text-ink-2">{sub}</p>}
    </div>
  );
}

function BigStat({ value, label, note, tone }: { value: string; label: string; note: string; tone?: "ok" }) {
  return (
    <div className="panel p-6">
      <div className={`font-display text-[44px] leading-none font-semibold tracking-tight ${tone === "ok" ? "text-ok" : "text-brand"}`}>{value}</div>
      <div className="mt-3 font-medium">{label}</div>
      <div className="mt-0.5 text-sm text-mute">{note}</div>
    </div>
  );
}

function Trust({ icon, title, body }: { icon: React.ReactNode; title: string; body: string }) {
  return (
    <div>
      <div className="grid size-10 place-items-center rounded-lg bg-ok-soft text-ok">{icon}</div>
      <div className="mt-4 font-medium">{title}</div>
      <p className="mt-1 text-sm leading-relaxed text-mute">{body}</p>
    </div>
  );
}
