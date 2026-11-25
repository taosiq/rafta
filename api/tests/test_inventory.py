import numpy as np
import pandas as pd
import pytest

from app.services.inventory import compute_policy_table, eoq, safety_stock, z_value


def test_z_values_match_normal_table():
    assert z_value(0.95) == pytest.approx(1.6449, abs=1e-3)
    assert z_value(0.99) == pytest.approx(2.3263, abs=1e-3)
    assert z_value(0.5) == pytest.approx(0.0)


def test_eoq_textbook_example():
    # D = 1000/yr, S = 50, c = 10, h = 20% -> sqrt(2*1000*50/2) = 223.6 -> rounded up to 224
    assert eoq(1000, 50, 10, 0.2)[()] == 224
    assert eoq(1000, 50, 10, 0.2, moq=500)[()] == 500
    assert eoq(0, 50, 10, 0.2)[()] == 1  # never zero


def test_safety_stock_components():
    assert safety_stock(1.645, 0.0, 7) == 0.0
    assert safety_stock(2.0, 3.0, 4) == pytest.approx(2.0 * np.sqrt(4 * 9))
    # Lead-time variability adds d^2 * sigma_L^2
    assert safety_stock(1.0, 0.0, 4, mean_d=10, sigma_lt=2) == pytest.approx(20.0)


def _inputs(on_hand: list[float], demand: float = 10.0, horizon: int = 28):
    ids = list(range(1, len(on_hand) + 1))
    products = pd.DataFrame(
        {
            "unit_cost": 5.0,
            "unit_price": 10.0,
            "lead_time_days": 7,
            "lead_time_std_days": 0.0,
            "order_cost": 50.0,
            "holding_rate": 0.25,
            "moq": 1,
        },
        index=ids,
    )
    forecast = pd.DataFrame(demand, index=pd.date_range("2026-01-01", periods=horizon), columns=ids)
    stock = pd.DataFrame({"on_hand": on_hand, "on_order": 0.0}, index=ids)
    classes = pd.DataFrame({"abc": ["A"] * len(ids), "xyz": ["X"] * len(ids)}, index=ids)
    return products, forecast, pd.Series(2.0, index=ids), stock, classes


def test_policy_status_thresholds():
    table = compute_policy_table(*_inputs([0, 40, 90, 1000]), service_levels={"A": 0.95})
    # ROP = 10*7 + 1.645*2*sqrt(7) = 78.7
    assert table.loc[1, "status"] == "stockout_risk"  # empty shelf
    assert table.loc[2, "status"] == "stockout_risk"  # 4 days of cover < lead time 7
    assert table.loc[3, "status"] == "healthy"  # above ROP
    assert table.loc[4, "status"] == "healthy"
    assert table.loc[2, "stockout_in_days"] == 5  # 40 units cover days 1-4; day 5 is short
    assert np.isnan(table.loc[4, "stockout_in_days"])  # not within the horizon
    assert table.loc[3, "reorder_point"] == pytest.approx(70 + 1.6449 * 2 * np.sqrt(7), abs=0.01)


def test_reorder_quantity_is_multiple_of_eoq_and_restores_position():
    table = compute_policy_table(*_inputs([75.0]), service_levels={"A": 0.95})
    row = table.loc[1]
    assert row["status"] == "reorder"
    assert row["suggested_order_qty"] % row["eoq"] == 0
    assert row["on_hand"] + row["suggested_order_qty"] > row["reorder_point"]


def test_higher_service_level_means_more_safety_stock():
    low = compute_policy_table(*_inputs([100]), service_levels={"A": 0.90})
    high = compute_policy_table(*_inputs([100]), service_levels={"A": 0.99})
    assert high.loc[1, "safety_stock"] > low.loc[1, "safety_stock"]
