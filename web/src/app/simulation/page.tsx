"use client";

import { FlaskConical, Loader2 } from "lucide-react";
import { useState } from "react";
import { useSWRConfig } from "swr";

import { CostBreakdownChart, FrontierChart, TrajectoryChart } from "@/components/charts";
import { NoDataState } from "@/components/setup";
import { Button, Card, ClassBadge, ErrorNote, PageHeader, Skeleton, Td, Th, Verdict } from "@/components/ui";
import { api, ApiError, type Abc, type Comparison, type SimulationResult } from "@/lib/api";
import { longDate, money, num, pct, signed } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { policyColor } from "@/lib/tokens";

export default function SimulationPage() {
  const { data, error, isLoading } = useApi<SimulationResult>("/simulations/latest", { shouldRetryOnError: false });
  const [showConfig, setShowConfig] = useState(false);

  const notFound = error instanceof ApiError && error.status === 404;
  if (error && !notFound) return <ErrorNote error={error} />;
  if (isLoading) return <Skeleton className="h-[700px]" />;

  const header = (
    <PageHeader
      title="Policy simulation"
      description="Does an ABC-differentiated service policy beat a uniform one on total cost and stock-outs? Every policy is replayed on the same held-out demand, with bootstrap replications and common random numbers."
      actions={
        <Button variant="primary" onClick={() => setShowConfig((s) => !s)}>
          <FlaskConical size={14} /> {showConfig ? "Hide settings" : "Run experiment"}
        </Button>
      }
    />
  );

  if (notFound || !data)
    return (
      <>
        {header}
        {showConfig ? <ExperimentForm onDone={() => setShowConfig(false)} /> : <NoDataState what="simulation" />}
      </>
    );

  const r = data.results;
  const policies = r.policies;

  return (
    <>
      {header}
      {showConfig && <ExperimentForm onDone={() => setShowConfig(false)} />}

      <p className="mb-4 text-xs text-muted">
        Simulation #{data.id} · {longDate(r.holdout_start)} to {longDate(r.holdout_end)} ({r.days_measured} days measured) ·{" "}
        {r.skus} SKUs (A {r.class_counts.A}, B {r.class_counts.B}, C {r.class_counts.C}) · {r.replications} replications
      </p>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {r.comparisons.map((c) => (
          <Answer key={c.candidate} c={c} />
        ))}
      </div>

      <Card className="mt-6" padded={false} title="Results by policy" description="Mean over replications. Costs over the measured holdout.">
        <div className="mt-3 overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
                <Th>Policy</Th>
                <Th align="right">Total cost</Th>
                <Th align="right">Holding</Th>
                <Th align="right">Ordering</Th>
                <Th align="right">Lost sales</Th>
                <Th align="right">Fill rate</Th>
                <Th align="right">Stock-out SKU-days</Th>
                <Th align="right">Avg inventory</Th>
                <Th align="right">Orders</Th>
              </tr>
            </thead>
            <tbody>
              {policies.map((p, i) => (
                <tr key={p.name}>
                  <Td>
                    <span className="inline-flex items-center gap-2 font-medium">
                      <span className="size-2.5 rounded-full" style={{ background: policyColor(i) }} aria-hidden />
                      {p.name}
                    </span>
                    <div className="max-w-[260px] text-xs whitespace-normal text-muted">{describeLevels(p.service_levels)}</div>
                  </Td>
                  <Td align="right" className="font-semibold">
                    {money(p.overall.total_cost)}
                  </Td>
                  <Td align="right">{money(p.overall.holding_cost)}</Td>
                  <Td align="right">{money(p.overall.ordering_cost)}</Td>
                  <Td align="right">{money(p.overall.shortage_cost)}</Td>
                  <Td align="right">{pct(p.overall.fill_rate, 2)}</Td>
                  <Td align="right">{num(p.overall.stockout_days, 1)}</Td>
                  <Td align="right">{money(p.overall.avg_inventory_value)}</Td>
                  <Td align="right">{num(p.overall.orders)}</Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-5">
        <Card className="xl:col-span-3" title="Cost vs service frontier" description="The fair test: compare at equal fill rate, not at equal settings">
          <FrontierChart
            frontier={r.frontier}
            policies={policies.map((p) => ({ name: p.name, fill_rate: p.overall.fill_rate, total_cost: p.overall.total_cost }))}
          />
        </Card>
        <Card className="xl:col-span-2" title="Where the cost comes from">
          <CostBreakdownChart
            rows={policies.map((p) => ({
              name: p.name,
              holding: p.overall.holding_cost,
              ordering: p.overall.ordering_cost,
              shortage: p.overall.shortage_cost,
            }))}
          />
        </Card>
      </div>

      <Card className="mt-6" padded={false} title="Results by ABC class" description="Where each policy gains or loses">
        <div className="mt-3 overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
                <Th>Class</Th>
                {policies.map((p, i) => (
                  <Th key={p.name} align="right" className="border-l border-border">
                    <span className="inline-flex items-center gap-1.5">
                      <span className="size-2 rounded-full" style={{ background: policyColor(i) }} aria-hidden />
                      {p.name}
                    </span>
                  </Th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(["A", "B", "C"] as Abc[]).map((c) =>
                policies[0].by_class[c] ? (
                  <tr key={c}>
                    <Td>
                      <ClassBadge abc={c} />
                    </Td>
                    {policies.map((p) => {
                      const m = p.by_class[c]!;
                      return (
                        <Td key={p.name} align="right" className="border-l border-border">
                          <div>{money(m.total_cost)}</div>
                          <div className="text-xs text-muted">
                            fill {pct(m.fill_rate, 2)} · {num(m.stockout_days, 1)} stock-out days
                          </div>
                        </Td>
                      );
                    })}
                  </tr>
                ) : null,
              )}
            </tbody>
          </table>
        </div>
      </Card>

      <Card className="mt-6" title="Inventory value over the holdout" description="Replication 0 (the actual demand trace)">
        <TrajectoryChart series={policies.map((p) => ({ name: p.name, values: p.trajectory }))} start={r.holdout_start} />
      </Card>

      <Card className="mt-6" title="Method">
        <ul className="grid list-disc gap-2 pl-5 text-sm text-fg-2 md:grid-cols-2">
          <li>Classes and initial parameters use only data before the holdout (no look-ahead).</li>
          <li>Continuous review (s, Q), lost sales. s = d·L + z·σ_LT, Q = EOQ, re-estimated weekly on a trailing window.</li>
          <li>Replication 0 replays actual demand; the others are 7-day block bootstraps of it.</li>
          <li>Common random numbers: all policies share demand and lead-time draws, so a paired t-test is valid.</li>
          <li>Total cost = holding + ordering + lost margin × multiplier ({String(data.params.stockout_cost_multiplier)}).</li>
          <li>&quot;Dominates&quot; = below the uniform frontier and significantly cheaper (p &lt; 0.05).</li>
        </ul>
      </Card>
    </>
  );
}

function describeLevels(levels: Record<string, number>) {
  return Object.entries(levels)
    .map(([k, v]) => `${k === "*" ? "all" : k} ${pct(v, 1)}`)
    .join(" · ");
}

function Answer({ c }: { c: Comparison }) {
  const cheaper = c.total_cost.mean_diff < 0;
  return (
    <section className="rounded-lg border border-border bg-surface p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs text-muted">vs {c.baseline}</div>
          <h2 className="text-base font-semibold">{c.candidate}</h2>
        </div>
        <Verdict verdict={c.verdict} />
      </div>
      <dl className="mt-4 grid grid-cols-3 gap-4">
        <div>
          <dt className="text-xs text-muted">Total cost</dt>
          <dd className="num text-xl font-semibold">{pct(c.total_cost_pct, 1, true)}</dd>
          <dd className="num text-xs text-muted">
            {signed(c.total_cost.mean_diff)} [{signed(c.total_cost.ci_low)}, {signed(c.total_cost.ci_high)}]
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Stock-out days</dt>
          <dd className="num text-xl font-semibold">{pct(c.stockout_days_pct, 1, true)}</dd>
          <dd className="num text-xs text-muted">{signed(c.stockout_days.mean_diff, 1)} SKU-days</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">At equal fill rate</dt>
          <dd className="num text-xl font-semibold">
            {c.saving_vs_frontier_pct != null ? pct(-c.saving_vs_frontier_pct, 1, true) : "–"}
          </dd>
          <dd className="text-xs text-muted">vs the uniform frontier</dd>
        </div>
      </dl>
      <p className="mt-4 text-sm text-fg-2">
        {c.candidate} is {cheaper ? "cheaper" : "more expensive"} than {c.baseline} by{" "}
        {money(Math.abs(c.total_cost.mean_diff))}
        {c.total_cost.p_value != null && (
          <>
            {" "}
            (paired t-test p = {c.total_cost.p_value.toPrecision(2)}, {c.significant ? "significant" : "not significant"})
          </>
        )}
        {c.uniform_cost_at_same_fill != null && (
          <>
            . A uniform policy reaching the same fill rate would cost {money(c.uniform_cost_at_same_fill)}
          </>
        )}
        .
      </p>
    </section>
  );
}

function ExperimentForm({ onDone }: { onDone: () => void }) {
  const { mutate } = useSWRConfig();
  const [form, setForm] = useState({
    replications: 20,
    holdout_days: 120,
    stockout_cost_multiplier: 1,
    uniform: 95,
    a: 98,
    b: 95,
    c: 90,
  });
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const field = (key: keyof typeof form, label: string, props: { min: number; max: number; step?: number; suffix?: string }) => (
    <label className="flex flex-col gap-1 text-xs text-muted">
      {label}
      <span className="relative">
        <input
          type="number"
          value={form[key]}
          min={props.min}
          max={props.max}
          step={props.step ?? 1}
          onChange={(e) => setForm({ ...form, [key]: Number(e.target.value) })}
          className="num h-9 w-full rounded-md border border-border-strong bg-surface px-2.5 text-sm text-fg"
        />
        {props.suffix && <span className="absolute top-1/2 right-2.5 -translate-y-1/2 text-xs">{props.suffix}</span>}
      </span>
    </label>
  );

  const submit = async () => {
    setRunning(true);
    setError(null);
    try {
      await api.post("/simulations", {
        replications: form.replications,
        holdout_days: form.holdout_days,
        stockout_cost_multiplier: form.stockout_cost_multiplier,
        policies: [
          { name: `Uniform ${form.uniform}%`, service_levels: { "*": form.uniform / 100 } },
          {
            name: `ABC ${form.a}/${form.b}/${form.c}`,
            service_levels: { A: form.a / 100, B: form.b / 100, C: form.c / 100 },
          },
          {
            name: "ABC-XYZ matrix",
            service_levels: { AX: 0.99, AY: 0.98, AZ: 0.95, BX: 0.97, BY: 0.95, BZ: 0.92, CX: 0.93, CY: 0.9, CZ: 0.85 },
          },
        ],
      });
      await mutate("/simulations/latest");
      await mutate("/overview");
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Simulation failed");
    } finally {
      setRunning(false);
    }
  };

  return (
    <Card className="mb-6" title="Experiment settings" description="The ABC-XYZ matrix policy is always included as a third arm.">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4 xl:grid-cols-7">
        {field("uniform", "Uniform service", { min: 50, max: 99.9, step: 0.5, suffix: "%" })}
        {field("a", "ABC: class A", { min: 50, max: 99.9, step: 0.5, suffix: "%" })}
        {field("b", "ABC: class B", { min: 50, max: 99.9, step: 0.5, suffix: "%" })}
        {field("c", "ABC: class C", { min: 50, max: 99.9, step: 0.5, suffix: "%" })}
        {field("replications", "Replications", { min: 1, max: 200 })}
        {field("holdout_days", "Holdout days", { min: 28, max: 365 })}
        {field("stockout_cost_multiplier", "Lost-sale cost × margin", { min: 0, max: 20, step: 0.5 })}
      </div>
      {error && (
        <div className="mt-4">
          <ErrorNote error={new Error(error)} />
        </div>
      )}
      <div className="mt-4 flex justify-end">
        <Button variant="primary" onClick={submit} disabled={running}>
          {running && <Loader2 size={14} className="animate-spin" />}
          {running ? "Simulating…" : "Run simulation"}
        </Button>
      </div>
    </Card>
  );
}
