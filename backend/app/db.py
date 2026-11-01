import os
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://retention:retention@localhost:5432/retention")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(engine)


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (Index("idx_customers_source_risk", "source", "risk"),)
    msno: Mapped[str] = mapped_column(String(80), primary_key=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="demo")
    city: Mapped[int | None] = mapped_column(Integer)
    registered_via: Mapped[int | None] = mapped_column(Integer)
    tenure_days: Mapped[int] = mapped_column(Integer, default=0)
    plan_days: Mapped[int] = mapped_column(Integer, default=0)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False)
    cancel_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    amount_paid: Mapped[float] = mapped_column(Float, default=0)
    transactions_90d: Mapped[int] = mapped_column(Integer, default=0)
    listening_days_30d: Mapped[int] = mapped_column(Integer, default=0)
    listening_days_prior_30d: Mapped[int] = mapped_column(Integer, default=0)
    songs_30d: Mapped[int] = mapped_column(Integer, default=0)
    total_seconds_30d: Mapped[float] = mapped_column(Float, default=0)
    days_since_listen: Mapped[int] = mapped_column(Integer, default=60)
    label: Mapped[int | None] = mapped_column(Integer)
    risk: Mapped[float | None] = mapped_column(Float)
    model_version: Mapped[str | None] = mapped_column(String(80))
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stage: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))
    details: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ModelRun(Base):
    __tablename__ = "model_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(80), unique=True)
    winner: Mapped[str] = mapped_column(String(80))
    metrics_json: Mapped[str] = mapped_column(Text)
    train_rows: Mapped[int] = mapped_column(Integer)
    calibration_rows: Mapped[int] = mapped_column(Integer)
    holdout_rows: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


def init_db():
    Base.metadata.create_all(engine)


def record_run(stage: str, status: str, details: str = ""):
    with SessionLocal.begin() as db:
        db.add(PipelineRun(stage=stage, status=status, details=details[:500]))


