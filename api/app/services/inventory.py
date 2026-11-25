"""Replenishment policy: safety stock, reorder point (ROP) and economic order quantity (EOQ).

Continuous-review (s, Q) policy:

    sigma_LT = sqrt(L * sigma_d^2 + d^2 * sigma_L^2)    demand uncertainty over the lead time
    SS       = z(service level) * sigma_LT
    ROP (s)  = d * L + SS
    EOQ (Q)  = sqrt(2 * D * S / H)                     D annual demand, S order cost, H = c * h

`sigma_d` is the backtested RMSE of the selected forecast model, i.e. the uncertainty of what we
actually plan with, not the raw demand variance (which would overstate it for predictable SKUs).
"""

from datetime import timedelta

import numpy as np
import pandas as pd
from scipy.stats import norm
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import BacktestMetric, Forecast, ForecastRun, InventoryPolicy
from app.services.data import load_classes, load_latest_stock, load_products

STATUS_RISK = "stockout_risk"
STATUS_REORDER = "reorder"
STATUS_HEALTHY = "healthy"


def z_value(service_level: float) -> float:
    return float(norm.ppf(np.clip(service_level, 0.5, 0.9999)))


def safety_stock(z: float, sigma_d, lead_time, mean_d=0.0, sigma_lt=0.0):
    return z * np.sqrt(lead_time * np.square(sigma_d) + np.square(mean_d) * np.square(sigma_lt))


def eoq(annual_demand, order_cost, unit_cost, holding_rate, moq=1):
    holding = np.asarray(unit_cost, dtype=float) * np.asarray(holding_rate, dtype=float)
    q = np.sqrt(
        np.divide(
            2 * np.asarray(annual_demand) * np.asarray(order_cost),
            holding,
            out=np.zeros_like(holding),
            where=holding > 0,
        )
    )
    q = np.ceil(np.maximum(q, 1.0))
    return np.maximum(q, moq)


def default_service_levels() -> dict[str, float]:
    s = get_settings()
    return {"A": s.service_level_a, "B": s.service_level_b, "C": s.service_level_c}


def compute_policy_table(
    products: pd.DataFrame,
    forecast: pd.DataFrame,
    sigma: pd.Series,
    stock: pd.DataFrame,
    classes: pd.DataFrame,
    service_levels: dict[str, float],
    default_level: float = 0.95,
) -> pd.DataFrame:
    """Pure function. `forecast` is (days x product_id) of expected daily demand."""
    ids = [pid for pid in forecast.columns if pid in products.index]
    p = products.loc[ids]
    abc = classes["abc"].reindex(ids) if not classes.empty else pd.Series(index=ids, dtype=object)
    level = abc.map(service_levels).fillna(default_level).astype(float)
    z = level.map(z_value)

    mean_d = forecast[ids].mean(axis=0)
    sig = sigma.reindex(ids).fillna(0.0)
    L = p["lead_time_days"].astype(float)
    ss = safety_stock(z, sig, L, mean_d, p["lead_time_std_days"].astype(float))
    rop = mean_d * L + ss
    q = pd.Series(eoq(mean_d * 365, p["order_cost"], p["unit_cost"], p["holding_rate"], p["moq"]), index=ids)

    on_hand = stock["on_hand"].reindex(ids).fillna(0.0) if not stock.empty else pd.Series(0.0, index=ids)
    on_order = stock["on_order"].reindex(ids).fillna(0.0) if not stock.empty else pd.Series(0.0, index=ids)
    position = on_hand + on_order

    # Projected stock-out: first day cumulative expected demand exceeds available stock.
    # Open orders are assumed to land after one lead time (conservative).
    cum = forecast[ids].cumsum(axis=0).to_numpy()
    days = np.arange(1, len(forecast) + 1)[:, None]
    available = on_hand.to_numpy()[None, :] + np.where(days >= L.to_numpy()[None, :], on_order.to_numpy(), 0.0)
    short = cum > available
    first = np.where(short.any(axis=0), short.argmax(axis=0) + 1, -1)
    stockout_in = pd.Series(np.where(first > 0, first, np.nan), index=ids)

    status = np.where(
        (on_hand <= 0) | (stockout_in <= L),
        STATUS_RISK,
        np.where(position <= rop, STATUS_REORDER, STATUS_HEALTHY),
    )
    need = np.maximum(rop - position, 0.0)
    order_qty = np.where(position <= rop, q * np.ceil((need + 1e-9) / q).clip(lower=1), 0.0)

    return pd.DataFrame(
        {
            "abc": abc,
            "service_level": level,
            "avg_daily_demand": mean_d,
            "demand_std": sig,
            "safety_stock": ss,
            "reorder_point": rop,
            "eoq": q,
            "on_hand": on_hand,
            "on_order": on_order,
            "days_of_cover": np.where(mean_d > 0, on_hand / mean_d.replace(0, np.nan), np.nan),
            "stockout_in_days": stockout_in,
            "suggested_order_qty": order_qty,
            "status": status,
        },
        index=ids,
    )


def latest_forecast_run(db: Session) -> ForecastRun | None:
    return db.execute(select(ForecastRun).order_by(ForecastRun.id.desc()).limit(1)).scalar_one_or_none()


def run_policies(db: Session, service_levels: dict[str, float] | None = None) -> dict:
    run = latest_forecast_run(db)
    if run is None:
        raise ValueError("No forecast run found. Run forecasting first.")

    fc_rows = db.execute(
        select(Forecast.product_id, Forecast.date, Forecast.yhat).where(Forecast.run_id == run.id)
    ).all()
    forecast = (
        pd.DataFrame(fc_rows, columns=["product_id", "date", "yhat"])
        .pivot(index="date", columns="product_id", values="yhat")
        .sort_index()
    )
    sigma_rows = db.execute(
        select(BacktestMetric.product_id, BacktestMetric.rmse).where(
            BacktestMetric.run_id == run.id, BacktestMetric.selected.is_(True)
        )
    ).all()
    sigma = pd.Series(dict(sigma_rows), dtype=float)

    table = compute_policy_table(
        load_products(db),
        forecast,
        sigma,
        load_latest_stock(db),
        load_classes(db),
        service_levels or default_service_levels(),
        get_settings().uniform_service_level,
    )

    db.execute(delete(InventoryPolicy))
    for pid, r in table.iterrows():
        db.add(
            InventoryPolicy(
                product_id=int(pid),
                forecast_run_id=run.id,
                service_level=float(r["service_level"]),
                avg_daily_demand=float(r["avg_daily_demand"]),
                demand_std=float(r["demand_std"]),
                safety_stock=float(r["safety_stock"]),
                reorder_point=float(r["reorder_point"]),
                eoq=float(r["eoq"]),
                on_hand=float(r["on_hand"]),
                on_order=float(r["on_order"]),
                days_of_cover=None if pd.isna(r["days_of_cover"]) else float(r["days_of_cover"]),
                stockout_date=None
                if pd.isna(r["stockout_in_days"])
                else run.history_end + timedelta(days=int(r["stockout_in_days"])),
                suggested_order_qty=float(r["suggested_order_qty"]),
                status=str(r["status"]),
            )
        )
    db.flush()
    counts = dict(db.execute(select(InventoryPolicy.status, func.count()).group_by(InventoryPolicy.status)).all())
    return {"forecast_run_id": run.id, "status_counts": counts}
