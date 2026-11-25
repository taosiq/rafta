import numpy as np
import pandas as pd
import pytest

from app.services.classification import ClassificationParams, classify


def _matrix(daily: dict[int, np.ndarray]) -> pd.DataFrame:
    n = len(next(iter(daily.values())))
    return pd.DataFrame(daily, index=pd.date_range("2025-01-01", periods=n, freq="D"))


def test_abc_follows_cumulative_revenue_share():
    days = 140
    # revenue shares: 60%, 25%, 10%, 5%
    sales = _matrix({1: np.full(days, 60.0), 2: np.full(days, 25.0), 3: np.full(days, 10.0), 4: np.full(days, 5.0)})
    out = classify(sales, pd.Series({1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0}))
    assert out.loc[1, "abc"] == "A"
    assert out.loc[2, "abc"] == "A"  # cumulative share before it is 60% < 80%
    assert out.loc[3, "abc"] == "B"  # 85% before it, below 95%
    assert out.loc[4, "abc"] == "C"
    assert out["revenue_share"].sum() == pytest.approx(1.0)
    assert out["cumulative_share"].is_monotonic_increasing


def test_price_matters_not_just_volume():
    days = 140
    sales = _matrix({1: np.full(days, 100.0), 2: np.full(days, 1.0)})
    out = classify(sales, pd.Series({1: 1.0, 2: 1000.0}))
    assert out.index[0] == 2  # 1 unit at 1000 beats 100 units at 1


def test_xyz_uses_weekly_coefficient_of_variation():
    rng = np.random.default_rng(0)
    days = 364
    stable = np.full(days, 10.0)
    erratic = np.where(rng.random(days) < 0.03, 300.0, 0.0)
    out = classify(_matrix({1: stable, 2: erratic}), pd.Series({1: 1.0, 2: 1.0}))
    assert out.loc[1, "xyz"] == "X"
    assert out.loc[1, "cv"] == pytest.approx(0.0, abs=1e-9)
    assert out.loc[2, "xyz"] == "Z"
    assert out.loc[2, "adi"] > 10


def test_zero_demand_product_is_c_and_z():
    days = 140
    out = classify(_matrix({1: np.full(days, 5.0), 2: np.zeros(days)}), pd.Series({1: 2.0, 2: 2.0}))
    assert out.loc[2, "abc"] == "C"
    assert out.loc[2, "xyz"] == "Z"


def test_window_limits_history():
    old, recent = np.r_[np.full(300, 100.0), np.zeros(100)], np.r_[np.zeros(300), np.full(100, 10.0)]
    out = classify(_matrix({1: old, 2: recent}), pd.Series({1: 1.0, 2: 1.0}), ClassificationParams(window_days=90))
    assert out.index[0] == 2


def test_empty_input():
    assert classify(pd.DataFrame(), pd.Series(dtype=float)).empty
