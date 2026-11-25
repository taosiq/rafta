"""Whitelisted, typed, read-only tools the assistant may call.

Safety model (defence in depth):
1. The LLM never writes SQL. It can only pick one of these functions.
2. Arguments are validated by Pydantic (types, enums, ranges, string length) before execution.
3. Every tool runs in `readonly_session()`: a read-only DB role, a READ ONLY transaction and an
   unconditional rollback.
4. Result sizes are capped (`limit` <= 50) so a prompt cannot exfiltrate the whole database.
"""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import readonly_session
from app.models import Classification, Forecast, ForecastRun, InventoryPolicy, Product, Sale, SimulationRun

AbcClass = Literal["A", "B", "C"]


class StockoutRiskArgs(BaseModel):
    within_days: int = Field(7, ge=1, le=90, description="Look-ahead window in days, e.g. 7 for 'next week'.")
    abc_class: AbcClass | None = Field(None, description="Only this ABC class.")
    limit: int = Field(10, ge=1, le=50)


class ReorderArgs(BaseModel):
    abc_class: AbcClass | None = None
    limit: int = Field(10, ge=1, le=50)


class ProductLookupArgs(BaseModel):
    query: str = Field(..., min_length=1, max_length=64, description="SKU code or part of a product name.")


class ForecastArgs(BaseModel):
    sku: str = Field(..., min_length=1, max_length=64)
    days: int = Field(14, ge=1, le=60)


class AccuracyArgs(BaseModel):
    abc_class: AbcClass | None = None


class TopProductsArgs(BaseModel):
    metric: Literal["revenue", "demand", "inventory_value"] = "revenue"
    abc_class: AbcClass | None = None
    limit: int = Field(10, ge=1, le=50)


class NoArgs(BaseModel):
    pass


def _as_of(db: Session) -> date | None:
    run = db.execute(select(ForecastRun).order_by(ForecastRun.id.desc()).limit(1)).scalar_one_or_none()
    return run.history_end if run else None


def _policy_rows(db: Session, stmt) -> list[dict]:
    rows = db.execute(stmt).all()
    return [
        {
            "sku": p.sku,
            "name": p.name,
            "abc": c.abc if c else None,
            "xyz": c.xyz if c else None,
            "on_hand": round(ip.on_hand, 1),
            "on_order": round(ip.on_order, 1),
            "avg_daily_demand": round(ip.avg_daily_demand, 2),
            "days_of_cover": None if ip.days_of_cover is None else round(ip.days_of_cover, 1),
            "reorder_point": round(ip.reorder_point, 1),
            "stockout_date": ip.stockout_date.isoformat() if ip.stockout_date else None,
            "suggested_order_qty": round(ip.suggested_order_qty),
            "status": ip.status,
        }
        for ip, p, c in rows
    ]


def _base_policy_query():
    return (
        select(InventoryPolicy, Product, Classification)
        .join(Product, Product.id == InventoryPolicy.product_id)
        .outerjoin(Classification, Classification.product_id == InventoryPolicy.product_id)
    )


def stockout_risk(db: Session, a: StockoutRiskArgs) -> dict:
    as_of = _as_of(db)
    if as_of is None:
        return {"error": "No forecasts yet. Run the pipeline first."}
    horizon = as_of + timedelta(days=a.within_days)
    stmt = _base_policy_query().where(
        InventoryPolicy.stockout_date.is_not(None), InventoryPolicy.stockout_date <= horizon
    )
    if a.abc_class:
        stmt = stmt.where(Classification.abc == a.abc_class)
    stmt = stmt.order_by(InventoryPolicy.stockout_date, Product.sku).limit(a.limit)
    rows = _policy_rows(db, stmt)
    for r in rows:
        r["days_until_stockout"] = (date.fromisoformat(r["stockout_date"]) - as_of).days
    total = db.execute(
        select(func.count())
        .select_from(InventoryPolicy)
        .where(InventoryPolicy.stockout_date.is_not(None), InventoryPolicy.stockout_date <= horizon)
    ).scalar()
    return {"as_of": as_of.isoformat(), "window_end": horizon.isoformat(), "total_at_risk": total, "products": rows}


def reorder_recommendations(db: Session, a: ReorderArgs) -> dict:
    stmt = _base_policy_query().where(InventoryPolicy.status.in_(["stockout_risk", "reorder"]))
    if a.abc_class:
        stmt = stmt.where(Classification.abc == a.abc_class)
    stmt = stmt.order_by(InventoryPolicy.status.desc(), InventoryPolicy.days_of_cover.asc()).limit(a.limit)
    rows = _policy_rows(db, stmt)
    value = 0.0
    for r in rows:
        cost = db.execute(select(Product.unit_cost).where(Product.sku == r["sku"])).scalar() or 0.0
        r["order_value"] = round(r["suggested_order_qty"] * cost, 2)
        value += r["order_value"]
    return {"as_of": str(_as_of(db)), "products": rows, "total_order_value": round(value, 2)}


def product_lookup(db: Session, a: ProductLookupArgs) -> dict:
    q = a.query.strip()
    stmt = _base_policy_query().where(or_(func.lower(Product.sku) == q.lower(), Product.name.ilike(f"%{q}%"))).limit(5)
    rows = _policy_rows(db, stmt)
    if not rows:
        return {"products": [], "message": f"No product matches '{q}'."}
    for r in rows:
        pid = db.execute(select(Product.id).where(Product.sku == r["sku"])).scalar()
        last = db.execute(select(func.max(Sale.date))).scalar()
        if last:
            r["units_sold_last_28d"] = round(
                db.execute(
                    select(func.coalesce(func.sum(Sale.quantity), 0)).where(
                        Sale.product_id == pid, Sale.date > last - timedelta(days=28)
                    )
                ).scalar()
                or 0,
                1,
            )
    return {"products": rows}


def forecast_for_product(db: Session, a: ForecastArgs) -> dict:
    product = db.execute(select(Product).where(func.lower(Product.sku) == a.sku.strip().lower())).scalar()
    if product is None:
        return {"error": f"Unknown SKU '{a.sku}'."}
    run_id = db.execute(select(func.max(ForecastRun.id))).scalar()
    rows = (
        db.execute(
            select(Forecast)
            .where(Forecast.run_id == run_id, Forecast.product_id == product.id)
            .order_by(Forecast.date)
            .limit(a.days)
        )
        .scalars()
        .all()
    )
    return {
        "sku": product.sku,
        "name": product.name,
        "model": rows[0].model if rows else None,
        "total": round(sum(r.yhat for r in rows), 1),
        "daily": [
            {
                "date": r.date.isoformat(),
                "forecast": round(r.yhat, 2),
                "low": round(r.yhat_lower, 2),
                "high": round(r.yhat_upper, 2),
            }
            for r in rows
        ],
    }


def classification_summary(db: Session, _: NoArgs) -> dict:
    rows = db.execute(
        select(Classification.abc, Classification.xyz, func.count(), func.sum(Classification.revenue_share)).group_by(
            Classification.abc, Classification.xyz
        )
    ).all()
    matrix = {f"{a}{x}": {"skus": n, "revenue_share": round(s or 0, 4)} for a, x, n, s in rows}
    by_abc: dict[str, dict] = {}
    for a, _x, n, s in rows:
        cur = by_abc.setdefault(a, {"skus": 0, "revenue_share": 0.0})
        cur["skus"] += n
        cur["revenue_share"] = round(cur["revenue_share"] + (s or 0), 4)
    return {"by_abc": by_abc, "matrix": matrix}


def forecast_accuracy(db: Session, a: AccuracyArgs) -> dict:
    run = db.execute(select(ForecastRun).order_by(ForecastRun.id.desc()).limit(1)).scalar_one_or_none()
    if run is None:
        return {"error": "No forecast run yet."}
    s = run.summary
    out = {
        "run_id": run.id,
        "history_end": run.history_end.isoformat(),
        "selected": s.get("selected"),
        "per_model": s.get("per_model"),
        "selected_counts": s.get("selected_counts"),
    }
    if a.abc_class:
        out["class"] = s.get("by_class", {}).get(a.abc_class)
    else:
        out["by_class"] = s.get("by_class")
    return out


def simulation_results(db: Session, _: NoArgs) -> dict:
    run = db.execute(select(SimulationRun).order_by(SimulationRun.id.desc()).limit(1)).scalar_one_or_none()
    if run is None:
        return {"error": "No simulation has been run yet."}
    r = run.results
    return {
        "run_id": run.id,
        "holdout": f"{r['holdout_start']} to {r['holdout_end']}",
        "replications": r["replications"],
        "policies": [{"name": p["name"], **{k: round(v, 4) for k, v in p["overall"].items()}} for p in r["policies"]],
        "comparisons": [
            {
                k: c[k]
                for k in (
                    "baseline",
                    "candidate",
                    "verdict",
                    "total_cost_pct",
                    "stockout_days_pct",
                    "saving_vs_frontier_pct",
                    "significant",
                )
            }
            for c in r["comparisons"]
        ],
    }


def inventory_overview(db: Session, _: NoArgs) -> dict:
    counts = dict(db.execute(select(InventoryPolicy.status, func.count()).group_by(InventoryPolicy.status)).all())
    value = (
        db.execute(
            select(func.sum(InventoryPolicy.on_hand * Product.unit_cost)).join(
                Product, Product.id == InventoryPolicy.product_id
            )
        ).scalar()
        or 0.0
    )
    return {
        "as_of": str(_as_of(db)),
        "skus": sum(counts.values()),
        "status_counts": counts,
        "inventory_value": round(value, 2),
    }


def top_products(db: Session, a: TopProductsArgs) -> dict:
    metric_col = {
        "revenue": Classification.revenue,
        "demand": InventoryPolicy.avg_daily_demand,
        "inventory_value": InventoryPolicy.on_hand * Product.unit_cost,
    }[a.metric]
    stmt = (
        select(Product.sku, Product.name, Classification.abc, metric_col.label("value"))
        .join(Classification, Classification.product_id == Product.id)
        .join(InventoryPolicy, InventoryPolicy.product_id == Product.id)
    )
    if a.abc_class:
        stmt = stmt.where(Classification.abc == a.abc_class)
    rows = db.execute(stmt.order_by(metric_col.desc()).limit(a.limit)).all()
    return {
        "metric": a.metric,
        "products": [{"sku": s, "name": n, "abc": c, "value": round(v or 0, 2)} for s, n, c, v in rows],
    }


class Tool(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    name: str
    description: str
    args: type[BaseModel]
    fn: Callable[[Session, Any], dict]


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        Tool(
            name="stockout_risk",
            args=StockoutRiskArgs,
            fn=stockout_risk,
            description="Products projected to run out of stock within N days, soonest first.",
        ),
        Tool(
            name="reorder_recommendations",
            args=ReorderArgs,
            fn=reorder_recommendations,
            description="Products at or below their reorder point, with suggested order quantities and value.",
        ),
        Tool(
            name="product_lookup",
            args=ProductLookupArgs,
            fn=product_lookup,
            description="Details for a product by SKU or name: stock, class, demand, reorder point.",
        ),
        Tool(
            name="forecast_for_product",
            args=ForecastArgs,
            fn=forecast_for_product,
            description="Daily demand forecast with 80% interval for one SKU.",
        ),
        Tool(
            name="classification_summary",
            args=NoArgs,
            fn=classification_summary,
            description="ABC/XYZ class counts and revenue share.",
        ),
        Tool(
            name="forecast_accuracy",
            args=AccuracyArgs,
            fn=forecast_accuracy,
            description="Backtested forecast accuracy (MASE, WAPE, bias) overall, per model and per class.",
        ),
        Tool(
            name="simulation_results",
            args=NoArgs,
            fn=simulation_results,
            description="Latest ABC-vs-uniform policy simulation: cost, fill rate, stock-outs, verdict.",
        ),
        Tool(
            name="inventory_overview",
            args=NoArgs,
            fn=inventory_overview,
            description="Headline KPIs: SKU count, inventory value, counts by stock status.",
        ),
        Tool(
            name="top_products",
            args=TopProductsArgs,
            fn=top_products,
            description="Top products by revenue, daily demand or inventory value.",
        ),
    ]
}


def openai_tool_specs() -> list[dict]:
    specs = []
    for t in TOOLS.values():
        schema = t.args.model_json_schema()
        schema.pop("title", None)
        specs.append(
            {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": schema}}
        )
    return specs


class ToolError(Exception):
    pass


def call_tool(name: str, arguments: dict | None) -> dict:
    tool = TOOLS.get(name)
    if tool is None:
        raise ToolError(f"Unknown tool '{name}'. Available: {', '.join(TOOLS)}")
    try:
        args = tool.args.model_validate(arguments or {})
    except ValidationError as exc:
        raise ToolError(f"Invalid arguments for {name}: {exc.errors(include_url=False)}") from exc
    with readonly_session() as db:
        return tool.fn(db, args)
