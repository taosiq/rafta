"""Load the synthetic demo dataset through the same CSV import path real users take."""

from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    AssistantLog,
    BacktestMetric,
    Classification,
    Forecast,
    ForecastRun,
    InventoryPolicy,
    Product,
    Sale,
    SimulationRun,
    StockSnapshot,
)
from app.services.ingest import import_csv
from app.services.synthetic import generate


def is_empty(db: Session) -> bool:
    return (db.execute(select(func.count()).select_from(Product)).scalar() or 0) == 0


def reset(db: Session) -> None:
    for model in (
        Forecast,
        BacktestMetric,
        ForecastRun,
        InventoryPolicy,
        Classification,
        SimulationRun,
        StockSnapshot,
        Sale,
        AssistantLog,
        Product,
    ):
        db.execute(delete(model))
    db.flush()


def load_demo(db: Session, skus: int = 150, days: int = 730, seed: int = 7) -> dict:
    reset(db)
    data = generate(n_skus=skus, days=days, seed=seed)
    counts = {}
    for kind in ("products", "sales", "stock"):
        report = import_csv(db, kind, data[kind].to_csv(index=False).encode())
        counts[kind] = report.rows
    return counts


def export_sample(directory: Path, skus: int = 150, days: int = 730, seed: int = 7) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    data = generate(n_skus=skus, days=days, seed=seed)
    paths = []
    for kind, df in data.items():
        path = directory / f"{kind}.csv"
        df.to_csv(path, index=False)
        paths.append(path)
    return paths
