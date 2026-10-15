import clsx from "clsx";
import { ChevronDown, Loader2, X } from "lucide-react";
import { useEffect, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from "react";

export const cx = clsx;

export function Panel({ title, right, children, className, bodyClass, sub }: { title?: ReactNode; right?: ReactNode; children: ReactNode; className?: string; bodyClass?: string; sub?: ReactNode }) {
  return (
    <section className={cx("panel flex min-h-0 flex-col", className)}>
      {(title || right) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
          <div className="min-w-0">
            <div className="label truncate">{title}</div>
            {sub && <div className="mt-0.5 truncate text-xs text-mute">{sub}</div>}
          </div>
          <div className="flex shrink-0 items-center gap-1.5">{right}</div>
        </header>
      )}
      <div className={cx("min-h-0 flex-1", bodyClass)}>{children}</div>
    </section>
  );
}

type BtnVariant = "solid" | "primary" | "outline" | "ghost" | "danger" | "info";
export function Button({ variant = "outline", size = "md", loading, icon, children, className, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant; size?: "sm" | "md" | "lg"; loading?: boolean; icon?: ReactNode }) {
  return (
    <button
      type="button"
      {...rest}
      disabled={rest.disabled || loading}
      className={cx(
        "inline-flex shrink-0 items-center justify-center gap-1.5 rounded-lg font-medium whitespace-nowrap transition disabled:cursor-not-allowed disabled:opacity-45",
        size === "sm" ? "h-8 px-3 text-[13px]" : size === "lg" ? "h-11 px-5 text-[15px]" : "h-9 px-3.5 text-sm",
        variant === "solid" && "bg-ink text-white hover:bg-ink-2",
        variant === "primary" && "bg-brand text-white shadow-sm hover:bg-brand-2",
        variant === "outline" && "border border-line-2 bg-white text-ink hover:border-ink/30 hover:bg-wash",
        variant === "ghost" && "text-ink-2 hover:bg-black/[0.04]",
        variant === "danger" && "border border-crit/25 bg-crit-soft/60 text-crit hover:bg-crit-soft",
        variant === "info" && "border border-info/25 bg-info-soft/70 text-info hover:bg-info-soft",
        className,
      )}
    >
      {loading ? <Loader2 className="size-3.5 animate-spin" /> : icon}
      {children}
    </button>
  );
}

const TONES: Record<string, string> = {
  neutral: "bg-black/[0.04] text-ink-2 border-black/[0.06]",
  info: "bg-info-soft text-info border-info/20",
  warn: "bg-warn-soft text-warn border-warn/20",
  crit: "bg-crit-soft text-crit border-crit/20",
  ok: "bg-ok-soft text-ok border-ok/20",
  ink: "bg-ink text-white border-ink",
};
export function Badge({ tone = "neutral", children, className, dot }: { tone?: keyof typeof TONES | string; children: ReactNode; className?: string; dot?: boolean }) {
  return (
    <span className={cx("mono inline-flex shrink-0 items-center gap-1 rounded-full border px-1.5 py-[1px] text-[10.5px] font-medium uppercase tracking-wide", TONES[tone] ?? TONES.neutral, className)}>
      {dot && <span className="size-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}

export function Stat({ label, value, unit, tone, hint, className, info }: { label: string; value: ReactNode; unit?: string; tone?: "crit" | "warn" | "ok" | "info"; hint?: ReactNode; className?: string; info?: string }) {
  return (
    <div className={cx("min-w-0", className)}>
      <div className="label flex items-center gap-1">
        <span className="truncate">{label}</span>
        {info && <InfoTip text={info} />}
      </div>
      <div className={cx("num mt-1 font-display text-[22px] leading-none font-semibold tracking-tight", tone === "crit" && "text-crit", tone === "warn" && "text-warn", tone === "ok" && "text-ok", tone === "info" && "text-info")}>
        {value ?? "—"}
        {unit && <span className="ml-0.5 text-xs font-medium text-mute">{unit}</span>}
      </div>
      {hint && <div className="mt-1 truncate text-[11px] text-mute">{hint}</div>}
    </div>
  );
}

/** Small ⓘ that explains a number in plain words (hover, focus or tap). */
export function InfoTip({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-flex normal-case" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button type="button" aria-label={text} onFocus={() => setOpen(true)} onBlur={() => setOpen(false)} onClick={() => setOpen((o) => !o)} className="grid size-3.5 place-items-center rounded-full border border-current text-[9px] leading-none font-semibold text-faint hover:text-ink">
        i
      </button>
      {open && <span role="tooltip" className="absolute top-5 left-1/2 z-50 w-56 -translate-x-1/2 rounded-lg bg-ink px-2.5 py-1.5 text-[12px] leading-snug font-normal tracking-normal text-white shadow-lg">{text}</span>}
    </span>
  );
}

export function Empty({ title, body, icon, action }: { title: string; body?: ReactNode; icon?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex h-full min-h-32 flex-col items-center justify-center gap-2 p-6 text-center">
      {icon && <div className="text-faint">{icon}</div>}
      <div className="text-sm font-medium text-ink-2">{title}</div>
      {body && <div className="max-w-sm text-xs text-mute">{body}</div>}
      {action}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 p-4 text-sm text-mute">
      <Loader2 className="size-4 animate-spin" />
      {label}
    </div>
  );
}

export function Segmented<T extends string | number>({ value, options, onChange, size = "md" }: { value: T; options: { value: T; label: ReactNode }[]; onChange: (v: T) => void; size?: "sm" | "md" }) {
  return (
    <div className="inline-flex max-w-full overflow-x-auto rounded-lg bg-black/[0.05] p-0.5">
      {options.map((o) => (
        <button
          type="button"
          key={String(o.value)}
          onClick={() => onChange(o.value)}
          aria-pressed={value === o.value}
          className={cx("shrink-0 rounded-md font-medium whitespace-nowrap transition", size === "sm" ? "px-2.5 py-1 text-xs" : "px-3 py-1.5 text-sm", value === o.value ? "bg-white text-ink shadow-[0_1px_2px_rgba(0,0,0,0.12)]" : "text-ink-2 hover:text-ink")}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Meter({ value, max, tone = "ink", reserved = 0, className }: { value: number; max: number; tone?: string; reserved?: number; className?: string }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 100;
  const rpct = max > 0 ? Math.min(100 - pct, (reserved / max) * 100) : 0;
  return (
    <div className={cx("flex h-1.5 w-full overflow-hidden rounded-full bg-black/[0.06]", className)}>
      <div className={cx("h-full", tone === "crit" ? "bg-crit" : tone === "warn" ? "bg-warn" : tone === "ok" ? "bg-ok" : tone === "info" ? "bg-info" : "bg-ink")} style={{ width: `${pct}%` }} />
      {rpct > 0 && <div className="h-full bg-info/45" style={{ width: `${rpct}%` }} />}
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="block">
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <span className="label">{label}</span>
        {hint && <span className="mono text-[11px] text-ink-2">{hint}</span>}
      </div>
      {children}
    </label>
  );
}

export const inputCls = "h-9 w-full rounded-lg border border-line-2 bg-white px-2.5 text-sm outline-none focus:border-info";

export function KV({ k, v, mono = true }: { k: ReactNode; v: ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1 text-sm">
      <span className="text-mute">{k}</span>
      <span className={cx("text-right text-ink", mono && "mono num text-[12.5px]")}>{v}</span>
    </div>
  );
}

export function PageHeader({ eyebrow, title, sub, right }: { eyebrow?: string; title: ReactNode; sub?: ReactNode; right?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 pt-2 pb-5">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1.5 text-[13px] font-semibold text-brand">{eyebrow}</div>}
        <h1 className="font-display text-[26px] leading-tight font-semibold tracking-[-0.02em] text-ink sm:text-[30px]">{title}</h1>
        {sub && <p className="mt-1.5 max-w-2xl text-[15px] leading-relaxed text-ink-2">{sub}</p>}
      </div>
      {right && <div className="flex flex-wrap items-center gap-2">{right}</div>}
    </div>
  );
}

/** Close a popover on outside click or Escape. */
export function useDismiss<T extends HTMLElement>(open: boolean, close: () => void) {
  const ref = useRef<T>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) close();
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close]);
  return ref;
}

/** Button that opens a dropdown panel. `children` receives a close() callback. */
export function Dropdown({ label, icon, variant = "outline", size = "sm", align = "right", width = "w-80", children, buttonClass }: { label: ReactNode; icon?: ReactNode; variant?: BtnVariant; size?: "sm" | "md"; align?: "left" | "right"; width?: string; children: (close: () => void) => ReactNode; buttonClass?: string }) {
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);
  const ref = useDismiss<HTMLDivElement>(open, close);
  return (
    <div className="relative" ref={ref}>
      <Button variant={variant} size={size} icon={icon} onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-haspopup="menu" className={buttonClass}>
        {label}
        <ChevronDown className={cx("size-3.5 opacity-60 transition", open && "rotate-180")} />
      </Button>
      {open && <div className={cx("panel fade-in absolute z-40 mt-2 max-h-[75vh] overflow-y-auto p-1.5", align === "right" ? "right-0" : "left-0", width, "max-w-[calc(100vw-2rem)]")}>{children(close)}</div>}
    </div>
  );
}

/** One row in a dropdown: title, plain-language description, optional icon. */
export function MenuItem({ icon, title, desc, onClick, disabled, tone, active }: { icon?: ReactNode; title: ReactNode; desc?: ReactNode; onClick: () => void; disabled?: boolean; tone?: "crit"; active?: boolean }) {
  return (
    <button type="button" role="menuitem" disabled={disabled} onClick={onClick} className={cx("flex w-full items-start gap-3 rounded-lg px-3 py-2.5 text-left transition disabled:cursor-not-allowed disabled:opacity-40", active ? "bg-brand-soft" : "hover:bg-black/[0.04]")}>
      {icon && <span className={cx("mt-0.5 grid size-7 shrink-0 place-items-center rounded-md", tone === "crit" ? "bg-crit-soft text-crit" : "bg-black/[0.05] text-ink-2")}>{icon}</span>}
      <span className="min-w-0">
        <span className={cx("block text-sm font-medium", tone === "crit" ? "text-crit" : "text-ink")}>{title}</span>
        {desc && <span className="mt-0.5 block text-[12.5px] leading-snug text-mute">{desc}</span>}
      </span>
    </button>
  );
}

export function Modal({ open, onClose, title, sub, children, footer, width = "max-w-2xl" }: { open: boolean; onClose: () => void; title: ReactNode; sub?: ReactNode; children: ReactNode; footer?: ReactNode; width?: string }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center bg-black/40 p-0 backdrop-blur-[2px] sm:items-center sm:p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" aria-label={typeof title === "string" ? title : undefined} className={cx("fade-in flex max-h-[92vh] w-full flex-col overflow-hidden rounded-t-2xl bg-white shadow-2xl sm:rounded-2xl", width)}>
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div>
            <h2 className="font-display text-lg font-semibold">{title}</h2>
            {sub && <p className="mt-0.5 text-sm text-mute">{sub}</p>}
          </div>
          <button type="button" aria-label="Close" onClick={onClose} className="rounded-md p-1 text-mute hover:bg-black/5 hover:text-ink">
            <X className="size-5" />
          </button>
        </div>
        <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="flex flex-wrap items-center justify-end gap-2 border-t border-line bg-wash px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}
