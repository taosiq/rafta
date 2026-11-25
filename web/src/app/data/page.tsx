"use client";

import { CalendarClock, Download, Loader2, Play, Sparkles, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { useSWRConfig } from "swr";

import { Button, Card, ErrorNote, PageHeader, Stat, StatusBadge, Td, Th } from "@/components/ui";
import { api, ApiError, type DataStatus, type Job, type Status } from "@/lib/api";
import { longDate, num, relativeTime } from "@/lib/format";
import { useApi, useJobRunner } from "@/lib/hooks";

const KINDS = [
  {
    kind: "products",
    title: "1 · Products",
    columns: "sku, name, unit_cost, unit_price (+ optional category, lead_time_days, lead_time_std_days, order_cost, holding_rate, moq)",
  },
  { kind: "sales", title: "2 · Sales", columns: "date, sku, quantity (one row per SKU per day; zero days may be omitted)" },
  { kind: "stock", title: "3 · Stock", columns: "date, sku, on_hand (+ optional on_order). The latest date is used." },
] as const;

const JOB_STATUS: Record<Job["status"], Status> = {
  success: "healthy",
  failed: "stockout_risk",
  running: "reorder",
  queued: "reorder",
};

function UploadCard({ kind, title, columns }: (typeof KINDS)[number]) {
  const { mutate } = useSWRConfig();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [errors, setErrors] = useState<string[]>([]);

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    setResult(null);
    setErrors([]);
    try {
      const r = await api.upload<{ rows: number; inserted: number }>(`/imports/${kind}`, file);
      setResult(`Imported ${num(r.rows)} rows from ${file.name}.`);
      await mutate("/data/status");
    } catch (e) {
      const detail = e instanceof ApiError ? (e.detail as { errors?: string[] } | undefined) : undefined;
      setErrors(detail?.errors ?? [e instanceof Error ? e.message : "Upload failed"]);
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  };

  return (
    <Card title={title} description={columns}>
      <div className="flex flex-wrap items-center gap-2">
        <input
          ref={input}
          type="file"
          accept=".csv,text/csv"
          className="sr-only"
          id={`file-${kind}`}
          onChange={(e) => onFile(e.target.files?.[0])}
        />
        <Button onClick={() => input.current?.click()} disabled={busy}>
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
          Upload CSV
        </Button>
        <a
          href={`/api/v1/imports/templates/${kind}`}
          className="inline-flex h-9 items-center gap-1.5 px-2 text-sm text-fg-2 hover:text-fg"
        >
          <Download size={14} /> Template
        </a>
      </div>
      {result && <p className="mt-3 text-sm text-healthy-ink">{result}</p>}
      {errors.length > 0 && (
        <div role="alert" className="mt-3 rounded-md bg-risk-soft px-3 py-2 text-xs text-risk-ink">
          <p className="font-medium">Nothing was imported. Fix these and upload again:</p>
          <ul className="mt-1 list-disc pl-4">
            {errors.slice(0, 8).map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
          {errors.length > 8 && <p className="mt-1">…and {errors.length - 8} more</p>}
        </div>
      )}
    </Card>
  );
}

export default function DataPage() {
  const { data: status } = useApi<DataStatus>("/data/status");
  const { data: jobs } = useApi<{ jobs: Job[]; schedule: string; next_run: string | null }>("/jobs", {
    refreshInterval: (d) => (d?.jobs.some((j) => j.status === "running" || j.status === "queued") ? 2000 : 15_000),
  });
  const runner = useJobRunner();

  return (
    <>
      <PageHeader
        title="Data & jobs"
        description="Import CSV exports from your POS or ERP, then run the pipeline: classify → forecast → policies → simulate."
        actions={
          <Button onClick={runner.seed} disabled={runner.busy}>
            <Sparkles size={14} /> Reset to demo data
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Stat label="Products" value={<span className="num">{num(status?.products)}</span>} />
        <Stat
          label="Sales rows"
          value={<span className="num">{num(status?.sales_rows)}</span>}
          hint={status?.first_sale ? `${longDate(status.first_sale)} – ${longDate(status.last_sale)}` : "No sales yet"}
        />
        <Stat label="Stock snapshot" value={longDate(status?.stock_as_of)} />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        {KINDS.map((k) => (
          <UploadCard key={k.kind} {...k} />
        ))}
      </div>

      <Card
        className="mt-6"
        padded={false}
        title="Background jobs"
        description={
          <span className="inline-flex items-center gap-1">
            <CalendarClock size={12} aria-hidden /> Nightly refresh, cron <code className="font-mono">{jobs?.schedule}</code> UTC
            {jobs?.next_run && <> · next run {new Date(jobs.next_run).toUTCString().slice(0, 22)}</>}
          </span>
        }
        actions={
          <div className="flex gap-2">
            <Button size="sm" onClick={() => runner.run("refresh")} disabled={runner.busy}>
              <Play size={12} /> Refresh forecasts
            </Button>
            <Button size="sm" variant="primary" onClick={() => runner.run("pipeline")} disabled={runner.busy}>
              {runner.busy ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />} Full pipeline
            </Button>
          </div>
        }
      >
        {runner.error && (
          <div className="px-5 pt-3">
            <ErrorNote error={new Error(runner.error)} />
          </div>
        )}
        <div className="mt-3 overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
                <Th>Job</Th>
                <Th>Status</Th>
                <Th>Trigger</Th>
                <Th>Started</Th>
                <Th align="right">Duration</Th>
                <Th>Result</Th>
              </tr>
            </thead>
            <tbody>
              {jobs?.jobs.map((j) => (
                <tr key={j.id}>
                  <Td>
                    <span className="font-medium">{j.job_type}</span> <span className="num text-xs text-muted">#{j.id}</span>
                  </Td>
                  <Td>
                    <StatusBadge status={JOB_STATUS[j.status]} label={j.status} />
                  </Td>
                  <Td className="text-fg-2">{j.trigger}</Td>
                  <Td className="text-fg-2">{relativeTime(j.started_at ?? j.created_at)}</Td>
                  <Td align="right">{j.duration_s != null ? `${num(j.duration_s, 1)} s` : "–"}</Td>
                  <Td className="max-w-[420px] truncate text-xs text-fg-2">
                    <span title={j.message ?? ""}>{j.message ?? "–"}</span>
                  </Td>
                </tr>
              ))}
              {jobs?.jobs.length === 0 && (
                <tr>
                  <Td colSpan={6} className="py-6 text-center text-muted">
                    No jobs have run yet.
                  </Td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
