/**
 * Typed client for the Rafta API. All requests go to same-origin `/api/v1/*`,
 * which Next.js rewrites to the FastAPI service (see next.config.ts), so the
 * browser never needs CORS or to know where the backend lives.
 */

export type Abc = "A" | "B" | "C";
export type Xyz = "X" | "Y" | "Z";
export type Status = "stockout_risk" | "reorder" | "healthy";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: unknown,
  ) {
    super(message);
  }
}

const BASE = "/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: init?.body instanceof FormData ? init.headers : { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = (await res.json()).detail;
    } catch {
      /* not JSON */
    }
    const message = [502, 503, 504].includes(res.status)
      ? "The server is waking up. Retrying…"
      : typeof detail === "string"
        ? detail
        : detail && typeof detail === "object" && "message" in detail
          ? String((detail as { message: string }).message)
          : `Request failed (${res.status})`;
    throw new ApiError(res.status, message, detail);
  }
  return res.json() as Promise<T>;
}

export const fetcher = <T>(path: string) => request<T>(path);

export const api = {
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  upload: <T>(path: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<T>(path, { method: "POST", body: form });
  },
};

/* ----------------------------------------------------------------- types */

export interface ProductRow {
  sku: string;
  name: string;
  category: string;
  unit_cost: number;
  unit_price: number;
  lead_time_days: number;
  abc: Abc | null;
  xyz: Xyz | null;
  revenue: number | null;
  cv: number | null;
  on_hand: number | null;
  on_order: number | null;
  avg_daily_demand: number | null;
  safety_stock: number | null;
  reorder_point: number | null;
  eoq: number | null;
  service_level: number | null;
  days_of_cover: number | null;
  stockout_date: string | null;
  suggested_order_qty: number | null;
  status: Status | null;
  inventory_value: number | null;
}

export interface Comparison {
  baseline: string;
  candidate: string;
  total_cost: { mean_diff: number; ci_low: number; ci_high: number; p_value: number | null };
  total_cost_pct: number;
  fill_rate: { mean_diff: number; ci_low: number; ci_high: number; p_value: number | null };
  stockout_days: { mean_diff: number; ci_low: number; ci_high: number; p_value: number | null };
  stockout_days_pct: number;
  uniform_cost_at_same_fill: number | null;
  saving_vs_frontier: number | null;
  saving_vs_frontier_pct: number | null;
  significant: boolean;
  verdict: "dominates" | "better" | "trade-off" | "worse";
  replications: number;
}

export interface Overview {
  as_of: string | null;
  skus: number;
  inventory_value: number;
  value_at_risk: number;
  suggested_order_value: number;
  status_counts: Record<Status, number>;
  by_class: Partial<Record<Abc, { skus: number; revenue: number; inventory_value: number; at_risk: number }>>;
  at_risk: ProductRow[];
  forecast: {
    run_id: number;
    created_at: string;
    median_mase: number;
    weighted_wape: number;
    weighted_bias: number;
    improvement_vs_naive: number;
  } | null;
  simulation: { run_id: number; created_at: string; comparisons: Comparison[] } | null;
  demand_trend: { week: string; units: number }[];
}

export interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface BacktestRow {
  model: string;
  label: string;
  mae: number;
  rmse: number;
  wape: number;
  mase: number;
  bias: number;
  selected: boolean;
}

export interface ProductDetail {
  product: ProductRow;
  adi: number | null;
  history: { date: string; actual: number }[];
  forecast: { date: string; forecast: number; lower: number; upper: number; model: string }[];
  backtest: BacktestRow[];
  params: { order_cost: number; holding_rate: number; moq: number; lead_time_std_days: number };
}

export interface ClassificationItem {
  sku: string;
  name: string;
  abc: Abc;
  xyz: Xyz;
  revenue: number;
  revenue_share: number;
  cumulative_share: number;
  cv: number;
  adi: number;
}

export interface ClassificationResponse {
  items: ClassificationItem[];
  matrix: Record<string, { skus: number; revenue_share: number }>;
  pareto: { sku_share: number; revenue_share: number; abc: Abc }[];
  computed_at: string | null;
}

export interface ModelStats {
  median_mase: number;
  mean_wape: number;
  weighted_wape: number;
  mean_bias: number;
}

export interface ForecastSummary {
  run: {
    id: number;
    created_at: string;
    horizon_days: number;
    folds: number;
    history_end: string;
    summary: {
      per_model: Record<string, ModelStats>;
      selected_counts: Record<string, number>;
      selected: ModelStats & { weighted_bias: number; improvement_vs_naive: number };
      by_class: Partial<Record<Abc, { median_mase: number; mean_wape: number; weighted_wape: number; skus: number }>>;
    };
  } | null;
  models: { name: string; label: string; description: string }[];
  wape_by_xyz: { xyz: Xyz; model: string; wape: number; skus: number }[];
}

export interface PolicyMetrics {
  total_cost: number;
  holding_cost: number;
  ordering_cost: number;
  shortage_cost: number;
  fill_rate: number;
  stockout_days: number;
  units_lost: number;
  orders: number;
  avg_inventory_value: number;
}

export interface SimulationResult {
  id: number;
  created_at: string;
  params: Record<string, unknown>;
  results: {
    skus: number;
    class_counts: Record<Abc, number>;
    holdout_start: string;
    holdout_end: string;
    days_measured: number;
    replications: number;
    policies: {
      name: string;
      service_levels: Record<string, number>;
      overall: PolicyMetrics;
      by_class: Partial<Record<Abc, PolicyMetrics>>;
      trajectory: number[];
    }[];
    frontier: (PolicyMetrics & { service_level: number })[];
    comparisons: Comparison[];
    per_sku: ({ product_id: number; sku: string; abc: Abc; xyz: Xyz } & Record<
      string,
      { total_cost: number; fill_rate: number; stockout_days: number } | string | number
    >)[];
  };
}

export interface Job {
  id: number;
  job_type: string;
  trigger: string;
  status: "queued" | "running" | "success" | "failed";
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_s: number | null;
  message: string | null;
}

export interface ToolCall {
  name: string;
  arguments: Record<string, unknown>;
  result: Record<string, unknown>;
}

export interface AssistantAnswer {
  answer: string;
  mode: "llm" | "offline";
  tool_calls: ToolCall[];
  latency_ms: number;
}

export interface DataStatus {
  products: number;
  sales_rows: number;
  first_sale: string | null;
  last_sale: string | null;
  stock_as_of: string | null;
}
