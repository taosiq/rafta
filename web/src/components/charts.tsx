"use client";

import type { ReactNode } from "react";
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts";

import type { Abc } from "@/lib/api";
import { compact, money, num, pct, shortDate } from "@/lib/format";
import { CLASS_COLOR, policyColor } from "@/lib/tokens";

/* ------------------------------------------------------------------ shared */

type Row = { label: string; value: string; color?: string; dashed?: boolean };

/** One tooltip, every series. Values lead (strong), labels follow; keys are line strokes. */
function TooltipBox({ title, rows }: { title?: ReactNode; rows: Row[] }) {
  return (
    <div className="min-w-40 rounded-md border border-border bg-surface px-3 py-2 text-xs shadow-sm">
      {title && <div className="mb-1.5 font-medium text-fg">{title}</div>}
      <div className="flex flex-col gap-1">
        {rows.map((r) => (
          <div key={r.label} className="flex items-center gap-2">
            {r.color && (
              <svg width="14" height="4" aria-hidden className="shrink-0">
                <line
                  x1="1"
                  y1="2"
                  x2="13"
                  y2="2"
                  stroke={r.color}
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeDasharray={r.dashed ? "3 3" : undefined}
                />
              </svg>
            )}
            <span className="num font-semibold text-fg">{r.value}</span>
            <span className="text-muted">{r.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function Legend({ items }: { items: { label: string; color: string; dashed?: boolean; band?: boolean }[] }) {
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-fg-2">
      {items.map((i) => (
        <li key={i.label} className="flex items-center gap-1.5">
          {i.band ? (
            <span aria-hidden className="h-2.5 w-3.5 rounded-sm" style={{ background: i.color, opacity: 0.18 }} />
          ) : (
            <svg width="16" height="4" aria-hidden>
              <line
                x1="1"
                y1="2"
                x2="15"
                y2="2"
                stroke={i.color}
                strokeWidth="2"
                strokeLinecap="round"
                strokeDasharray={i.dashed ? "3 3" : undefined}
              />
            </svg>
          )}
          {i.label}
        </li>
      ))}
    </ul>
  );
}

const axisProps = { tickLine: false, axisLine: false, tickMargin: 8 } as const;
const cursor = { stroke: "var(--axis)", strokeWidth: 1 };

/* ------------------------------------------------------------ forecast chart */

export interface ForecastPoint {
  date: string;
  actual?: number;
  forecast?: number;
  band?: [number, number];
}

export function ForecastChart({ data, reorderPoint }: { data: ForecastPoint[]; reorderPoint?: number | null }) {
  const splitAt = data.find((d) => d.forecast !== undefined)?.date;
  return (
    <div className="flex flex-col gap-3">
      <Legend
        items={[
          { label: "Actual demand", color: "var(--fg-2)" },
          { label: "Forecast", color: "var(--accent)" },
          { label: "80% interval", color: "var(--accent)", band: true },
        ]}
      />
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
            <CartesianGrid vertical={false} />
            <XAxis dataKey="date" tickFormatter={shortDate} minTickGap={40} {...axisProps} />
            <YAxis tickFormatter={(v) => compact(v)} width={48} {...axisProps} />
            <Tooltip
              cursor={cursor}
              content={({ active, payload, label }: TooltipContentProps) => {
                if (!active || !payload?.length) return null;
                const p = payload[0].payload as ForecastPoint;
                const rows: Row[] = [];
                if (p.actual !== undefined) rows.push({ label: "actual", value: num(p.actual, 1), color: "var(--fg-2)" });
                if (p.forecast !== undefined)
                  rows.push({ label: "forecast", value: num(p.forecast, 1), color: "var(--accent)" });
                if (p.band) rows.push({ label: "80% interval", value: `${num(p.band[0], 1)}–${num(p.band[1], 1)}` });
                return <TooltipBox title={shortDate(String(label))} rows={rows} />;
              }}
            />
            {splitAt && <ReferenceLine x={splitAt} stroke="var(--axis)" />}
            <Area
              dataKey="band"
              stroke="none"
              fill="var(--accent)"
              fillOpacity={0.12}
              isAnimationActive={false}
              activeDot={false}
            />
            <Line
              dataKey="actual"
              stroke="var(--fg-2)"
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
              activeDot={{ r: 4, stroke: "var(--surface)", strokeWidth: 2 }}
            />
            <Line
              dataKey="forecast"
              stroke="var(--accent)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              activeDot={{ r: 4, stroke: "var(--surface)", strokeWidth: 2 }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      {reorderPoint != null && (
        <p className="text-xs text-muted">Vertical line marks the end of history; forecasts start after it.</p>
      )}
    </div>
  );
}

/* --------------------------------------------------------------- pareto curve */

export function ParetoChart({ data }: { data: { sku_share: number; revenue_share: number; abc: Abc }[] }) {
  const boundaries = (["A", "B"] as Abc[])
    .map((c) => {
      const last = [...data].reverse().find((d) => d.abc === c);
      return last ? { abc: c, x: last.sku_share } : null;
    })
    .filter(Boolean) as { abc: Abc; x: number }[];
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 16, right: 12, bottom: 0, left: -8 }}>
          <CartesianGrid vertical={false} />
          <XAxis
            dataKey="sku_share"
            type="number"
            domain={[0, 1]}
            ticks={[0, 0.2, 0.4, 0.6, 0.8, 1]}
            tickFormatter={(v) => pct(v, 0)}
            {...axisProps}
          />
          <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tickFormatter={(v) => pct(v, 0)} width={48} {...axisProps} />
          <Tooltip
            cursor={cursor}
            content={({ active, payload }: TooltipContentProps) => {
              if (!active || !payload?.length) return null;
              const p = payload[0].payload as { sku_share: number; revenue_share: number; abc: Abc };
              return (
                <TooltipBox
                  title={`Class ${p.abc}`}
                  rows={[
                    { label: "of SKUs", value: pct(p.sku_share, 0) },
                    { label: "of revenue", value: pct(p.revenue_share, 1), color: CLASS_COLOR[p.abc] },
                  ]}
                />
              );
            }}
          />
          {boundaries.map((b) => (
            <ReferenceLine
              key={b.abc}
              x={b.x}
              stroke="var(--axis)"
              label={{ value: `${b.abc} | ${b.abc === "A" ? "B" : "C"}`, position: "top", fill: "var(--muted)", fontSize: 11 }}
            />
          ))}
          <Line
            dataKey="revenue_share"
            stroke="var(--fg-2)"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
            activeDot={{ r: 4, stroke: "var(--surface)", strokeWidth: 2 }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

/* ---------------------------------------------- cost vs fill-rate frontier */

export interface FrontierPoint {
  fill_rate: number;
  total_cost: number;
  service_level?: number;
}

export function FrontierChart({
  frontier,
  policies,
}: {
  frontier: FrontierPoint[];
  policies: { name: string; fill_rate: number; total_cost: number }[];
}) {
  const line = [...frontier].sort((a, b) => a.fill_rate - b.fill_rate);
  const allCost = [...line.map((p) => p.total_cost), ...policies.map((p) => p.total_cost)];
  const allFill = [...line.map((p) => p.fill_rate), ...policies.map((p) => p.fill_rate)];
  const pad = (max: number, min: number) => (max - min) * 0.08 || max * 0.02;
  const yDomain = [Math.min(...allCost) - pad(Math.max(...allCost), Math.min(...allCost)), Math.max(...allCost) + pad(Math.max(...allCost), Math.min(...allCost))];
  const xDomain = [Math.min(...allFill) - pad(Math.max(...allFill), Math.min(...allFill)), Math.min(1, Math.max(...allFill) + pad(Math.max(...allFill), Math.min(...allFill)))];

  return (
    <div className="flex flex-col gap-3">
      <Legend
        items={[
          { label: "Uniform policy at 75%–99.5% service", color: "var(--reference)", dashed: true },
          ...policies.map((p, i) => ({ label: p.name, color: policyColor(i) })),
        ]}
      />
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart margin={{ top: 8, right: 16, bottom: 8, left: 4 }}>
            <CartesianGrid vertical={false} />
            <XAxis
              type="number"
              dataKey="fill_rate"
              domain={xDomain}
              tickFormatter={(v) => pct(v, 1)}
              label={{ value: "Fill rate (higher is better)", position: "insideBottom", offset: -4, fill: "var(--muted)", fontSize: 11 }}
              height={40}
              {...axisProps}
            />
            <YAxis
              type="number"
              dataKey="total_cost"
              domain={yDomain}
              tickFormatter={(v) => money(v, { compact: true })}
              width={64}
              {...axisProps}
            />
            <Tooltip
              cursor={false}
              content={({ active, payload }: TooltipContentProps) => {
                if (!active || !payload?.length) return null;
                const p = payload[0].payload as FrontierPoint & { name?: string };
                return (
                  <TooltipBox
                    title={p.name ?? `Uniform ${pct(p.service_level ?? 0, 1)} service`}
                    rows={[
                      { label: "total cost", value: money(p.total_cost) },
                      { label: "fill rate", value: pct(p.fill_rate, 2) },
                    ]}
                  />
                );
              }}
            />
            <Line
              data={line}
              dataKey="total_cost"
              stroke="var(--reference)"
              strokeWidth={2}
              strokeDasharray="4 4"
              dot={{ r: 3, fill: "var(--reference)", stroke: "var(--surface)", strokeWidth: 2 }}
              activeDot={{ r: 5, stroke: "var(--surface)", strokeWidth: 2 }}
              isAnimationActive={false}
            />
            {policies.map((p, i) => (
              <Scatter
                key={p.name}
                data={[p]}
                fill={policyColor(i)}
                isAnimationActive={false}
                shape={(props: unknown) => {
                  const { cx, cy } = props as { cx: number; cy: number };
                  // 12px marker with a 2px surface ring: larger than the frontier dots
                  return <circle cx={cx} cy={cy} r={6} fill={policyColor(i)} stroke="var(--surface)" strokeWidth={2} />;
                }}
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="text-xs text-muted">
        A policy below the dashed line is cheaper than a uniform policy that delivers the same fill rate.
      </p>
    </div>
  );
}

/* --------------------------------------------- stacked cost breakdown bars */

export function CostBreakdownChart({
  rows,
}: {
  rows: { name: string; holding: number; ordering: number; shortage: number }[];
}) {
  const parts = [
    { key: "holding", label: "Holding", color: "var(--seq-700)" },
    { key: "ordering", label: "Ordering", color: "var(--reference)" }, // neutral: violet is a policy colour on this page
    { key: "shortage", label: "Lost sales", color: "var(--risk)" },
  ] as const;
  return (
    <div className="flex flex-col gap-3">
      <Legend items={parts.map((p) => ({ label: p.label, color: p.color }))} />
      <div style={{ height: rows.length * 56 + 40 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 0 }} barSize={22}>
            <CartesianGrid horizontal={false} />
            <XAxis type="number" tickFormatter={(v) => money(v, { compact: true })} {...axisProps} />
            <YAxis type="category" dataKey="name" width={120} {...axisProps} tick={{ fill: "var(--fg-2)", fontSize: 12 }} />
            <Tooltip
              cursor={{ fill: "var(--surface-2)" }}
              content={({ active, payload, label }: TooltipContentProps) => {
                if (!active || !payload?.length) return null;
                const r = payload[0].payload as (typeof rows)[number];
                return (
                  <TooltipBox
                    title={String(label)}
                    rows={[
                      ...parts.map((p) => ({ label: p.label.toLowerCase(), value: money(r[p.key]), color: p.color })),
                      { label: "total", value: money(r.holding + r.ordering + r.shortage) },
                    ]}
                  />
                );
              }}
            />
            {parts.map((p, i) => (
              <Bar
                key={p.key}
                dataKey={p.key}
                stackId="cost"
                fill={p.color}
                stroke="var(--surface)"
                strokeWidth={2}
                radius={i === parts.length - 1 ? [0, 4, 4, 0] : 0}
                isAnimationActive={false}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/* --------------------------------------------- inventory value trajectory */

export function TrajectoryChart({ series, start }: { series: { name: string; values: number[] }[]; start: string }) {
  const startMs = Date.parse(`${start}T00:00:00Z`);
  const data = (series[0]?.values ?? []).map((_, t) => {
    const row: Record<string, number | string> = { date: new Date(startMs + t * 86_400_000).toISOString().slice(0, 10) };
    series.forEach((s) => (row[s.name] = s.values[t]));
    return row;
  });
  return (
    <div className="flex flex-col gap-3">
      <Legend items={series.map((s, i) => ({ label: s.name, color: policyColor(i) }))} />
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 4 }}>
            <CartesianGrid vertical={false} />
            <XAxis dataKey="date" tickFormatter={shortDate} minTickGap={48} {...axisProps} />
            <YAxis tickFormatter={(v) => money(v, { compact: true })} width={64} {...axisProps} />
            <Tooltip
              cursor={cursor}
              content={({ active, payload, label }: TooltipContentProps) => {
                if (!active || !payload?.length) return null;
                return (
                  <TooltipBox
                    title={shortDate(String(label))}
                    rows={series.map((s, i) => ({
                      label: s.name,
                      value: money(Number(payload[0].payload[s.name]), { compact: true }),
                      color: policyColor(i),
                    }))}
                  />
                );
              }}
            />
            {series.map((s, i) => (
              <Line
                key={s.name}
                dataKey={s.name}
                stroke={policyColor(i)}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, stroke: "var(--surface)", strokeWidth: 2 }}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/* ------------------------------------------------ simple horizontal bars */

export function HBarChart({
  data,
  format,
  color = "var(--accent)",
  highlight,
}: {
  data: { label: string; value: number; color?: string }[];
  format: (v: number) => string;
  color?: string;
  highlight?: string;
}) {
  return (
    <div style={{ height: data.length * 36 + 24 }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 56, bottom: 0, left: 0 }} barSize={18}>
          <XAxis type="number" hide domain={[0, "dataMax"]} />
          <YAxis type="category" dataKey="label" width={72} {...axisProps} tick={{ fill: "var(--fg-2)", fontSize: 12 }} />
          <Tooltip
            cursor={{ fill: "var(--surface-2)" }}
            content={({ active, payload, label }: TooltipContentProps) =>
              active && payload?.length ? (
                <TooltipBox title={String(label)} rows={[{ label: "", value: format(Number(payload[0].value)) }]} />
              ) : null
            }
          />
          <Bar
            dataKey="value"
            radius={[0, 4, 4, 0]}
            isAnimationActive={false}
            label={{ position: "right", fill: "var(--fg-2)", fontSize: 12, formatter: (v: unknown) => format(Number(v)) }}
            shape={(props: unknown) => {
              const p = props as { x: number; y: number; width: number; height: number; payload: { label: string; color?: string } };
              const fill = p.payload.color ?? (highlight && p.payload.label === highlight ? "var(--accent)" : color);
              const r = Math.min(4, p.width / 2);
              const w = Math.max(p.width, 0);
              return (
                <path
                  d={`M${p.x},${p.y} h${Math.max(w - r, 0)} a${r},${r} 0 0 1 ${r},${r} v${p.height - 2 * r} a${r},${r} 0 0 1 -${r},${r} h-${Math.max(w - r, 0)} Z`}
                  fill={fill}
                />
              );
            }}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/* ------------------------------------------------------------- sparkline */

export function Sparkline({ values, label }: { values: number[]; label: string }) {
  const data = values.map((v, i) => ({ i, v }));
  return (
    <div className="h-10 w-full" role="img" aria-label={label}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
          <YAxis hide domain={["dataMin", "dataMax"]} />
          <Tooltip
            cursor={cursor}
            content={({ active, payload }: TooltipContentProps) =>
              active && payload?.length ? (
                <TooltipBox rows={[{ label: "units / week", value: num(Number(payload[0].value)) }]} />
              ) : null
            }
          />
          <Line dataKey="v" stroke="var(--accent)" strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
