import { useEffect, useState } from "react";
import { BookOpen } from "lucide-react";
import compliance from "../../../docs/ps27-compliance.md?raw";
import assumptions from "../../../docs/assumptions.md?raw";
import provenance from "../../../docs/dataset-provenance.md?raw";
import benchmarks from "../../../docs/BENCHMARKS.md?raw";
import sos from "../../../docs/SOS_INTAKE.md?raw";
import messaging from "../../../docs/MESSAGE_PASSING.md?raw";
import commander from "../../../docs/COMMANDER.md?raw";
import crew from "../../../docs/CREW_APP.md?raw";
import { Markdown } from "../lib/markdown";
import { cx, PageHeader, Panel } from "../components/ui";

const DOCS = [
  { id: "ps27-compliance", label: "PS 27 compliance", src: compliance },
  { id: "benchmarks", label: "Benchmarks", src: benchmarks },
  { id: "assumptions", label: "Assumptions", src: assumptions },
  { id: "dataset-provenance", label: "Data provenance", src: provenance },
  { id: "message_passing", label: "Message passing", src: messaging },
  { id: "sos_intake", label: "SOS intake", src: sos },
  { id: "commander", label: "Mission Commander", src: commander },
  { id: "crew_app", label: "Crew app", src: crew },
];

/** Evidence & evaluation: the repository's own docs, rendered so judges read exactly what is committed. */
export default function Research() {
  const fromHash = () => DOCS.find((d) => `#doc-${d.id}` === window.location.hash)?.id ?? DOCS[0].id;
  const [active, setActive] = useState(fromHash);
  useEffect(() => {
    const on = () => setActive(fromHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const doc = DOCS.find((d) => d.id === active) ?? DOCS[0];
  return (
    <div className="space-y-3 p-3">
      <PageHeader eyebrow="Results" title="Evidence & documentation" sub="How each requirement is met and tested, where the data comes from, and what is assumed or simulated." />
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[220px_minmax(0,1fr)]">
        <nav aria-label="Documents" className="panel h-fit p-2">
          {DOCS.map((d) => (
            <a key={d.id} href={`#doc-${d.id}`} className={cx("flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[13px]", d.id === active ? "bg-ink text-white" : "hover:bg-black/[0.04]")}>
              <BookOpen className="size-3.5 shrink-0" />
              {d.label}
            </a>
          ))}
        </nav>
        <Panel>
          <article className="p-5">
            <Markdown source={doc.src} />
          </article>
        </Panel>
      </div>
    </div>
  );
}
