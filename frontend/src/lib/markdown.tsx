import { Fragment, type ReactNode } from "react";

/** Minimal Markdown renderer for the project's own docs (headings, paragraphs, lists,
 * tables, blockquotes, code blocks, **bold**, *italic*, `code`, [links](url)).
 * Input is trusted repository content; no raw HTML is ever rendered. */
function inline(text: string, key = 0): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\)|\*[^*\s][^*]*\*|_[^_\s][^_]*_)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const t = m[0];
    const k = `${key}-${i++}`;
    if (t.startsWith("**")) out.push(<b key={k}>{inline(t.slice(2, -2), i)}</b>);
    else if (t.startsWith("`")) out.push(<code key={k} className="mono rounded bg-black/[0.05] px-1 text-[0.9em]">{t.slice(1, -1)}</code>);
    else if (t.startsWith("[")) {
      const [, label, href] = t.match(/^\[([^\]]+)\]\(([^)]+)\)$/) ?? [];
      const external = /^https?:/.test(href);
      const doc = href.match(/^([A-Za-z_-]+)\.md$/);
      out.push(
        <a key={k} href={external ? href : doc ? `#doc-${doc[1].toLowerCase()}` : href} target={external ? "_blank" : undefined} rel="noreferrer" className="text-info underline underline-offset-2">
          {label}
        </a>,
      );
    } else out.push(<i key={k}>{t.slice(1, -1)}</i>);
    last = m.index + t.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function Markdown({ source }: { source: string }) {
  const lines = source.replace(/\r/g, "").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  let n = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }
    if (line.startsWith("```")) {
      const body: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) body.push(lines[i++]);
      i++;
      blocks.push(<pre key={n++} className="mono scroll-thin overflow-x-auto rounded-lg bg-black/[0.04] p-3 text-[11.5px] leading-snug">{body.join("\n")}</pre>);
      continue;
    }
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h) {
      const lvl = h[1].length;
      const cls = ["", "text-2xl font-semibold tracking-tight", "mt-4 text-lg font-semibold", "mt-3 text-[15px] font-semibold", "mt-2 text-[14px] font-semibold"][lvl];
      blocks.push(<div key={n++} role="heading" aria-level={lvl} className={cls}>{inline(h[2])}</div>);
      i++;
      continue;
    }
    if (line.startsWith("|")) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].startsWith("|")) {
        const cells = lines[i].trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
        if (!cells.every((c) => /^:?-{2,}:?$/.test(c))) rows.push(cells);
        i++;
      }
      const [head, ...body] = rows;
      blocks.push(
        <div key={n++} className="scroll-thin overflow-x-auto">
          <table className="w-full text-[12.5px]">
            <thead>
              <tr className="border-b border-line text-left">
                {head.map((c, j) => (
                  <th key={j} className="px-2 py-1.5 font-medium">{inline(c)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {body.map((r, ri) => (
                <tr key={ri} className="border-b border-line/60 align-top">
                  {r.map((c, j) => (
                    <td key={j} className="px-2 py-1.5">{inline(c)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    if (/^\s*([-*]|\d+\.)\s/.test(line)) {
      const ordered = /^\s*\d+\./.test(line);
      const items: string[] = [];
      while (i < lines.length && /^\s*([-*]|\d+\.)\s/.test(lines[i])) items.push(lines[i++].replace(/^\s*([-*]|\d+\.)\s/, ""));
      const Tag = ordered ? "ol" : "ul";
      blocks.push(
        <Tag key={n++} className={ordered ? "list-decimal space-y-1 pl-5" : "list-disc space-y-1 pl-5"}>
          {items.map((it, j) => (
            <li key={j}>{inline(it)}</li>
          ))}
        </Tag>,
      );
      continue;
    }
    if (line.startsWith(">")) {
      const body: string[] = [];
      while (i < lines.length && lines[i].startsWith(">")) body.push(lines[i++].replace(/^>\s?/, ""));
      blocks.push(<blockquote key={n++} className="border-l-2 border-info/50 pl-3 text-ink-2">{inline(body.join(" "))}</blockquote>);
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(#|\||```|>|\s*([-*]|\d+\.)\s)/.test(lines[i])) para.push(lines[i++]);
    blocks.push(<p key={n++}>{inline(para.join(" "))}</p>);
  }
  return <div className="space-y-3 text-[13.5px] leading-relaxed">{blocks.map((b, j) => <Fragment key={j}>{b}</Fragment>)}</div>;
}
