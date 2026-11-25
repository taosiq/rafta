"""Demand forecasting with rolling-origin backtesting and per-SKU model selection.

Every model works on a *matrix* (rows = days, columns = SKUs) and returns an (h x n) array of
point forecasts. Local models are fitted per column; LightGBM is a single global model trained
across all SKUs on mean-scaled demand, which lets sparse SKUs borrow strength from dense ones.

Backtesting uses expanding-window rolling origins: for fold k the model sees data up to origin_k
and is scored on the next `h` days. No information from the test window ever reaches the fit.
"""

import logging
import warnings
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.models import BacktestMetric, Forecast, ForecastRun
from app.services.data import load_classes, load_sales_matrix

log = logging.getLogger(__name__)

SEASON = 7
Z_80 = 1.2816  # two-sided 80% prediction interval


# --------------------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------------------


def seasonal_naive(y: np.ndarray, h: int) -> np.ndarray:
    """Repeat the last observed week. The benchmark every other model must beat."""
    last = y[-SEASON:]
    reps = int(np.ceil(h / SEASON))
    return np.tile(last, (reps, 1))[:h]


def moving_average(y: np.ndarray, h: int, window: int = 28) -> np.ndarray:
    return np.repeat(y[-window:].mean(axis=0, keepdims=True), h, axis=0)


def ses(y: np.ndarray, h: int, alphas=(0.05, 0.1, 0.2, 0.3, 0.5)) -> np.ndarray:
    """Simple exponential smoothing, vectorised over SKUs; alpha picked by in-sample SSE."""
    best_level = np.zeros(y.shape[1])
    best_sse = np.full(y.shape[1], np.inf)
    for a in alphas:
        level = y[: SEASON * 4].mean(axis=0)
        sse = np.zeros(y.shape[1])
        for t in range(y.shape[0]):
            err = y[t] - level
            sse += err * err
            level = level + a * err
        better = sse < best_sse
        best_sse[better] = sse[better]
        best_level[better] = level[better]
    return np.repeat(best_level[None, :], h, axis=0)


def croston_sba(y: np.ndarray, h: int, alpha: float = 0.1) -> np.ndarray:
    """Croston's method with the Syntetos-Boylan bias correction, for intermittent demand."""
    out = np.zeros(y.shape[1])
    for j in range(y.shape[1]):
        series = y[:, j]
        nz = np.flatnonzero(series > 0)
        if len(nz) == 0:
            continue
        # Initialise with average size and interval (more stable than the first observation).
        z = float(series[nz].mean())
        p = float(np.diff(np.r_[-1, nz]).mean())
        q = 1
        for t in range(nz[0] + 1, len(series)):
            if series[t] > 0:
                z += alpha * (series[t] - z)
                p += alpha * (q - p)
                q = 1
            else:
                q += 1
        out[j] = (1 - alpha / 2) * z / p
    return np.repeat(out[None, :], h, axis=0)


def holt_winters(y: np.ndarray, h: int, max_history: int = 365) -> np.ndarray:
    """Damped additive-trend, additive weekly seasonality ETS (statsmodels)."""
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    y = y[-max_history:]
    out = np.zeros((h, y.shape[1]))
    for j in range(y.shape[1]):
        series = y[:, j]
        if series.sum() == 0 or len(series) < SEASON * 4 or (series > 0).mean() < 0.3:
            out[:, j] = seasonal_naive(series[:, None], h)[:, 0]
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fit = ExponentialSmoothing(
                    series,
                    trend="add",
                    damped_trend=True,
                    seasonal="add",
                    seasonal_periods=SEASON,
                    initialization_method="estimated",
                ).fit(optimized=True, use_brute=False)
            out[:, j] = fit.forecast(h)
        except Exception:  # numerical failure -> fall back, never crash the run
            out[:, j] = seasonal_naive(series[:, None], h)[:, 0]
    return out


def lightgbm_global(y: np.ndarray, h: int, dates: pd.DatetimeIndex, max_history: int = 365) -> np.ndarray:
    """One LightGBM model for all SKUs, recursive multi-step, Tweedie loss on scaled demand."""
    import lightgbm as lgb

    lags = (1, 7, 14, 28)
    scale = np.maximum(y[-90:].mean(axis=0), 1e-3)
    ys = y / scale
    n = ys.shape[1]
    log_scale = np.log1p(scale)

    def features(hist: np.ndarray, t: int, day: pd.Timestamp) -> np.ndarray:
        cols = [hist[t - lag] for lag in lags]
        cols.append(hist[t - 7 : t].mean(axis=0))
        cols.append(hist[t - 28 : t].mean(axis=0))
        cols.append((hist[t - 28 : t] > 0).mean(axis=0))
        cols.append(np.full(n, day.dayofweek))
        cols.append(np.full(n, np.sin(2 * np.pi * day.dayofyear / 365.25)))
        cols.append(np.full(n, np.cos(2 * np.pi * day.dayofyear / 365.25)))
        cols.append(log_scale)
        return np.column_stack(cols)

    start = max(28, len(ys) - max_history)
    X = np.vstack([features(ys, t, dates[t]) for t in range(start, len(ys))])
    target = np.concatenate([ys[t] for t in range(start, len(ys))])
    params = {
        "objective": "tweedie",
        "learning_rate": 0.05,
        "num_leaves": 31,
        "min_data_in_leaf": 50,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "feature_fraction": 0.9,
        "seed": 42,
        "deterministic": True,
        "num_threads": 2,
        "verbose": -1,
    }
    model = lgb.train(params, lgb.Dataset(X, label=target), num_boost_round=250)

    hist = np.vstack([ys, np.zeros((h, n))])
    future = pd.date_range(dates[-1] + pd.Timedelta(days=1), periods=h, freq="D")
    for step in range(h):
        t = len(ys) + step
        hist[t] = np.maximum(model.predict(features(hist, t, future[step])), 0.0)
    return hist[len(ys) :] * scale


@dataclass(frozen=True)
class ModelSpec:
    name: str
    label: str
    description: str
    fn: Callable[..., np.ndarray]
    needs_dates: bool = False


MODELS: dict[str, ModelSpec] = {
    m.name: m
    for m in [
        ModelSpec("seasonal_naive", "Seasonal naive", "Repeats last week. Benchmark.", seasonal_naive),
        ModelSpec("moving_average", "Moving average (28d)", "Mean of the last 4 weeks.", moving_average),
        ModelSpec("ses", "Exponential smoothing", "SES with alpha tuned per SKU.", ses),
        ModelSpec("holt_winters", "Holt-Winters ETS", "Damped trend + weekly seasonality.", holt_winters),
        ModelSpec("croston", "Croston (SBA)", "For intermittent, lumpy demand.", croston_sba),
        ModelSpec("lightgbm", "LightGBM global", "Gradient boosting across all SKUs.", lightgbm_global, True),
    ]
}


def available_models(enable_lightgbm: bool = True) -> list[str]:
    names = list(MODELS)
    if not enable_lightgbm:
        names.remove("lightgbm")
    else:
        try:
            import lightgbm  # noqa: F401
        except Exception:  # pragma: no cover - optional dependency
            names.remove("lightgbm")
    return names


def predict(model: str, train: pd.DataFrame, h: int) -> np.ndarray:
    spec = MODELS[model]
    y = train.to_numpy(dtype=float)
    out = spec.fn(y, h, train.index) if spec.needs_dates else spec.fn(y, h)
    return np.clip(np.nan_to_num(out, nan=0.0, posinf=0.0), 0.0, None)


# --------------------------------------------------------------------------------------
# Backtesting
# --------------------------------------------------------------------------------------


def metrics(actual: np.ndarray, forecast: np.ndarray, scale: np.ndarray) -> dict[str, np.ndarray]:
    """Per-column accuracy metrics. `scale` is the in-sample seasonal-naive MAE (for MASE)."""
    err = forecast - actual
    abs_sum = np.abs(actual).sum(axis=0)
    denom = np.where(abs_sum > 0, abs_sum, np.nan)
    mae = np.abs(err).mean(axis=0)
    return {
        "mae": mae,
        "rmse": np.sqrt((err**2).mean(axis=0)),
        "wape": np.nan_to_num(np.abs(err).sum(axis=0) / denom, nan=0.0),
        "bias": np.nan_to_num(err.sum(axis=0) / denom, nan=0.0),
        "mase": mae / np.where(scale > 0, scale, 1.0),
        "volume": abs_sum,  # used to volume-weight WAPE in summaries
    }


def backtest(sales: pd.DataFrame, models: list[str], horizon: int, folds: int) -> dict[str, pd.DataFrame]:
    """Rolling-origin evaluation. Returns {model: DataFrame[product_id x metric]}."""
    T = len(sales)
    min_train = 8 * SEASON
    origins = [T - horizon * k for k in range(folds, 0, -1) if T - horizon * k >= min_train]
    if not origins:
        raise ValueError(f"Not enough history for backtesting: need > {min_train + horizon} days.")

    first_train = sales.iloc[: origins[0]].to_numpy()
    scale = np.abs(first_train[SEASON:] - first_train[:-SEASON]).mean(axis=0)

    results: dict[str, pd.DataFrame] = {}
    for model in models:
        actual_all, fc_all = [], []
        for origin in origins:
            train = sales.iloc[:origin]
            test = sales.iloc[origin : origin + horizon].to_numpy()
            actual_all.append(test)
            fc_all.append(predict(model, train, len(test)))
        m = metrics(np.vstack(actual_all), np.vstack(fc_all), scale)
        results[model] = pd.DataFrame(m, index=sales.columns)
        log.info("backtest %s: median MASE %.3f", model, float(np.median(m["mase"])))
    return results


def select_models(bt: dict[str, pd.DataFrame], criterion: str = "mase") -> pd.Series:
    """Pick the best model per SKU (lowest criterion). Ties go to the simpler (earlier) model."""
    table = pd.DataFrame({name: df[criterion] for name, df in bt.items()})
    return table.idxmin(axis=1)


# --------------------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------------------


def run_forecasts(db: Session, horizon: int = 28, folds: int = 3, enable_lightgbm: bool = True) -> ForecastRun:
    sales = load_sales_matrix(db)
    if sales.empty:
        raise ValueError("No sales data. Import data first.")

    models = available_models(enable_lightgbm)
    bt = backtest(sales, models, horizon, folds)
    selected = select_models(bt)

    # Final forecasts: refit each selected model on all history, once per model.
    future_dates = pd.date_range(sales.index[-1] + pd.Timedelta(days=1), periods=horizon, freq="D")
    final = pd.DataFrame(0.0, index=future_dates, columns=sales.columns)
    for model in selected.unique():
        cols = list(selected.index[selected == model])
        if MODELS[model].needs_dates:  # global model: train on every SKU, keep the selected ones
            pred = pd.DataFrame(predict(model, sales, horizon), index=future_dates, columns=sales.columns)
            final[cols] = pred[cols].to_numpy()
        else:
            final[cols] = predict(model, sales[cols], horizon)

    run = ForecastRun(
        horizon_days=horizon,
        folds=folds,
        history_end=sales.index[-1].date(),
        models=models,
        summary=_summarise(db, bt, selected),
    )
    db.add(run)
    db.flush()

    rmse = pd.Series({pid: bt[selected[pid]].at[pid, "rmse"] for pid in sales.columns})
    rows = []
    for pid in sales.columns:
        band = Z_80 * float(rmse[pid])
        for day, value in final[pid].items():
            rows.append(
                {
                    "run_id": run.id,
                    "product_id": int(pid),
                    "date": day.date(),
                    "yhat": float(value),
                    "yhat_lower": max(0.0, float(value) - band),
                    "yhat_upper": float(value) + band,
                    "model": selected[pid],
                }
            )
    db.execute(Forecast.__table__.insert(), rows)

    metric_rows = []
    for model, df in bt.items():
        for pid, r in df.iterrows():
            metric_rows.append(
                {
                    "run_id": run.id,
                    "product_id": int(pid),
                    "model": model,
                    **{k: float(r[k]) for k in ("mae", "rmse", "wape", "mase", "bias")},
                    "selected": bool(selected[pid] == model),
                }
            )
    db.execute(BacktestMetric.__table__.insert(), metric_rows)
    db.flush()
    return run


def _summarise(db: Session, bt: dict[str, pd.DataFrame], selected: pd.Series) -> dict:
    """Aggregate accuracy, so the dashboard does not have to recompute it."""
    classes = load_classes(db)

    def weighted(df: pd.DataFrame, col: str) -> float:
        vol = df["volume"].sum()
        return float((df[col] * df["volume"]).sum() / vol) if vol > 0 else 0.0

    per_model = {
        name: {
            "median_mase": float(df["mase"].median()),
            "mean_wape": float(df["wape"].mean()),
            "weighted_wape": weighted(df, "wape"),
            "mean_bias": float(df["bias"].mean()),
        }
        for name, df in bt.items()
    }
    sel = pd.DataFrame(
        {k: [bt[m].at[pid, k] for pid, m in selected.items()] for k in ("mase", "wape", "bias", "volume")},
        index=selected.index,
    )
    by_class: dict[str, dict] = {}
    if not classes.empty:
        sel = sel.join(classes, how="left")
        for cls, grp in sel.groupby("abc"):
            by_class[str(cls)] = {
                "median_mase": float(grp["mase"].median()),
                "mean_wape": float(grp["wape"].mean()),
                "weighted_wape": weighted(grp, "wape"),
                "skus": int(len(grp)),
            }
    baseline = bt["seasonal_naive"]["mase"].median()
    return {
        "per_model": per_model,
        "selected_counts": {k: int(v) for k, v in selected.value_counts().items()},
        "selected": {
            "median_mase": float(sel["mase"].median()),
            "mean_wape": float(sel["wape"].mean()),
            "weighted_wape": weighted(sel, "wape"),
            "mean_bias": float(sel["bias"].mean()),
            "weighted_bias": weighted(sel, "bias"),
            "improvement_vs_naive": float(1 - sel["mase"].median() / baseline) if baseline else 0.0,
        },
        "by_class": by_class,
    }
