"""CSV import with strict validation.

Three file kinds are supported:

* products: sku,name,category,unit_cost,unit_price,lead_time_days,lead_time_std_days,order_cost,holding_rate,moq
* sales:    date,sku,quantity
* stock:    date,sku,on_hand,on_order

Errors are collected per row (capped) and returned, never raised half-way through: either the
whole file is valid and imported, or nothing is written.
"""

import io
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd
from sqlalchemy import and_, delete, insert, select
from sqlalchemy.orm import Session

from app.models import Product, Sale, StockSnapshot

Kind = Literal["products", "sales", "stock"]

SCHEMAS: dict[str, dict[str, list[str]]] = {
    "products": {
        "required": ["sku", "name", "unit_cost", "unit_price"],
        "optional": ["category", "lead_time_days", "lead_time_std_days", "order_cost", "holding_rate", "moq"],
    },
    "sales": {"required": ["date", "sku", "quantity"], "optional": []},
    "stock": {"required": ["date", "sku", "on_hand"], "optional": ["on_order"]},
}

PRODUCT_DEFAULTS = {
    "category": "General",
    "lead_time_days": 7,
    "lead_time_std_days": 0.0,
    "order_cost": 50.0,
    "holding_rate": 0.25,
    "moq": 1,
}

MAX_ERRORS = 50


@dataclass
class ImportReport:
    kind: str
    rows: int = 0
    inserted: int = 0
    updated: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


class ImportValidationError(ValueError):
    def __init__(self, report: ImportReport):
        super().__init__("; ".join(report.errors[:3]))
        self.report = report


def _read(content: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False)
    df.columns = [c.strip().lower() for c in df.columns]
    return df.apply(lambda s: s.str.strip())


def _numeric(df: pd.DataFrame, col: str, report: ImportReport, *, min_value: float = 0.0, integer=False):
    values = pd.to_numeric(df[col], errors="coerce")
    bad = values.isna() | (values < min_value)
    if integer:
        bad |= values.notna() & (values % 1 != 0)
    for idx in df.index[bad][:MAX_ERRORS]:
        report.errors.append(f"row {idx + 2}: '{col}' must be a number >= {min_value} (got '{df.at[idx, col]}')")
    return values


def _dates(df: pd.DataFrame, report: ImportReport) -> pd.Series:
    values = pd.to_datetime(df["date"], errors="coerce", format="mixed")
    for idx in df.index[values.isna()][:MAX_ERRORS]:
        report.errors.append(f"row {idx + 2}: invalid date '{df.at[idx, 'date']}' (use YYYY-MM-DD)")
    return values.dt.date


def validate(kind: Kind, content: bytes) -> tuple[pd.DataFrame, ImportReport]:
    report = ImportReport(kind=kind)
    try:
        df = _read(content)
    except Exception as exc:  # malformed CSV
        report.errors.append(f"could not parse CSV: {exc}")
        return pd.DataFrame(), report

    report.rows = len(df)
    schema = SCHEMAS[kind]
    missing = [c for c in schema["required"] if c not in df.columns]
    if missing:
        report.errors.append(f"missing required column(s): {', '.join(missing)}")
        return df, report
    if df.empty:
        report.errors.append("file has no data rows")
        return df, report

    empty_sku = df["sku"] == ""
    for idx in df.index[empty_sku][:MAX_ERRORS]:
        report.errors.append(f"row {idx + 2}: 'sku' is empty")

    if kind == "products":
        for col, default in PRODUCT_DEFAULTS.items():
            if col not in df.columns:
                df[col] = str(default)
            df[col] = df[col].replace("", str(default))
        df["unit_cost"] = _numeric(df, "unit_cost", report, min_value=0.0)
        df["unit_price"] = _numeric(df, "unit_price", report, min_value=0.0)
        df["lead_time_days"] = _numeric(df, "lead_time_days", report, min_value=0, integer=True)
        df["lead_time_std_days"] = _numeric(df, "lead_time_std_days", report)
        df["order_cost"] = _numeric(df, "order_cost", report)
        df["holding_rate"] = _numeric(df, "holding_rate", report)
        df["moq"] = _numeric(df, "moq", report, min_value=1, integer=True)
        dupes = df["sku"].duplicated()
        for idx in df.index[dupes][:MAX_ERRORS]:
            report.errors.append(f"row {idx + 2}: duplicate sku '{df.at[idx, 'sku']}'")
    elif kind == "sales":
        df["date"] = _dates(df, report)
        df["quantity"] = _numeric(df, "quantity", report)
    else:
        if "on_order" not in df.columns:
            df["on_order"] = "0"
        df["on_order"] = df["on_order"].replace("", "0")
        df["date"] = _dates(df, report)
        df["on_hand"] = _numeric(df, "on_hand", report)
        df["on_order"] = _numeric(df, "on_order", report)

    report.errors = report.errors[:MAX_ERRORS]
    return df, report


def import_csv(db: Session, kind: Kind, content: bytes) -> ImportReport:
    df, report = validate(kind, content)
    if report.errors:
        raise ImportValidationError(report)

    if kind == "products":
        _import_products(db, df, report)
    else:
        sku_to_id = dict(db.execute(select(Product.sku, Product.id)).all())
        unknown = sorted(set(df["sku"]) - set(sku_to_id))
        if unknown:
            preview = ", ".join(unknown[:10])
            report.errors.append(
                f"{len(unknown)} unknown sku(s): {preview}{'...' if len(unknown) > 10 else ''}. Import products first."
            )
            raise ImportValidationError(report)
        df["product_id"] = df["sku"].map(sku_to_id)
        if kind == "sales":
            _replace_timeseries(
                db, Sale, df.groupby(["product_id", "date"], as_index=False)["quantity"].sum(), ["quantity"], report
            )
        else:
            agg = df.groupby(["product_id", "date"], as_index=False)[["on_hand", "on_order"]].last()
            _replace_timeseries(db, StockSnapshot, agg, ["on_hand", "on_order"], report)
    db.flush()
    return report


def _import_products(db: Session, df: pd.DataFrame, report: ImportReport) -> None:
    existing = {p.sku: p for p in db.execute(select(Product)).scalars()}
    fields = [
        "name",
        "category",
        "unit_cost",
        "unit_price",
        "lead_time_days",
        "lead_time_std_days",
        "order_cost",
        "holding_rate",
        "moq",
    ]
    for rec in df.to_dict("records"):
        values = {f: rec[f] for f in fields}
        values["lead_time_days"] = int(values["lead_time_days"])
        values["moq"] = int(values["moq"])
        if rec["sku"] in existing:
            for k, v in values.items():
                setattr(existing[rec["sku"]], k, v)
            report.updated += 1
        else:
            db.add(Product(sku=rec["sku"], **values))
            report.inserted += 1


def _replace_timeseries(db: Session, model, df: pd.DataFrame, value_cols: list[str], report: ImportReport) -> None:
    """Re-importing a file replaces each SKU's rows inside the file's date range (idempotent)."""
    for pid, group in df.groupby("product_id"):
        lo, hi = group["date"].min(), group["date"].max()
        res = db.execute(delete(model).where(and_(model.product_id == int(pid), model.date >= lo, model.date <= hi)))
        report.updated += res.rowcount or 0
    records = [
        {"product_id": int(r["product_id"]), "date": r["date"], **{c: float(r[c]) for c in value_cols}}
        for r in df.to_dict("records")
    ]
    for i in range(0, len(records), 5000):
        db.execute(insert(model), records[i : i + 5000])
    report.inserted = len(records)  # rows written; report.updated counts rows they replaced
