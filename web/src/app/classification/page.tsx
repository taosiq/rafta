"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { ParetoChart } from "@/components/charts";
import { NoDataState } from "@/components/setup";
import { Card, ClassBadge, ErrorNote, PageHeader, Segmented, Skeleton, Td, Th } from "@/components/ui";
import type { Abc, ClassificationResponse, Xyz } from "@/lib/api";
import { money, num, pct } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { CLASS_COLOR, CLASS_LABEL, XYZ_LABEL } from "@/lib/tokens";

const ABC: Abc[] = ["A", "B", "C"];
const XYZ: Xyz[] = ["X", "Y", "Z"];

const GUIDANCE: Record<string, string> = {
  AX: "Tight control, high service, frequent review",
  AY: "High service, buffer for variability",
  AZ: "High value but erratic: review manually",
  BX: "Automate replenishment",
  BY: "Automate with moderate safety stock",
  BZ: "Consider make-to-order",
  CX: "Bulk order, low attention",
  CY: "Lower service is acceptable",
  CZ: "Candidate to delist or order on demand",
};

export default function ClassificationPage() {
  const { data, error } = useApi<ClassificationResponse>("/classification");
  const [metric, setMetric] = useState<"skus" | "revenue">("revenue");
  const [cell, setCell] = useState<string | null>(null);

  const items = useMemo(
    () => (data?.items ?? []).filter((i) => !cell || `${i.abc}${i.xyz}` === cell),
    [data, cell],
  );

  if (error) return <ErrorNote error={error} />;
  if (!data) return <Skeleton className="h-[600px]" />;
  if (data.items.length === 0)
    return (
      <>
        <PageHeader title="ABC / XYZ classification" />
        <NoDataState what="classification" />
      </>
    );

  const total = data.items.length;
  const maxValue = Math.max(
    ...Object.values(data.matrix).map((m) => (metric === "skus" ? m.skus / total : m.revenue_share)),
  );

  return (
    <>
      <PageHeader
        title="ABC / XYZ classification"
        description="ABC ranks SKUs by 12-month revenue (A = top 80%, B = next 15%, C = rest). XYZ ranks by the variability of weekly demand (coefficient of variation: X ≤ 0.5, Y ≤ 1.0, Z > 1.0)."
      />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
        <Card
          className="xl:col-span-3"
          title="Classification matrix"
          description="Select a cell to filter the table below"
          actions={
            <Segmented
              label="Matrix metric"
              value={metric}
              onChange={setMetric}
              options={[
                { value: "revenue", label: "Revenue share" },
                { value: "skus", label: "SKU count" },
              ]}
            />
          }
        >
          <div className="grid grid-cols-[auto_repeat(3,minmax(0,1fr))] gap-0.5" role="grid" aria-label="ABC by XYZ matrix">
            <div />
            {XYZ.map((x) => (
              <div key={x} className="px-2 pb-2 text-center text-xs text-muted" role="columnheader">
                <span className="font-medium text-fg">{x}</span> · {XYZ_LABEL[x]}
              </div>
            ))}
            {ABC.map((a) => (
              <div key={a} className="contents" role="row">
                <div className="flex items-center gap-2 pr-3 text-xs" role="rowheader">
                  <span className="size-2.5 rounded-sm" style={{ background: CLASS_COLOR[a] }} aria-hidden />
                  <span className="font-medium text-fg">{a}</span>
                  <span className="hidden text-muted sm:inline">{CLASS_LABEL[a]}</span>
                </div>
                {XYZ.map((x) => {
                  const key = `${a}${x}`;
                  const m = data.matrix[key] ?? { skus: 0, revenue_share: 0 };
                  const value = metric === "skus" ? m.skus / total : m.revenue_share;
                  const intensity = maxValue > 0 ? value / maxValue : 0;
                  const dark = intensity > 0.55;
                  const active = cell === key;
                  return (
                    <button
                      key={key}
                      role="gridcell"
                      aria-selected={active}
                      onClick={() => setCell(active ? null : key)}
                      title={GUIDANCE[key]}
                      className="flex h-24 flex-col items-start justify-between rounded-md p-3 text-left transition-shadow"
                      style={{
                        background: `color-mix(in oklab, var(--accent) ${Math.round(8 + intensity * 72)}%, var(--surface))`,
                        color: dark ? "var(--accent-fg)" : "var(--fg)",
                        boxShadow: active ? "inset 0 0 0 2px var(--fg)" : undefined,
                      }}
                    >
                      <span className="text-xs font-medium opacity-80">{key}</span>
                      <span>
                        <span className="num block text-lg font-semibold">{metric === "skus" ? m.skus : pct(m.revenue_share, 1)}</span>
                        <span className="num text-xs opacity-80">
                          {metric === "skus" ? `${pct(m.revenue_share, 0)} of revenue` : `${m.skus} SKUs`}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </Card>

        <Card className="xl:col-span-2" title="Pareto curve" description="Cumulative revenue share by share of SKUs">
          <ParetoChart data={data.pareto} />
          <p className="mt-2 text-xs text-muted">
            {pct(data.pareto.filter((p) => p.abc === "A").length / total, 0)} of SKUs generate{" "}
            {pct(data.pareto.filter((p) => p.abc === "A").at(-1)?.revenue_share ?? 0, 0)} of revenue.
          </p>
        </Card>
      </div>

      <Card className="mt-6" padded={false} title="Policy guidance by segment" description="How each cell is typically managed">
        <div className="mt-3 grid grid-cols-1 gap-px bg-border sm:grid-cols-3">
          {ABC.flatMap((a) =>
            XYZ.map((x) => (
              <div key={`${a}${x}`} className="bg-surface px-5 py-3 text-sm">
                <ClassBadge abc={a} xyz={x} /> <span className="ml-2 text-fg-2">{GUIDANCE[`${a}${x}`]}</span>
              </div>
            )),
          )}
        </div>
      </Card>

      <Card
        className="mt-6"
        padded={false}
        title={cell ? `Products in ${cell}` : "All products"}
        description={`${items.length} SKUs, sorted by revenue`}
        actions={
          cell && (
            <button className="text-xs text-fg-2 hover:text-fg" onClick={() => setCell(null)}>
              Clear filter
            </button>
          )
        }
      >
        <div className="mt-3 max-h-[480px] overflow-auto">
          <table className="w-full">
            <thead className="sticky top-0 bg-surface">
              <tr>
                <Th>Product</Th>
                <Th>Class</Th>
                <Th align="right">Revenue</Th>
                <Th align="right">Share</Th>
                <Th align="right">Cumulative</Th>
                <Th align="right">CV (weekly)</Th>
                <Th align="right">Avg interval (d)</Th>
              </tr>
            </thead>
            <tbody>
              {items.map((i) => (
                <tr key={i.sku} className="hover:bg-surface-2">
                  <Td>
                    <Link href={`/products/${i.sku}`} className="font-medium hover:underline">
                      {i.name}
                    </Link>
                    <span className="num ml-2 text-xs text-muted">{i.sku}</span>
                  </Td>
                  <Td>
                    <ClassBadge abc={i.abc} xyz={i.xyz} />
                  </Td>
                  <Td align="right">{money(i.revenue)}</Td>
                  <Td align="right">{pct(i.revenue_share, 2)}</Td>
                  <Td align="right">{pct(i.cumulative_share, 1)}</Td>
                  <Td align="right">{i.cv >= 99 ? "∞" : num(i.cv, 2)}</Td>
                  <Td align="right">{num(i.adi, 1)}</Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
