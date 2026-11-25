"""Read endpoints that power the dashboard, plus running a simulation on demand."""

from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.db import get_db, session_scope
from app.models import (
    BacktestMetric,
    Classification,
    Forecast,
    ForecastRun,
    InventoryPolicy,
    Product,
    Sale,
    SimulationRun,
)
from app.schemas import SimulationIn
from app.services.forecasting import MODELS
from app.services.simulation import PolicySpec, SimParams, run_simulation

router = APIRouter(tags=["analytics"])


def _latest_run(db: Session) -> ForecastRun | None:
    return db.execute(select(ForecastRun).order_by(ForecastRun.id.desc()).limit(1)).scalar_one_or_none()


def _product_row(p: Product, c: Classification | None, ip: InventoryPolicy | None) -> dict:
    return {
        "sku": p.sku,
        "name": p.name,
        "category": p.category,
        "unit_cost": p.unit_cost,
        "unit_price": p.unit_price,
        "lead_time_days": p.lead_time_days,
        "abc": c.abc if c else None,
        "xyz": c.xyz if c else None,
        "revenue": c.revenue if c else None,
        "cv": c.cv if c else None,
        "on_hand": ip.on_hand if ip else None,
        "on_order": ip.on_order if ip else None,
        "avg_daily_demand": ip.avg_daily_demand if ip else None,
        "safety_stock": ip.safety_stock if ip else None,
        "reorder_point": ip.reorder_point if ip else None,
        "eoq": ip.eoq if ip else None,
        "service_level": ip.service_level if ip else None,
        "days_of_cover": ip.days_of_cover if ip else None,
        "stockout_date": ip.stockout_date if ip else None,
        "suggested_order_qty": ip.suggested_order_qty if ip else None,
        "status": ip.status if ip else None,
        "inventory_value": (ip.on_hand * p.unit_cost) if ip else None,
    }


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    run = _latest_run(db)
    rows = db.execute(
        select(Product, Classification, InventoryPolicy)
        .outerjoin(Classification, Classification.product_id == Product.id)
        .outerjoin(InventoryPolicy, InventoryPolicy.product_id == Product.id)
    ).all()
    items = [_product_row(p, c, ip) for p, c, ip in rows]
    status_counts = {"stockout_risk": 0, "reorder": 0, "healthy": 0}
    by_class: dict[str, dict] = {}
    for it in items:
        if it["status"]:
            status_counts[it["status"]] = status_counts.get(it["status"], 0) + 1
        if it["abc"]:
            b = by_class.setdefault(it["abc"], {"skus": 0, "revenue": 0.0, "inventory_value": 0.0, "at_risk": 0})
            b["skus"] += 1
            b["revenue"] += it["revenue"] or 0
            b["inventory_value"] += it["inventory_value"] or 0
            b["at_risk"] += it["status"] == "stockout_risk"

    at_risk = sorted(
        (i for i in items if i["status"] in ("stockout_risk", "reorder")),
        key=lambda i: (i["status"] != "stockout_risk", str(i["stockout_date"] or "9999"), -(i["revenue"] or 0)),
    )[:8]
    sim = db.execute(select(SimulationRun).order_by(SimulationRun.id.desc()).limit(1)).scalar_one_or_none()

    # Total demand (last 90 days, by week) for the trend sparkline
    last = db.execute(select(func.max(Sale.date))).scalar()
    trend = []
    if last:
        week = (
            func.strftime("%Y-%W", Sale.date)
            if db.bind.dialect.name == "sqlite"
            else func.to_char(Sale.date, "IYYY-IW")
        )
        trend = [
            {"week": w, "units": float(u)}
            for w, u in db.execute(
                select(week.label("w"), func.sum(Sale.quantity))
                .where(Sale.date > last - timedelta(days=91))
                .group_by("w")
                .order_by("w")
            ).all()
        ]

    return {
        "as_of": run.history_end if run else None,
        "skus": len(items),
        "inventory_value": sum(i["inventory_value"] or 0 for i in items),
        "value_at_risk": sum(
            (i["revenue"] or 0) / 365 * (i["lead_time_days"] or 0) for i in items if i["status"] == "stockout_risk"
        ),
        "suggested_order_value": sum((i["suggested_order_qty"] or 0) * i["unit_cost"] for i in items),
        "status_counts": status_counts,
        "by_class": by_class,
        "at_risk": at_risk,
        "forecast": {"run_id": run.id, "created_at": run.created_at, **run.summary.get("selected", {})}
        if run
        else None,
        "simulation": {
            "run_id": sim.id,
            "created_at": sim.created_at,
            "comparisons": sim.results.get("comparisons", []),
        }
        if sim
        else None,
        "demand_trend": trend,
    }


SORTABLE = {
    "sku": Product.sku,
    "name": Product.name,
    "revenue": Classification.revenue,
    "on_hand": InventoryPolicy.on_hand,
    "days_of_cover": InventoryPolicy.days_of_cover,
    "stockout_date": InventoryPolicy.stockout_date,
    "avg_daily_demand": InventoryPolicy.avg_daily_demand,
    "suggested_order_qty": InventoryPolicy.suggested_order_qty,
}


@router.get("/products")
def list_products(
    q: str | None = Query(None, max_length=64),
    abc: Literal["A", "B", "C"] | None = None,
    xyz: Literal["X", "Y", "Z"] | None = None,
    status: Literal["stockout_risk", "reorder", "healthy"] | None = None,
    sort: str = "revenue",
    order: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Product, Classification, InventoryPolicy)
        .outerjoin(Classification, Classification.product_id == Product.id)
        .outerjoin(InventoryPolicy, InventoryPolicy.product_id == Product.id)
    )
    if q:
        stmt = stmt.where(
            or_(Product.sku.ilike(f"%{q}%"), Product.name.ilike(f"%{q}%"), Product.category.ilike(f"%{q}%"))
        )
    if abc:
        stmt = stmt.where(Classification.abc == abc)
    if xyz:
        stmt = stmt.where(Classification.xyz == xyz)
    if status:
        stmt = stmt.where(InventoryPolicy.status == status)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    col = SORTABLE.get(sort, Classification.revenue)
    direction = asc(col).nulls_last() if order == "asc" else desc(col).nulls_last()
    rows = db.execute(stmt.order_by(direction, Product.sku).offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [_product_row(p, c, ip) for p, c, ip in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/products/{sku}")
def product_detail(sku: str, history_days: int = Query(180, ge=28, le=1460), db: Session = Depends(get_db)):
    p = db.execute(select(Product).where(Product.sku == sku)).scalar_one_or_none()
    if p is None:
        raise HTTPException(404, "Product not found")
    c = db.get(Classification, p.id)
    ip = db.get(InventoryPolicy, p.id)
    run = _latest_run(db)

    last = db.execute(select(func.max(Sale.date))).scalar()
    history = []
    if last:
        sales = dict(
            db.execute(
                select(Sale.date, Sale.quantity).where(
                    Sale.product_id == p.id, Sale.date > last - timedelta(days=history_days)
                )
            ).all()
        )
        history = [
            {"date": d, "actual": sales.get(d, 0.0)}
            for d in (last - timedelta(days=i) for i in range(history_days - 1, -1, -1))
        ]

    forecast, metrics = [], []
    if run:
        forecast = [
            {"date": f.date, "forecast": f.yhat, "lower": f.yhat_lower, "upper": f.yhat_upper, "model": f.model}
            for f in db.execute(
                select(Forecast).where(Forecast.run_id == run.id, Forecast.product_id == p.id).order_by(Forecast.date)
            ).scalars()
        ]
        metrics = [
            {
                "model": m.model,
                "label": MODELS[m.model].label if m.model in MODELS else m.model,
                "mae": m.mae,
                "rmse": m.rmse,
                "wape": m.wape,
                "mase": m.mase,
                "bias": m.bias,
                "selected": m.selected,
            }
            for m in db.execute(
                select(BacktestMetric)
                .where(BacktestMetric.run_id == run.id, BacktestMetric.product_id == p.id)
                .order_by(BacktestMetric.mase)
            ).scalars()
        ]
    return {
        "product": _product_row(p, c, ip),
        "adi": c.adi if c else None,
        "history": history,
        "forecast": forecast,
        "backtest": metrics,
        "params": {
            "order_cost": p.order_cost,
            "holding_rate": p.holding_rate,
            "moq": p.moq,
            "lead_time_std_days": p.lead_time_std_days,
        },
    }


@router.get("/classification")
def classification(db: Session = Depends(get_db)):
    rows = db.execute(
        select(Product.sku, Product.name, Classification)
        .join(Classification, Classification.product_id == Product.id)
        .order_by(Classification.revenue.desc())
    ).all()
    items = [
        {
            "sku": s,
            "name": n,
            "abc": c.abc,
            "xyz": c.xyz,
            "revenue": c.revenue,
            "revenue_share": c.revenue_share,
            "cumulative_share": c.cumulative_share,
            "cv": c.cv,
            "adi": c.adi,
        }
        for s, n, c in rows
    ]
    matrix: dict[str, dict] = {}
    for it in items:
        cell = matrix.setdefault(f"{it['abc']}{it['xyz']}", {"skus": 0, "revenue_share": 0.0})
        cell["skus"] += 1
        cell["revenue_share"] += it["revenue_share"]
    n = len(items)
    pareto = (
        [
            {"sku_share": (i + 1) / n, "revenue_share": it["cumulative_share"], "abc": it["abc"]}
            for i, it in enumerate(items)
        ]
        if n
        else []
    )
    return {"items": items, "matrix": matrix, "pareto": pareto, "computed_at": rows[0][2].computed_at if rows else None}


@router.get("/forecasts/summary")
def forecasts_summary(db: Session = Depends(get_db)):
    run = _latest_run(db)
    models = [{"name": m.name, "label": m.label, "description": m.description} for m in MODELS.values()]
    if run is None:
        return {"run": None, "models": models}
    by_xyz = db.execute(
        select(Classification.xyz, BacktestMetric.model, func.avg(BacktestMetric.wape), func.count())
        .join(Classification, Classification.product_id == BacktestMetric.product_id)
        .where(BacktestMetric.run_id == run.id)
        .group_by(Classification.xyz, BacktestMetric.model)
    ).all()
    return {
        "run": {
            "id": run.id,
            "created_at": run.created_at,
            "horizon_days": run.horizon_days,
            "folds": run.folds,
            "history_end": run.history_end,
            "summary": run.summary,
        },
        "models": models,
        "wape_by_xyz": [{"xyz": x, "model": m, "wape": float(w), "skus": int(c)} for x, m, w, c in by_xyz],
    }


@router.get("/simulations")
def list_simulations(db: Session = Depends(get_db)):
    runs = db.execute(select(SimulationRun).order_by(SimulationRun.id.desc()).limit(20)).scalars().all()
    return [
        {
            "id": r.id,
            "created_at": r.created_at,
            "replications": r.results.get("replications"),
            "policies": [p["name"] for p in r.results.get("policies", [])],
            "verdicts": [c["verdict"] for c in r.results.get("comparisons", [])],
        }
        for r in runs
    ]


@router.get("/simulations/latest")
def latest_simulation(db: Session = Depends(get_db)):
    run = db.execute(select(SimulationRun).order_by(SimulationRun.id.desc()).limit(1)).scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "No simulation yet")
    return {"id": run.id, "created_at": run.created_at, "params": run.params, "results": run.results}


@router.get("/simulations/{run_id}")
def get_simulation(run_id: int, db: Session = Depends(get_db)):
    run = db.get(SimulationRun, run_id)
    if run is None:
        raise HTTPException(404, "Simulation not found")
    return {"id": run.id, "created_at": run.created_at, "params": run.params, "results": run.results}


@router.post("/simulations", status_code=201)
async def create_simulation(body: SimulationIn):
    data = body.model_dump(exclude={"policies"})
    params = SimParams(**data)
    if body.policies:
        params.policies = [PolicySpec(p.name, p.service_levels) for p in body.policies]

    def _run() -> dict:
        with session_scope() as db:
            try:
                run = run_simulation(db, params)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            return {"id": run.id, "created_at": run.created_at, "params": run.params, "results": run.results}

    return await run_in_threadpool(_run)
