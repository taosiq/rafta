"""ORM models. Types are kept portable so the same schema runs on PostgreSQL and SQLite."""

from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(128), default="General")
    unit_cost: Mapped[float] = mapped_column(Float)
    unit_price: Mapped[float] = mapped_column(Float)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=7)
    lead_time_std_days: Mapped[float] = mapped_column(Float, default=0.0)
    order_cost: Mapped[float] = mapped_column(Float, default=50.0)
    holding_rate: Mapped[float] = mapped_column(Float, default=0.25)  # annual, fraction of unit cost
    moq: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    sales: Mapped[list["Sale"]] = relationship(back_populates="product", cascade="all, delete-orphan")


class Sale(Base):
    __tablename__ = "sales"
    __table_args__ = (UniqueConstraint("product_id", "date", name="uq_sales_product_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    quantity: Mapped[float] = mapped_column(Float)

    product: Mapped[Product] = relationship(back_populates="sales")


class StockSnapshot(Base):
    __tablename__ = "stock_snapshots"
    __table_args__ = (UniqueConstraint("product_id", "date", name="uq_stock_product_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date)
    on_hand: Mapped[float] = mapped_column(Float)
    on_order: Mapped[float] = mapped_column(Float, default=0.0)


class Classification(Base):
    """Latest ABC/XYZ class per product (overwritten on each run)."""

    __tablename__ = "classifications"

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    abc: Mapped[str] = mapped_column(String(1), index=True)
    xyz: Mapped[str] = mapped_column(String(1), index=True)
    revenue: Mapped[float] = mapped_column(Float)
    revenue_share: Mapped[float] = mapped_column(Float)
    cumulative_share: Mapped[float] = mapped_column(Float)
    cv: Mapped[float] = mapped_column(Float)  # coefficient of variation of weekly demand
    adi: Mapped[float] = mapped_column(Float)  # average demand interval (days)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ForecastRun(Base):
    __tablename__ = "forecast_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    horizon_days: Mapped[int] = mapped_column(Integer)
    folds: Mapped[int] = mapped_column(Integer)
    history_end: Mapped[date] = mapped_column(Date)
    models: Mapped[list] = mapped_column(JSON)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)


class Forecast(Base):
    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("forecast_runs.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date)
    yhat: Mapped[float] = mapped_column(Float)
    yhat_lower: Mapped[float] = mapped_column(Float)
    yhat_upper: Mapped[float] = mapped_column(Float)
    model: Mapped[str] = mapped_column(String(32))


class BacktestMetric(Base):
    __tablename__ = "backtest_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("forecast_runs.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    model: Mapped[str] = mapped_column(String(32))
    mae: Mapped[float] = mapped_column(Float)
    rmse: Mapped[float] = mapped_column(Float)
    wape: Mapped[float] = mapped_column(Float)
    mase: Mapped[float] = mapped_column(Float)
    bias: Mapped[float] = mapped_column(Float)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)


class InventoryPolicy(Base):
    """Current replenishment parameters per product (overwritten on each run)."""

    __tablename__ = "inventory_policies"

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    forecast_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    service_level: Mapped[float] = mapped_column(Float)
    avg_daily_demand: Mapped[float] = mapped_column(Float)
    demand_std: Mapped[float] = mapped_column(Float)
    safety_stock: Mapped[float] = mapped_column(Float)
    reorder_point: Mapped[float] = mapped_column(Float)
    eoq: Mapped[float] = mapped_column(Float)
    on_hand: Mapped[float] = mapped_column(Float)
    on_order: Mapped[float] = mapped_column(Float)
    days_of_cover: Mapped[float | None] = mapped_column(Float, nullable=True)
    stockout_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    suggested_order_qty: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), index=True)  # stockout_risk | reorder | healthy
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    params: Mapped[dict] = mapped_column(JSON)
    results: Mapped[dict] = mapped_column(JSON)


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_type: Mapped[str] = mapped_column(String(32), index=True)
    trigger: Mapped[str] = mapped_column(String(16), default="manual")  # manual | schedule | startup
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|running|success|failed
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AssistantLog(Base):
    """Audit trail of every assistant question and the tools it called."""

    __tablename__ = "assistant_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    tool_calls: Mapped[list] = mapped_column(JSON, default=list)
    mode: Mapped[str] = mapped_column(String(16))  # llm | offline
    latency_ms: Mapped[int] = mapped_column(Integer)
