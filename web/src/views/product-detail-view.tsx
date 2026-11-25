"use client";

import { ArrowLeft, Check } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";

import { ForecastChart, type ForecastPoint } from "@/components/charts";
import { Card, ClassBadge, ErrorNote, PageHeader, Segmented, Skeleton, StatusBadge, Td, Th } from "@/components/ui";
import type { ProductDetail } from "@/lib/api";
import { longDate, money, num, pct } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { CLASS_LABEL, XYZ_LABEL } from "@/lib/tokens";

export function ProductDetailView() {
  const { sku } = useParams<{ sku: string }>();
  const [range, setRange] = useState<"90" | "180" | "365">("90");
  const { data, error } = useApi<ProductDetail>(`/products/${encodeURIComponent(sku)}?history_days=365`);

  const chartData = useMemo<ForecastPoint[]>(() => {
    if (!data) return [];
    const hist = data.history.slice(-Number(range)).map((h) => ({ date: h.date, actual: h.actual }));
    const fc = data.forecast.map((f) => ({ date: f.date, forecast: f.forecast, band: [f.lower, f.upper] as [number, number] }));
    // Connect the forecast line to the last actual so there is no visual gap.
    if (hist.length && fc.length) {
      const last = hist[hist.length - 1];
      Object.assign(last, { forecast: last.actual });
    }
    return [...hist, ...fc];
  }, [data, range]);

  if (error) return <ErrorNote error={error} />;
  if (!data)
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-12 w-80" />
        <Skeleton className="h-96" />
      </div>
    );

  const p = data.product;
  const leadDemand = (p.avg_daily_demand ?? 0) * p.lead_time_days;
  const horizonTotal = data.forecast.reduce((s, f) => s + f.forecast, 0);
  const selected = data.backtest.find((b) => b.selected);

  return (
    <>
      <Link href="/products" className="mb-4 inline-flex items-center gap-1 text-sm text-fg-2 hover:text-fg">
        <ArrowLeft size={14} /> Products
      </Link>
      <PageHeader
        title={p.name}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <span className="num">{p.sku}</span>· {p.category} ·
            <ClassBadge abc={p.abc} xyz={p.xyz} />
            {p.abc && p.xyz && (
              <span>
                {CLASS_LABEL[p.abc]}, {XYZ_LABEL[p.xyz].toLowerCase()} demand
              </span>
            )}
          </span>
        }
        actions={<StatusBadge status={p.status} />}
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Fact label="On hand" value={num(p.on_hand)} hint={p.on_order ? `${num(p.on_order)} on order` : "Nothing on order"} />
        <Fact label="Days of cover" value={num(p.days_of_cover, 1)} hint={p.stockout_date ? `Runs out ${longDate(p.stockout_date)}` : "No stock-out within the forecast horizon"} />
        <Fact label="Reorder point" value={num(p.reorder_point)} hint={`${num(leadDemand)} lead-time demand + ${num(p.safety_stock)} safety stock`} />
        <Fact
          label="Suggested order"
          value={p.suggested_order_qty ? num(p.suggested_order_qty) : "–"}
          hint={p.suggested_order_qty ? `${money((p.suggested_order_qty ?? 0) * p.unit_cost)} at cost` : `EOQ ${num(p.eoq)} units`}
        />
      </div>

      <Card
        className="mt-6"
        title="Demand and forecast"
        description={`Next ${data.forecast.length} days: ${num(horizonTotal)} units expected · model: ${selected?.label ?? "–"}`}
        actions={
          <Segmented
            label="History range"
            value={range}
            onChange={setRange}
            options={[
              { value: "90", label: "90d" },
              { value: "180", label: "180d" },
              { value: "365", label: "1y" },
            ]}
          />
        }
      >
        <ForecastChart data={chartData} reorderPoint={p.reorder_point} />
      </Card>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2" padded={false} title="Backtest: model comparison" description="Rolling-origin evaluation. The lowest MASE wins and is used for planning.">
          <div className="mt-3 overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr>
                  <Th>Model</Th>
                  <Th align="right">MASE</Th>
                  <Th align="right">WAPE</Th>
                  <Th align="right">MAE</Th>
                  <Th align="right">RMSE</Th>
                  <Th align="right">Bias</Th>
                </tr>
              </thead>
              <tbody>
                {data.backtest.map((b) => (
                  <tr key={b.model} className={b.selected ? "bg-accent-soft" : undefined}>
                    <Td>
                      <span className="inline-flex items-center gap-1.5 font-medium">
                        {b.label}
                        {b.selected && (
                          <span className="inline-flex items-center gap-0.5 text-xs text-accent">
                            <Check size={12} aria-hidden /> selected
                          </span>
                        )}
                      </span>
                    </Td>
                    <Td align="right">{num(b.mase, 3)}</Td>
                    <Td align="right">{pct(b.wape, 1)}</Td>
                    <Td align="right">{num(b.mae, 2)}</Td>
                    <Td align="right">{num(b.rmse, 2)}</Td>
                    <Td align="right">{pct(b.bias, 1, true)}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="px-5 py-3 text-xs text-muted">
            MASE below 1 beats the seasonal-naive benchmark. RMSE of the selected model feeds the safety stock.
          </p>
        </Card>

        <Card title="Replenishment parameters">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
            <Param k="Service level" v={pct(p.service_level, 1)} />
            <Param k="Lead time" v={`${p.lead_time_days} d ± ${num(data.params.lead_time_std_days, 1)}`} />
            <Param k="Demand / day" v={num(p.avg_daily_demand, 2)} />
            <Param k="Safety stock" v={num(p.safety_stock)} />
            <Param k="EOQ" v={num(p.eoq)} />
            <Param k="MOQ" v={num(data.params.moq)} />
            <Param k="Unit cost" v={money(p.unit_cost)} />
            <Param k="Unit price" v={money(p.unit_price)} />
            <Param k="Order cost" v={money(data.params.order_cost)} />
            <Param k="Holding rate" v={`${pct(data.params.holding_rate, 0)} / yr`} />
            <Param k="Demand CV" v={num(p.cv, 2)} />
            <Param k="Avg demand interval" v={`${num(data.adi, 1)} d`} />
          </dl>
          <p className="mt-4 text-xs text-muted">
            ROP = d·L + z·√(L·σ² + d²·σ<sub>L</sub>²). EOQ = √(2DS / H).
          </p>
        </Card>
      </div>
    </>
  );
}

function Fact({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface px-4 py-3">
      <div className="text-xs text-muted">{label}</div>
      <div className="num mt-1 text-xl font-semibold">{value}</div>
      <div className="mt-0.5 text-xs text-muted">{hint}</div>
    </div>
  );
}

function Param({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <dt className="text-xs text-muted">{k}</dt>
      <dd className="num">{v}</dd>
    </div>
  );
}
