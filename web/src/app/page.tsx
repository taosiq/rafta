"use client";

import { AlertTriangle, ArrowRight, Clock, Package, Target } from "lucide-react";
import Link from "next/link";

import { HBarChart, Sparkline } from "@/components/charts";
import { NoDataState } from "@/components/setup";
import {
  Card,
  ClassBadge,
  ErrorNote,
  PageHeader,
  Skeleton,
  Stat,
  StatusBadge,
  Td,
  Th,
  Verdict,
} from "@/components/ui";
import type { Abc, Overview } from "@/lib/api";
import { daysBetween, longDate, money, num, pct, shortDate } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { CLASS_COLOR } from "@/lib/tokens";

export default function OverviewPage() {
  const { data, error, isLoading } = useApi<Overview>("/overview", { refreshInterval: 60_000 });

  if (error) return <ErrorNote error={error} />;
  if (isLoading || !data) return <OverviewSkeleton />;
  if (data.skus === 0 || !data.as_of)
    return (
      <>
        <PageHeader title="Overview" description="Stock health, forecast accuracy and policy results at a glance." />
        <NoDataState />
      </>
    );

  const cmp = data.simulation?.comparisons[0];
  const classes = (["A", "B", "C"] as Abc[]).filter((c) => data.by_class[c]);
  const totalRevenue = classes.reduce((s, c) => s + (data.by_class[c]?.revenue ?? 0), 0);

  return (
    <>
      <PageHeader
        title="Overview"
        description={<>Data as of {longDate(data.as_of)} · {data.skus} SKUs</>}
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Inventory value"
          icon={Package}
          value={<span className="num">{money(data.inventory_value)}</span>}
          hint={<>Open orders suggested: {money(data.suggested_order_value)}</>}
        />
        <Stat
          label="Stock-out risk"
          icon={AlertTriangle}
          tone="stockout_risk"
          value={<span className="num">{data.status_counts.stockout_risk}</span>}
          hint={<>Revenue at risk ≈ {money(data.value_at_risk)} over one lead time</>}
        />
        <Stat
          label="Reorder soon"
          icon={Clock}
          tone="reorder"
          value={<span className="num">{data.status_counts.reorder}</span>}
          hint={<>{data.status_counts.healthy} SKUs healthy</>}
        />
        <Stat
          label="Forecast error (WAPE)"
          icon={Target}
          value={<span className="num">{pct(data.forecast?.weighted_wape, 1)}</span>}
          hint={
            data.forecast ? (
              <>{pct(data.forecast.improvement_vs_naive, 0)} more accurate than seasonal naive (MASE)</>
            ) : (
              "No forecast yet"
            )
          }
        />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card
          className="xl:col-span-2"
          padded={false}
          title="Needs attention"
          description="Projected to run out within a lead time, or at the reorder point"
          actions={
            <Link
              href="/products?status=stockout_risk"
              className="inline-flex items-center gap-1 text-xs text-fg-2 hover:text-fg"
            >
              All products <ArrowRight size={12} />
            </Link>
          }
        >
          <div className="mt-3 overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr>
                  <Th>Product</Th>
                  <Th>Class</Th>
                  <Th>Status</Th>
                  <Th align="right">On hand</Th>
                  <Th align="right">Runs out</Th>
                  <Th align="right">Order qty</Th>
                </tr>
              </thead>
              <tbody>
                {data.at_risk.map((p) => (
                  <tr key={p.sku} className="hover:bg-surface-2">
                    <Td>
                      <Link href={`/products/${p.sku}`} className="block max-w-56 truncate font-medium hover:underline">
                        {p.name}
                      </Link>
                      <span className="num text-xs text-muted">{p.sku}</span>
                    </Td>
                    <Td>
                      <ClassBadge abc={p.abc} xyz={p.xyz} />
                    </Td>
                    <Td>
                      <StatusBadge status={p.status} />
                    </Td>
                    <Td align="right">{num(p.on_hand)}</Td>
                    <Td align="right">
                      {p.stockout_date ? (
                        <>
                          {shortDate(p.stockout_date)}{" "}
                          <span className="text-muted">({daysBetween(data.as_of!, p.stockout_date)}d)</span>
                        </>
                      ) : (
                        "–"
                      )}
                    </Td>
                    <Td align="right">{num(p.suggested_order_qty)}</Td>
                  </tr>
                ))}
                {data.at_risk.length === 0 && (
                  <tr>
                    <Td className="text-muted">Nothing needs attention.</Td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>

        <Card
          title="ABC vs uniform policy"
          description="Research question: does differentiating service by class beat one level for all?"
        >
          {cmp ? (
            <div className="flex flex-col gap-4">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium">{cmp.candidate}</span>
                <Verdict verdict={cmp.verdict} />
              </div>
              <dl className="grid grid-cols-2 gap-4">
                <Metric label="Total cost" value={pct(cmp.total_cost_pct, 1, true)} />
                <Metric label="Stock-out days" value={pct(cmp.stockout_days_pct, 1, true)} />
                <Metric
                  label="Saving at equal fill rate"
                  value={cmp.saving_vs_frontier_pct != null ? pct(cmp.saving_vs_frontier_pct, 1) : "–"}
                />
                <Metric
                  label="Significance"
                  value={cmp.total_cost.p_value != null ? `p = ${cmp.total_cost.p_value.toPrecision(2)}` : "–"}
                />
              </dl>
              <p className="text-xs text-muted">
                vs {cmp.baseline}, {cmp.replications} paired replications.
              </p>
              <Link href="/simulation" className="inline-flex items-center gap-1 text-sm font-medium text-accent">
                Open the experiment <ArrowRight size={14} />
              </Link>
            </div>
          ) : (
            <p className="text-sm text-muted">No simulation yet.</p>
          )}
        </Card>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2" title="Inventory value by class" description="Where the money sits">
          <HBarChart
            data={classes.map((c) => ({
              label: `Class ${c}`,
              value: data.by_class[c]!.inventory_value,
              color: CLASS_COLOR[c],
            }))}
            format={(v) => money(v, { compact: true })}
          />
          <table className="mt-4 w-full">
            <caption className="sr-only">Inventory by class</caption>
            <thead>
              <tr>
                <Th>Class</Th>
                <Th align="right">SKUs</Th>
                <Th align="right">Revenue share</Th>
                <Th align="right">Inventory value</Th>
                <Th align="right">At risk</Th>
              </tr>
            </thead>
            <tbody>
              {classes.map((c) => {
                const b = data.by_class[c]!;
                return (
                  <tr key={c}>
                    <Td>
                      <ClassBadge abc={c} />
                    </Td>
                    <Td align="right">{b.skus}</Td>
                    <Td align="right">{pct(b.revenue / (totalRevenue || 1), 1)}</Td>
                    <Td align="right">{money(b.inventory_value)}</Td>
                    <Td align="right">{b.at_risk}</Td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
        <Card title="Weekly demand" description="Units sold, last 13 weeks">
          <div className="num text-2xl font-semibold tracking-tight">
            {num(data.demand_trend.at(-2)?.units ?? 0)}
            <span className="ml-1 text-sm font-normal text-muted">units last full week</span>
          </div>
          <div className="mt-4 h-24">
            <Sparkline values={data.demand_trend.slice(0, -1).map((d) => d.units)} label="Weekly units sold" />
          </div>
          <p className="mt-3 text-xs text-muted">
            The forecast job refreshes nightly; the latest run finished {longDate(data.forecast?.created_at)}.
          </p>
        </Card>
      </div>
    </>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="num mt-0.5 text-lg font-semibold">{value}</dd>
    </div>
  );
}

function OverviewSkeleton() {
  return (
    <div className="flex flex-col gap-6">
      <Skeleton className="h-10 w-64" />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-28" />
        ))}
      </div>
      <Skeleton className="h-96" />
    </div>
  );
}
