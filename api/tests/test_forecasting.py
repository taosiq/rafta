import numpy as np
import pandas as pd
import pytest

from app.services.forecasting import (
    MODELS,
    backtest,
    croston_sba,
    metrics,
    predict,
    seasonal_naive,
    select_models,
)


def _weekly_matrix(weeks: int = 30) -> pd.DataFrame:
    pattern = np.array([1, 2, 3, 4, 5, 10, 8], dtype=float)
    y = np.tile(pattern, weeks)
    return pd.DataFrame({1: y, 2: y * 3}, index=pd.date_range("2025-01-06", periods=len(y), freq="D"))


def test_seasonal_naive_repeats_last_week():
    y = np.arange(21, dtype=float)[:, None]
    out = seasonal_naive(y, 10)
    assert out[:7, 0].tolist() == list(range(14, 21))
    assert out[7:, 0].tolist() == [14, 15, 16]


def test_croston_on_regular_intermittent_demand():
    y = np.zeros((100, 1))
    y[::4] = 8.0  # 8 units every 4 days -> rate 2/day
    out = croston_sba(y, 5, alpha=0.1)
    assert out[0, 0] == pytest.approx(2.0 * (1 - 0.05), rel=0.05)
    assert (out == out[0]).all()


@pytest.mark.parametrize("model", list(MODELS))
def test_every_model_returns_non_negative_finite_forecasts(model):
    sales = _weekly_matrix()
    out = predict(model, sales, 14)
    assert out.shape == (14, 2)
    assert np.isfinite(out).all()
    assert (out >= 0).all()


def test_metrics_known_values():
    actual = np.array([[10.0], [10.0], [0.0]])
    forecast = np.array([[12.0], [8.0], [0.0]])
    m = metrics(actual, forecast, scale=np.array([2.0]))
    assert m["mae"][0] == pytest.approx(4 / 3)
    assert m["rmse"][0] == pytest.approx(np.sqrt(8 / 3))
    assert m["wape"][0] == pytest.approx(4 / 20)
    assert m["bias"][0] == pytest.approx(0.0)
    assert m["mase"][0] == pytest.approx((4 / 3) / 2)


def test_backtest_perfect_on_pure_weekly_pattern():
    bt = backtest(_weekly_matrix(), ["seasonal_naive", "moving_average"], horizon=14, folds=3)
    assert bt["seasonal_naive"]["mae"].max() == pytest.approx(0.0, abs=1e-9)
    assert (bt["moving_average"]["mae"] > 0).all()
    assert (select_models(bt) == "seasonal_naive").all()


def test_backtest_has_no_look_ahead(monkeypatch):
    """Each fold's model must only ever see data strictly before that fold's test window."""
    import app.services.forecasting as fc

    sales = _weekly_matrix(40)
    seen: list[pd.Timestamp] = []
    real_predict = fc.predict

    def spy(model, train, h):
        seen.append(train.index[-1])
        return real_predict(model, train, h)

    monkeypatch.setattr(fc, "predict", spy)
    horizon, folds = 14, 3
    fc.backtest(sales, ["ses"], horizon, folds)
    expected_origins = [len(sales) - horizon * k for k in range(folds, 0, -1)]
    assert [sales.index.get_loc(t) + 1 for t in seen] == expected_origins

    # Perturbing data inside a test window changes the score but never the training data.
    tampered = sales.copy()
    tampered.iloc[-1] += 100
    base = backtest(sales, ["ses"], horizon, folds)["ses"]
    changed = backtest(tampered, ["ses"], horizon, folds)["ses"]
    assert (changed["mae"] > base["mae"]).all()


def test_backtest_requires_history():
    short = _weekly_matrix(4)
    with pytest.raises(ValueError, match="Not enough history"):
        backtest(short, ["ses"], horizon=14, folds=3)
