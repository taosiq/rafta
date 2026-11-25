"use client";

import { Loader2, Play } from "lucide-react";

import { HBarChart } from "@/components/charts";
import { NoDataState } from "@/components/setup";
import { Button, Card, ClassBadge, ErrorNote, PageHeader, Skeleton, Stat, Td, Th } from "@/components/ui";
import type { Abc, ForecastSummary, Xyz } from "@/lib/api";
import { longDate, num, pct } from "@/lib/format";
import { useApi, useJobRunner } from "@/lib/hooks";
import { MODEL_LABEL, XYZ_LABEL } from "@/lib/tokens";

export default function ForecastsPage() {
  const { data, error } = useApi<ForecastSummary>("/forecasts/summary");
  const runner = useJobRunner();

  if (error) return <ErrorNote error={error} />;
  if (!data) return <Skeleton className="h-[600px]" />;
  if (!data.run)
    return (
      <>
        <PageHeader title="Forecasts" />
        <NoDataState what="forecasts" />
      </>
    );

  const { run } = data;
  const s = run.summary;
  const models = Object.entries(s.per_model).sort((a, b) => a[1].median_mase - b[1].median_mase);
  const best = models[0]?.[0];
  const xyzModels = Array.from(new Set(data.wape_by_xyz.map((r) => r.model)));
  const cellFor = (x: Xyz, m: string) => data.wape_by_xyz.find((r) => r.xyz === x && r.model === m);

  return (
    <>
      <PageHeader
        title="Forecasts"
        description={
          <>
            Run #{run.id} · history to {longDate(run.history_end)} · {run.horizon_days}-day horizon · {run.folds}{" "}
            rolling-origin folds. Each SKU uses whichever model had the lowest backtest MASE.
          </>
        }
        actions={
          <Button onClick={() => runner.run("refresh")} disabled={runner.busy}>
            {runner.busy ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            {runner.busy ? `Running (${runner.job?.status})…` : "Re-run forecasts"}
          </Button>
        }
      />
      {runner.error && <ErrorNote error={new Error(runner.error)} />}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Weighted WAPE" value={<span className="num">{pct(s.selected.weighted_wape, 1)}</span>} hint="Volume-weighted absolute error" />
        <Stat label="Median MASE" value={<span className="num">{num(s.selected.median_mase, 3)}</span>} hint="Below 1 beats seasonal naive" />
        <Stat
          label="vs seasonal naive"
          value={<span className="num">{pct(s.selected.improvement_vs_naive, 0)}</span>}
          hint="Reduction in median MASE"
        />
        <Stat label="Bias" value={<span className="num">{pct(s.selected.weighted_bias, 1, true)}</span>} hint="Positive = over-forecasting" />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card title="Model leaderboard" description="Median MASE across SKUs (lower is better)">
          <HBarChart
            data={models.map(([m, v]) => ({ label: MODEL_LABEL[m] ?? m, value: v.median_mase }))}
            format={(v) => num(v, 3)}
            color="var(--reference)"
            highlight={MODEL_LABEL[best] ?? best}
          />
        </Card>

        <Card padded={false} title="Per-model accuracy" description="Backtest across all SKUs">
          <div className="mt-3 overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr>
                  <Th>Model</Th>
                  <Th align="right">Median MASE</Th>
                  <Th align="right">Weighted WAPE</Th>
                  <Th align="right">Bias</Th>
                  <Th align="right">Chosen for</Th>
                </tr>
              </thead>
              <tbody>
                {models.map(([m, v]) => (
                  <tr key={m}>
                    <Td>
                      <span className="font-medium">{MODEL_LABEL[m] ?? m}</span>
                      <div className="text-xs text-muted">{data.models.find((x) => x.name === m)?.description}</div>
                    </Td>
                    <Td align="right">{num(v.median_mase, 3)}</Td>
                    <Td align="right">{pct(v.weighted_wape, 1)}</Td>
                    <Td align="right">{pct(v.mean_bias, 1, true)}</Td>
                    <Td align="right">{s.selected_counts[m] ?? 0} SKUs</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card padded={false} title="Accuracy by ABC class" description="Selected model per SKU">
          <table className="mt-3 w-full">
            <thead>
              <tr>
                <Th>Class</Th>
                <Th align="right">SKUs</Th>
                <Th align="right">Median MASE</Th>
                <Th align="right">Weighted WAPE</Th>
              </tr>
            </thead>
            <tbody>
              {(["A", "B", "C"] as Abc[]).map((c) => {
                const v = s.by_class[c];
                if (!v) return null;
                return (
                  <tr key={c}>
                    <Td>
                      <ClassBadge abc={c} />
                    </Td>
                    <Td align="right">{v.skus}</Td>
                    <Td align="right">{num(v.median_mase, 3)}</Td>
                    <Td align="right">{pct(v.weighted_wape, 1)}</Td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="px-5 py-3 text-xs text-muted">
            A items are high-volume and usually most predictable in relative terms; C items are often intermittent.
          </p>
        </Card>

        <Card padded={false} title="Mean WAPE by variability class" description="Which model works for which demand pattern">
          <div className="mt-3 overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr>
                  <Th>Model</Th>
                  {(["X", "Y", "Z"] as Xyz[]).map((x) => (
                    <Th key={x} align="right">
                      {x} · {XYZ_LABEL[x]}
                    </Th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {xyzModels.map((m) => {
                  const best = (["X", "Y", "Z"] as Xyz[]).map(
                    (x) => Math.min(...xyzModels.map((mm) => cellFor(x, mm)?.wape ?? Infinity)),
                  );
                  return (
                    <tr key={m}>
                      <Td className="font-medium">{MODEL_LABEL[m] ?? m}</Td>
                      {(["X", "Y", "Z"] as Xyz[]).map((x, i) => {
                        const c = cellFor(x, m);
                        const isBest = c && c.wape === best[i];
                        return (
                          <Td key={x} align="right" className={isBest ? "font-semibold text-accent" : undefined}>
                            {c ? pct(c.wape, 1) : "–"}
                          </Td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="px-5 py-3 text-xs text-muted">Best model per column in bold. Unweighted mean across SKUs.</p>
        </Card>
      </div>
    </>
  );
}
