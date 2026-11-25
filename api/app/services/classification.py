"""ABC (value) and XYZ (variability) classification.

ABC: products ranked by revenue over the analysis window. The top products that make up
`a_cut` of cumulative revenue are A, up to `b_cut` are B, the rest are C.

XYZ: coefficient of variation (CV = std / mean) of *weekly* demand. Weekly buckets are used
because daily CV is dominated by day-of-week noise. X = stable, Y = variable, Z = erratic.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import Classification
from app.services.data import load_products, load_sales_matrix


@dataclass(frozen=True)
class ClassificationParams:
    window_days: int = 365
    a_cut: float = 0.80
    b_cut: float = 0.95
    x_cv: float = 0.50
    y_cv: float = 1.00


def classify(sales: pd.DataFrame, prices: pd.Series, params: ClassificationParams | None = None) -> pd.DataFrame:
    """Pure function: daily demand matrix + unit prices -> classification table."""
    params = params or ClassificationParams()
    if sales.empty:
        return pd.DataFrame(columns=["abc", "xyz", "revenue", "revenue_share", "cumulative_share", "cv", "adi"])

    window = sales.iloc[-params.window_days :]
    prices = prices.reindex(window.columns).fillna(0.0)
    revenue = (window.sum(axis=0) * prices).sort_values(ascending=False)
    total = float(revenue.sum()) or 1.0
    share = revenue / total
    cumulative = share.cumsum()

    # A product is A if the cumulative share *before* it is still below the cut,
    # which guarantees at least one A item and avoids off-by-one at the boundary.
    prior = cumulative - share
    abc = np.where(prior < params.a_cut, "A", np.where(prior < params.b_cut, "B", "C"))

    # Only complete weeks: partial weeks at the window edges would inflate the CV.
    days_per_week = window.iloc[:, 0].resample("W").size()
    weekly = window.resample("W").sum()[days_per_week == 7]
    if weekly.empty:
        weekly = window.resample("W").sum()
    mean = weekly.mean(axis=0)
    std = weekly.std(axis=0, ddof=0)
    cv = (std / mean.replace(0, np.nan)).fillna(np.inf)

    nonzero_days = (window > 0).sum(axis=0)
    adi = (len(window) / nonzero_days.replace(0, np.nan)).fillna(float(len(window)))

    out = pd.DataFrame(
        {
            "abc": pd.Series(abc, index=revenue.index),
            "revenue": revenue,
            "revenue_share": share,
            "cumulative_share": cumulative,
        }
    )
    out["cv"] = cv.reindex(out.index)
    out["adi"] = adi.reindex(out.index)
    out["xyz"] = np.where(out["cv"] <= params.x_cv, "X", np.where(out["cv"] <= params.y_cv, "Y", "Z"))
    return out


def run_classification(db: Session, params: ClassificationParams | None = None) -> dict:
    products = load_products(db)
    sales = load_sales_matrix(db)
    if products.empty or sales.empty:
        raise ValueError("No products or sales data. Import data first.")

    table = classify(sales, products["unit_price"], params)
    db.execute(delete(Classification))
    for product_id, row in table.iterrows():
        db.add(
            Classification(
                product_id=int(product_id),
                abc=row["abc"],
                xyz=row["xyz"],
                revenue=float(row["revenue"]),
                revenue_share=float(row["revenue_share"]),
                cumulative_share=float(row["cumulative_share"]),
                cv=float(min(row["cv"], 99.0)),
                adi=float(row["adi"]),
            )
        )
    db.flush()
    matrix = table.groupby(["abc", "xyz"]).size().to_dict()
    return {
        "products": int(len(table)),
        "matrix": {f"{a}{x}": int(n) for (a, x), n in matrix.items()},
    }
