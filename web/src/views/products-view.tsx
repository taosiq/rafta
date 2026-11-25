"use client";

import clsx from "clsx";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Search } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { NoDataState } from "@/components/setup";
import { Button, Card, ClassBadge, ErrorNote, PageHeader, Segmented, Skeleton, StatusBadge, Td, Th } from "@/components/ui";
import type { Paged, ProductRow } from "@/lib/api";
import { money, num, shortDate } from "@/lib/format";
import { useApi } from "@/lib/hooks";

const PAGE_SIZE = 25;

type SortKey = "revenue" | "sku" | "on_hand" | "days_of_cover" | "stockout_date" | "avg_daily_demand" | "suggested_order_qty";

function SortTh({
  k,
  children,
  align = "right",
  sort,
  order,
  onSort,
}: {
  k: SortKey;
  children: string;
  align?: "left" | "right";
  sort: SortKey;
  order: string;
  onSort: (k: SortKey) => void;
}) {
  return (
    <Th align={align}>
      <button
        onClick={() => onSort(k)}
        className={clsx("inline-flex items-center gap-1 hover:text-fg", sort === k && "text-fg")}
        aria-label={`Sort by ${children}`}
      >
        {children}
        {sort === k && (order === "asc" ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}
      </button>
    </Th>
  );
}

export function ProductsView() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const abc = params.get("abc") ?? "";
  const status = params.get("status") ?? "";
  const sort = (params.get("sort") as SortKey) ?? "revenue";
  const order = params.get("order") ?? "desc";
  const page = Number(params.get("page") ?? 1);
  const [q, setQ] = useState(params.get("q") ?? "");

  const update = (patch: Record<string, string | number | null>) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v === null || v === "") next.delete(k);
      else next.set(k, String(v));
    }
    if (!("page" in patch)) next.delete("page");
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  };

  // Debounce search into the URL.
  useEffect(() => {
    const t = setTimeout(() => {
      if ((params.get("q") ?? "") !== q) update({ q });
    }, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const query = new URLSearchParams({ sort, order, page: String(page), page_size: String(PAGE_SIZE) });
  if (abc) query.set("abc", abc);
  if (status) query.set("status", status);
  if (params.get("q")) query.set("q", params.get("q")!);
  const { data, error, isLoading, isValidating } = useApi<Paged<ProductRow>>(`/products?${query}`);

  const sortBy = (key: SortKey) =>
    update({ sort: key, order: sort === key && order === "desc" ? "asc" : key === "sku" || key === "days_of_cover" || key === "stockout_date" ? "asc" : "desc" });

  const sp = { sort, order, onSort: sortBy };

  if (data && data.total === 0 && !abc && !status && !params.get("q")) {
    return (
      <>
        <PageHeader title="Products" />
        <NoDataState what="products" />
      </>
    );
  }

  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <>
      <PageHeader
        title="Products"
        description="Current stock, replenishment parameters and status for every SKU."
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <label className="relative">
          <span className="sr-only">Search products</span>
          <Search size={14} className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-muted" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search SKU, name or category"
            className="h-9 w-64 rounded-md border border-border-strong bg-surface pr-3 pl-8 text-sm placeholder:text-muted"
          />
        </label>
        <Segmented
          label="Class"
          value={abc}
          onChange={(v) => update({ abc: v })}
          options={[
            { value: "", label: "All classes" },
            { value: "A", label: "A" },
            { value: "B", label: "B" },
            { value: "C", label: "C" },
          ]}
        />
        <Segmented
          label="Status"
          value={status}
          onChange={(v) => update({ status: v })}
          options={[
            { value: "", label: "Any status" },
            { value: "stockout_risk", label: "Stock-out risk" },
            { value: "reorder", label: "Reorder soon" },
            { value: "healthy", label: "Healthy" },
          ]}
        />
        {data && <span className="num ml-auto text-xs text-muted">{data.total} products</span>}
      </div>

      {error && <ErrorNote error={error} />}

      <Card padded={false} className={clsx(isValidating && "opacity-80 transition-opacity")}>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
                <SortTh {...sp} k="sku" align="left">
                  Product
                </SortTh>
                <Th>Class</Th>
                <Th>Status</Th>
                <SortTh {...sp} k="revenue">Revenue (12m)</SortTh>
                <SortTh {...sp} k="on_hand">On hand</SortTh>
                <SortTh {...sp} k="avg_daily_demand">Demand / day</SortTh>
                <Th align="right">Reorder pt</Th>
                <SortTh {...sp} k="days_of_cover">Cover (days)</SortTh>
                <SortTh {...sp} k="stockout_date">Runs out</SortTh>
                <SortTh {...sp} k="suggested_order_qty">Order qty</SortTh>
              </tr>
            </thead>
            <tbody>
              {isLoading && !data
                ? Array.from({ length: 10 }).map((_, i) => (
                    <tr key={i}>
                      <Td colSpan={10}>
                        <Skeleton className="h-5" />
                      </Td>
                    </tr>
                  ))
                : data?.items.map((p) => (
                    <tr key={p.sku} className="hover:bg-surface-2">
                      <Td>
                        <Link href={`/products/${p.sku}`} className="block max-w-64 truncate font-medium hover:underline">
                          {p.name}
                        </Link>
                        <span className="num text-xs text-muted">
                          {p.sku} · {p.category}
                        </span>
                      </Td>
                      <Td>
                        <ClassBadge abc={p.abc} xyz={p.xyz} />
                      </Td>
                      <Td>
                        <StatusBadge status={p.status} compact />
                      </Td>
                      <Td align="right">{money(p.revenue)}</Td>
                      <Td align="right">{num(p.on_hand)}</Td>
                      <Td align="right">{num(p.avg_daily_demand, 1)}</Td>
                      <Td align="right">{num(p.reorder_point)}</Td>
                      <Td align="right">{num(p.days_of_cover, 1)}</Td>
                      <Td align="right">{shortDate(p.stockout_date)}</Td>
                      <Td align="right">{p.suggested_order_qty ? num(p.suggested_order_qty) : "–"}</Td>
                    </tr>
                  ))}
              {data?.items.length === 0 && (
                <tr>
                  <Td colSpan={10} className="py-8 text-center text-muted">
                    No products match these filters.
                  </Td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between px-5 py-3">
          <span className="num text-xs text-muted">
            Page {page} of {pages}
          </span>
          <div className="flex gap-2">
            <Button size="sm" disabled={page <= 1} onClick={() => update({ page: page - 1 })} aria-label="Previous page">
              <ChevronLeft size={14} /> Prev
            </Button>
            <Button size="sm" disabled={page >= pages} onClick={() => update({ page: page + 1 })} aria-label="Next page">
              Next <ChevronRight size={14} />
            </Button>
          </div>
        </div>
      </Card>
    </>
  );
}
