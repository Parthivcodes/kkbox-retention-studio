"""KKBox batch pipeline. Run `python -m app.pipeline <import|features|train|score>`."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from .db import Customer, ModelRun, SessionLocal, engine, init_db, record_run
from .model import FEATURES, MODEL_PATH, load_model, train_model

DATA_DIR = Path(os.getenv("DATA_DIR", "../data/kkbox"))
CUTOFF = 20170201
TRANSACTION_START = 20161103
LOG_START = 20161203
CURRENT_LISTENING_START = 20170102

TRANSACTION_COLUMNS = ["msno", "transaction_date", "membership_expire_date", "payment_plan_days", "actual_amount_paid", "is_auto_renew", "is_cancel"]
LOG_COLUMNS = ["msno", "date", "num_25", "num_50", "num_75", "num_985", "num_100", "total_secs"]


def _path(filename: str) -> Path:
    path = DATA_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"Missing {path}. Download the official KKBox competition files from Kaggle first.")
    return path


def _copy_rows(table: str, columns: list[str], frame: pd.DataFrame):
    """Use PostgreSQL COPY for event volumes; fall back to pandas for SQLite tests."""
    if frame.empty:
        return
    if engine.dialect.name != "postgresql":
        frame.to_sql(table, engine, if_exists="append", index=False, chunksize=2000)
        return
    import psycopg

    url = engine.url.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(url) as connection:
        with connection.cursor() as cursor:
            with cursor.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as copy:
                for row in frame[columns].itertuples(index=False, name=None):
                    copy.write_row(tuple(None if pd.isna(value) else value.item() if hasattr(value, "item") else value for value in row))


def _event_chunks(filename: str, columns: list[str], ids: set[str], date_column: str, start: int):
    for chunk in pd.read_csv(_path(filename), usecols=columns, chunksize=100_000, low_memory=False):
        chunk[date_column] = pd.to_numeric(chunk[date_column], errors="coerce")
        filtered = chunk[chunk.msno.isin(ids) & chunk[date_column].between(start, CUTOFF - 1)].copy()
        if not filtered.empty:
            for column in columns:
                if column != "msno":
                    filtered[column] = pd.to_numeric(filtered[column], errors="coerce")
            yield filtered


def import_data():
    init_db()
    labels = pd.read_csv(_path("train_v2.csv"), usecols=["msno", "is_churn"])
    members = pd.read_csv(_path("members_v3.csv"), usecols=["msno", "city", "registered_via", "registration_init_time"])
    if labels.msno.duplicated().any():
        raise ValueError("train_v2.csv contains duplicate member IDs")
    base = labels.merge(members.drop_duplicates("msno"), on="msno", how="left").rename(columns={"is_churn": "label"})
    for column in ("label", "city", "registered_via", "registration_init_time"):
        base[column] = pd.to_numeric(base[column], errors="coerce").astype("Int64")
    if base.label.isna().any() or not set(base.label.unique()).issubset({0, 1}):
        raise ValueError("Churn labels must be 0 or 1")
    ids = set(base.msno)

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS raw_transactions"))
        conn.execute(text("DROP TABLE IF EXISTS raw_user_logs"))
        conn.execute(text("CREATE TABLE raw_transactions (msno TEXT, transaction_date BIGINT, membership_expire_date BIGINT, payment_plan_days BIGINT, actual_amount_paid DOUBLE PRECISION, is_auto_renew BIGINT, is_cancel BIGINT)"))
        conn.execute(text("CREATE TABLE raw_user_logs (msno TEXT, date BIGINT, num_25 BIGINT, num_50 BIGINT, num_75 BIGINT, num_985 BIGINT, num_100 BIGINT, total_secs DOUBLE PRECISION)"))

    transaction_count = 0
    for chunk in _event_chunks("transactions.csv", TRANSACTION_COLUMNS, ids, "transaction_date", TRANSACTION_START):
        _copy_rows("raw_transactions", TRANSACTION_COLUMNS, chunk)
        transaction_count += len(chunk)
    log_count = 0
    for chunk in _event_chunks("user_logs.csv", LOG_COLUMNS, ids, "date", LOG_START):
        _copy_rows("raw_user_logs", LOG_COLUMNS, chunk)
        log_count += len(chunk)
    if not transaction_count:
        raise ValueError("No pre-cutoff transactions matched the training cohort")
    base.to_sql("raw_cohort", engine, if_exists="replace", index=False, chunksize=2000)
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX idx_raw_tx_msno ON raw_transactions (msno, transaction_date DESC)"))
        conn.execute(text("CREATE INDEX idx_raw_logs_msno ON raw_user_logs (msno)"))
        conn.execute(text("CREATE INDEX idx_raw_cohort_msno ON raw_cohort (msno)"))
    result = {"labels": len(base), "transactions": transaction_count, "log_days": log_count, "cutoff": "2017-02-01"}
    record_run("import", "success", json.dumps(result))
    return result


FEATURE_SQL = f"""
WITH last_tx AS (
  SELECT DISTINCT ON (msno) msno, membership_expire_date, payment_plan_days,
    actual_amount_paid, is_auto_renew, is_cancel
  FROM raw_transactions ORDER BY msno, transaction_date DESC, membership_expire_date DESC
), tx AS (
  SELECT msno, COUNT(*) AS transactions_90d FROM raw_transactions GROUP BY msno
), logs AS (
  SELECT msno,
    COUNT(DISTINCT date) FILTER (WHERE date >= {CURRENT_LISTENING_START}) AS listening_days_30d,
    COUNT(DISTINCT date) FILTER (WHERE date < {CURRENT_LISTENING_START}) AS listening_days_prior_30d,
    COALESCE(SUM(COALESCE(num_25,0) + COALESCE(num_50,0) + COALESCE(num_75,0) + COALESCE(num_985,0) + COALESCE(num_100,0)) FILTER (WHERE date >= {CURRENT_LISTENING_START}),0) AS songs_30d,
    COALESCE(SUM(COALESCE(total_secs,0)) FILTER (WHERE date >= {CURRENT_LISTENING_START}),0) AS total_seconds_30d,
    MAX(date) AS last_listen_date
  FROM raw_user_logs GROUP BY msno
)
SELECT c.msno,c.label,c.city,c.registered_via,
  CASE WHEN c.registration_init_time IS NULL THEN 0 ELSE GREATEST(0, DATE '2017-02-01' - TO_DATE(c.registration_init_time::text,'YYYYMMDD')) END AS tenure_days,
  COALESCE(t.payment_plan_days,0) AS plan_days,
  (COALESCE(t.is_auto_renew,0) <> 0) AS auto_renew,
  (COALESCE(t.is_cancel,0) <> 0) AS cancel_flag,
  COALESCE(t.actual_amount_paid,0) AS amount_paid,
  COALESCE(x.transactions_90d,0) AS transactions_90d,
  COALESCE(l.listening_days_30d,0) AS listening_days_30d,
  COALESCE(l.listening_days_prior_30d,0) AS listening_days_prior_30d,
  COALESCE(l.songs_30d,0) AS songs_30d,
  COALESCE(l.total_seconds_30d,0) AS total_seconds_30d,
  CASE WHEN l.last_listen_date IS NULL THEN 60 ELSE GREATEST(0, DATE '2017-02-01' - TO_DATE(l.last_listen_date::text,'YYYYMMDD')) END AS days_since_listen,
  'kkbox' AS source
FROM raw_cohort c JOIN last_tx t ON c.msno=t.msno
LEFT JOIN tx x ON c.msno=x.msno LEFT JOIN logs l ON c.msno=l.msno
WHERE t.membership_expire_date >= {CUTOFF}
"""


def build_features():
    init_db()
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS customer_stage"))
    total = 0
    with engine.connect() as conn:
        for chunk in pd.read_sql_query(text(FEATURE_SQL), conn, chunksize=10_000):
            chunk.to_sql("customer_stage", engine, if_exists="append", index=False, chunksize=2000)
            total += len(chunk)
    if total == 0:
        raise ValueError("No members were eligible at the 2017-02-01 cutoff")
    columns = [column.name for column in Customer.__table__.columns if column.name not in {"risk", "model_version", "scored_at"}]
    names = ", ".join(columns)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM customers"))
        conn.execute(text(f"INSERT INTO customers ({names}) SELECT {names} FROM customer_stage"))
        conn.execute(text("DROP TABLE customer_stage"))
    record_run("features", "success", f"{total} eligible customer feature rows")
    return total


def train():
    with engine.connect() as conn:
        frame = pd.read_sql_query(text("SELECT * FROM customers WHERE source='kkbox' AND label IS NOT NULL"), conn)
    result = train_model(frame)
    version = datetime.now(timezone.utc).strftime("kkbox-%Y%m%d%H%M%S%f")
    with SessionLocal.begin() as db:
        db.add(ModelRun(version=version, winner=result["winner"], metrics_json=json.dumps(result), train_rows=result["train_rows"], calibration_rows=result["calibration_rows"], holdout_rows=result["holdout_rows"]))
    try:
        import mlflow
        mlflow.set_experiment("kkbox-churn")
        with mlflow.start_run(run_name=version):
            mlflow.log_params({"cutoff": "2017-02-01", "winner": result["winner"], "validation": result["validation"]})
            mlflow.log_metrics({f"{name}_{metric}": value for name, values in result["metrics"].items() for metric, value in values.items()})
            mlflow.log_artifact(str(MODEL_PATH))
    except ImportError:
        pass
    record_run("train", "success", json.dumps({"version": version, **result}))
    return {"version": version, **result}


def score():
    model = load_model()
    if model is None:
        raise RuntimeError("No trained model. Run train first.")
    with SessionLocal() as db:
        latest = db.query(ModelRun).order_by(ModelRun.created_at.desc()).first()
        if latest is None:
            raise RuntimeError("Model metadata is missing. Run train first.")
        version = latest.version
    now = datetime.now(timezone.utc)
    total = 0
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS score_stage"))
        conn.execute(text("CREATE TABLE score_stage (msno TEXT PRIMARY KEY, risk DOUBLE PRECISION)"))
    with engine.connect() as conn:
        for chunk in pd.read_sql_query(text("SELECT msno, " + ", ".join(FEATURES) + " FROM customers WHERE source='kkbox' ORDER BY msno"), conn, chunksize=10_000):
            risk = model.predict_proba(chunk[FEATURES])[:, 1]
            stage = pd.DataFrame({"msno": chunk.msno, "risk": risk})
            _copy_rows("score_stage", ["msno", "risk"], stage)
            total += len(stage)
    with engine.begin() as conn:
        conn.execute(text("UPDATE customers AS c SET risk=s.risk, model_version=:version, scored_at=:at FROM score_stage AS s WHERE c.msno=s.msno"), {"version": version, "at": now})
        conn.execute(text("DROP TABLE score_stage"))
    record_run("score", "success", f"{total} members scored with {version}")
    return {"scored": total, "version": version}


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    actions = {"import": import_data, "features": build_features, "train": train, "score": score}
    if command not in actions:
        raise SystemExit("Usage: python -m app.pipeline <import|features|train|score>")
    print(actions[command]())
