import numpy as np
import pandas as pd
import pytest

from app.services.simulation import PolicySpec, SimParams, _bootstrap_index, simulate


def _products(n: int, lead: int = 5, lt_std: float = 0.0) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    return pd.DataFrame(
        {
            "sku": [f"S{i}" for i in range(n)],
            "unit_cost": rng.uniform(2, 20, n),
            "unit_price": rng.uniform(25, 40, n),
            "lead_time_days": lead,
            "lead_time_std_days": lt_std,
            "order_cost": 40.0,
            "holding_rate": 0.25,
            "moq": 1,
        },
        index=range(n),
    )


def _sales(n: int, days: int = 300, noisy: bool = True, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    levels = np.exp(rng.normal(1.5, 1.0, n))  # Pareto-ish revenue so ABC has all classes
    data = rng.poisson(np.tile(levels, (days, 1))) if noisy else np.tile(np.round(levels), (days, 1))
    return pd.DataFrame(data.astype(float), index=pd.date_range("2025-01-01", periods=days, freq="D"))


def test_constant_demand_never_stocks_out():
    params = SimParams(replications=1, holdout_days=90, lead_time_variability=False)
    out = simulate(_sales(12, noisy=False), _products(12), params)
    for p in out["policies"]:
        assert p["overall"]["fill_rate"] == pytest.approx(1.0)
        assert p["overall"]["stockout_days"] == 0


def test_frontier_is_monotonic_in_service_level():
    params = SimParams(replications=8, holdout_days=90, frontier_levels=[0.75, 0.9, 0.99])
    out = simulate(_sales(30), _products(30), params)
    fill = [f["fill_rate"] for f in out["frontier"]]
    holding = [f["holding_cost"] for f in out["frontier"]]
    assert fill == sorted(fill)
    assert holding == sorted(holding)


def test_results_are_reproducible_with_same_seed():
    params = SimParams(replications=4, holdout_days=90)
    a = simulate(_sales(15), _products(15), params)
    b = simulate(_sales(15), _products(15), params)
    assert a["comparisons"] == b["comparisons"]


def test_identical_policies_have_zero_difference():
    """Common random numbers: two identical policies must produce identical results."""
    params = SimParams(
        replications=5, holdout_days=90, policies=[PolicySpec("U1", {"*": 0.95}), PolicySpec("U2", {"*": 0.95})]
    )
    cmp = simulate(_sales(20), _products(20), params)["comparisons"][0]
    assert cmp["total_cost"]["mean_diff"] == pytest.approx(0.0)
    assert cmp["verdict"] != "dominates"


def test_costs_add_up_and_classes_cover_all_skus():
    out = simulate(_sales(25), _products(25), SimParams(replications=3, holdout_days=90))
    assert sum(out["class_counts"].values()) == 25
    o = out["policies"][0]["overall"]
    assert o["total_cost"] == pytest.approx(o["holding_cost"] + o["ordering_cost"] + o["shortage_cost"])
    assert len(out["per_sku"]) == 25
    assert len(out["policies"][0]["trajectory"]) == 90


def test_lead_time_variability_increases_stockouts():
    sales = _sales(30)
    base = SimParams(
        replications=6, holdout_days=90, policies=[PolicySpec("U", {"*": 0.9}), PolicySpec("U2", {"*": 0.9})]
    )
    fixed = simulate(sales, _products(30, lead=7, lt_std=0), base)
    var_params = SimParams(**{**base.__dict__, "lead_time_variability": True})
    variable = simulate(sales, _products(30, lead=7, lt_std=3.0), var_params)
    assert variable["policies"][0]["overall"]["fill_rate"] <= fixed["policies"][0]["overall"]["fill_rate"]


def test_bootstrap_index_shape_and_range():
    idx = _bootstrap_index(90, 7, np.random.default_rng(0))
    assert len(idx) == 90
    assert idx.min() >= 0 and idx.max() < 90


def test_rejects_too_short_history():
    with pytest.raises(ValueError, match="Need at least"):
        simulate(_sales(5, days=100), _products(5), SimParams(holdout_days=90))
