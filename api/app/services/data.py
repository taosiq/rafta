"""Helpers that turn database rows into pandas structures for the analytics engine."""

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Classification, Product, Sale, StockSnapshot


def load_products(db: Session) -> pd.DataFrame:
    rows = db.execute(select(Product)).scalars().all()
    df = pd.DataFrame(
        [
            {
                "product_id": p.id,
                "sku": p.sku,
                "name": p.name,
                "category": p.category,
                "unit_cost": p.unit_cost,
                "unit_price": p.unit_price,
                "lead_time_days": p.lead_time_days,
                "lead_time_std_days": p.lead_time_std_days,
                "order_cost": p.order_cost,
                "holding_rate": p.holding_rate,
                "moq": p.moq,
            }
            for p in rows
        ]
    )
    return df.set_index("product_id") if not df.empty else df


def load_sales_matrix(db: Session) -> pd.DataFrame:
    """Daily demand matrix: index = every calendar day, columns = product_id, zero-filled."""
    rows = db.execute(select(Sale.product_id, Sale.date, Sale.quantity)).all()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["product_id", "date", "quantity"])
    df["date"] = pd.to_datetime(df["date"])
    matrix = df.pivot_table(index="date", columns="product_id", values="quantity", aggfunc="sum")
    full_index = pd.date_range(matrix.index.min(), matrix.index.max(), freq="D")
    return matrix.reindex(full_index).fillna(0.0).clip(lower=0.0)


def load_latest_stock(db: Session) -> pd.DataFrame:
    """Most recent stock snapshot per product."""
    rows = db.execute(
        select(StockSnapshot.product_id, StockSnapshot.date, StockSnapshot.on_hand, StockSnapshot.on_order)
    ).all()
    if not rows:
        return pd.DataFrame(columns=["on_hand", "on_order", "date"])
    df = pd.DataFrame(rows, columns=["product_id", "date", "on_hand", "on_order"])
    df = df.sort_values("date").groupby("product_id").tail(1)
    return df.set_index("product_id")


def load_classes(db: Session) -> pd.DataFrame:
    rows = db.execute(select(Classification.product_id, Classification.abc, Classification.xyz)).all()
    if not rows:
        return pd.DataFrame(columns=["abc", "xyz"])
    return pd.DataFrame(rows, columns=["product_id", "abc", "xyz"]).set_index("product_id")
