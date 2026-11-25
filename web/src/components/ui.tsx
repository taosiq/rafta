import clsx from "clsx";
import { AlertTriangle, CheckCircle2, Clock, type LucideIcon } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

import type { Abc, Status, Xyz } from "@/lib/api";
import { CLASS_COLOR, CLASS_LABEL, STATUS_META, XYZ_LABEL } from "@/lib/tokens";

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight text-fg">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  );
}

export function Card({
  title,
  description,
  actions,
  children,
  className,
  padded = true,
}: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <section className={clsx("rounded-lg border border-border bg-surface", className)}>
      {(title || actions) && (
        <div className="flex items-start justify-between gap-4 px-5 pt-4">
          <div>
            {title && <h2 className="text-sm font-medium text-fg">{title}</h2>}
            {description && <p className="mt-0.5 text-xs text-muted">{description}</p>}
          </div>
          {actions}
        </div>
      )}
      <div className={clsx(padded && "p-5", title && padded && "pt-4")}>{children}</div>
    </section>
  );
}

export function Stat({
  label,
  value,
  hint,
  icon: Icon,
  tone,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: LucideIcon;
  tone?: Status;
}) {
  return (
    <div className="rounded-lg border border-border bg-surface px-5 py-4">
      <div className="flex items-center gap-2 text-xs font-medium text-muted">
        {Icon && <Icon size={14} aria-hidden style={tone ? { color: STATUS_META[tone].color } : undefined} />}
        {label}
      </div>
      <div className="mt-2 text-2xl font-semibold tracking-tight text-fg">{value}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  );
}

const STATUS_ICON: Record<Status, LucideIcon> = {
  stockout_risk: AlertTriangle,
  reorder: Clock,
  healthy: CheckCircle2,
};

/** Status is never colour alone: icon + text label, colour as a third cue. */
export function StatusBadge({
  status,
  compact = false,
  label,
}: {
  status: Status | null;
  compact?: boolean;
  label?: string;
}) {
  if (!status) return <span className="text-muted">–</span>;
  const meta = STATUS_META[status];
  const Icon = STATUS_ICON[status];
  return (
    <span
      className="inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium"
      style={{ background: meta.soft, color: meta.ink }}
    >
      <Icon size={12} aria-hidden />
      {label ?? (compact ? meta.short : meta.label)}
    </span>
  );
}

export function ClassBadge({ abc, xyz }: { abc: Abc | null; xyz?: Xyz | null }) {
  if (!abc) return <span className="text-muted">–</span>;
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded border border-border px-1.5 py-0.5 text-xs font-medium text-fg"
      title={`${CLASS_LABEL[abc]}${xyz ? ` · ${XYZ_LABEL[xyz]} demand` : ""}`}
    >
      <span aria-hidden className="size-2 rounded-sm" style={{ background: CLASS_COLOR[abc] }} />
      {abc}
      {xyz && <span className="text-muted">{xyz}</span>}
    </span>
  );
}

export function Button({
  variant = "secondary",
  size = "md",
  className,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost"; size?: "sm" | "md" }) {
  return (
    <button
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        size === "md" ? "h-9 px-3.5 text-sm" : "h-8 px-2.5 text-xs",
        variant === "primary" && "bg-accent text-accent-fg hover:opacity-90",
        variant === "secondary" && "border border-border-strong bg-surface text-fg hover:bg-surface-2",
        variant === "ghost" && "text-fg-2 hover:bg-surface-2 hover:text-fg",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("animate-pulse rounded-md bg-surface-2", className)} aria-hidden />;
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border-strong px-6 py-16 text-center">
      <h3 className="text-sm font-medium text-fg">{title}</h3>
      {children && <p className="mt-1 max-w-md text-sm text-muted">{children}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : "Something went wrong";
  return (
    <div role="alert" className="rounded-md border border-border bg-risk-soft px-4 py-3 text-sm text-risk-ink">
      {message}
    </div>
  );
}

export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: ReactNode }[];
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-md border border-border bg-surface p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={clsx(
            "h-7 rounded px-2.5 text-xs font-medium transition-colors",
            value === o.value ? "bg-surface-2 text-fg shadow-[inset_0_0_0_1px_var(--border)]" : "text-muted hover:text-fg",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/* Tables: right-aligned tabular numbers, thin row dividers. */
export function Th({ children, align = "left", className }: { children?: ReactNode; align?: "left" | "right"; className?: string }) {
  return (
    <th
      scope="col"
      className={clsx(
        "h-9 whitespace-nowrap border-b border-border px-3 text-xs font-medium text-muted first:pl-5 last:pr-5",
        align === "right" ? "text-right" : "text-left",
        className,
      )}
    >
      {children}
    </th>
  );
}

export function Td({
  children,
  align = "left",
  className,
  colSpan,
}: {
  children?: ReactNode;
  align?: "left" | "right";
  className?: string;
  colSpan?: number;
}) {
  return (
    <td
      colSpan={colSpan}
      className={clsx(
        "h-11 whitespace-nowrap border-b border-border px-3 text-sm first:pl-5 last:pr-5",
        align === "right" && "num text-right",
        className,
      )}
    >
      {children}
    </td>
  );
}

export function Verdict({ verdict }: { verdict: "dominates" | "better" | "trade-off" | "worse" }) {
  const map = {
    dominates: { label: "Dominates uniform", status: "healthy" as Status },
    better: { label: "Better", status: "healthy" as Status },
    "trade-off": { label: "Trade-off", status: "reorder" as Status },
    worse: { label: "Worse", status: "stockout_risk" as Status },
  }[verdict];
  const meta = STATUS_META[map.status];
  const Icon = STATUS_ICON[map.status];
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium"
      style={{ background: meta.soft, color: meta.ink }}
    >
      <Icon size={12} aria-hidden />
      {map.label}
    </span>
  );
}
