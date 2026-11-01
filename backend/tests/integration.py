"""Run only against an isolated disposable PostgreSQL database.

Set TEST_DATABASE_URL, then run `python tests/integration.py` from backend.
"""
import csv
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

url = os.environ.get("TEST_DATABASE_URL", "")
if not url or not url.rsplit("/", 1)[-1].endswith("_test"):
    raise SystemExit("Set TEST_DATABASE_URL to an isolated database whose name ends in _test")
os.environ["DATABASE_URL"] = url
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import pipeline  # noqa: E402
from app.db import Customer, SessionLocal  # noqa: E402
from app.main import Scenario, customers, dashboard, model_metrics, scenario  # noqa: E402


def write_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


with tempfile.TemporaryDirectory() as folder:
    data_dir = Path(folder)
    pipeline.DATA_DIR = data_dir
    labels, members, transactions, logs = [], [], [], []
    for i in range(320):
        member = f"M{i:04d}"
        auto = int(i % 4 != 0)
        low_listening = i % 5 == 0
        churn = int((not auto and i % 3 != 0) or low_listening)
        labels.append({"msno": member, "is_churn": churn})
        members.append({"msno": member, "city": i % 10 + 1, "registered_via": 7, "registration_init_time": 20150301})
        transactions.append({"msno": member, "transaction_date": 20170115, "membership_expire_date": 20170228,
                             "payment_plan_days": 30, "actual_amount_paid": 149, "is_auto_renew": auto, "is_cancel": 0})
        # This is after the cutoff and must have no effect on features.
        transactions.append({"msno": member, "transaction_date": 20170205, "membership_expire_date": 20170328,
                             "payment_plan_days": 90, "actual_amount_paid": 9999, "is_auto_renew": 0, "is_cancel": 1})
        count = 2 if low_listening else 13
        for offset in range(count):
            day = date(2017, 1, 3) + timedelta(days=offset)
            logs.append({"msno": member, "date": day.strftime("%Y%m%d"), "num_25": 2, "num_50": 2,
                         "num_75": 1, "num_985": 1, "num_100": 6, "total_secs": 1800})
        logs.append({"msno": member, "date": 20170203, "num_25": 100, "num_50": 100,
                     "num_75": 100, "num_985": 100, "num_100": 100, "total_secs": 999999})
    # Present in the label file, but not an active member at the cutoff.
    labels.append({"msno": "INELIGIBLE", "is_churn": 1})
    members.append({"msno": "INELIGIBLE", "city": 1, "registered_via": 7, "registration_init_time": 20160101})
    transactions.append({"msno": "INELIGIBLE", "transaction_date": 20170105, "membership_expire_date": 20170128,
                         "payment_plan_days": 30, "actual_amount_paid": 149, "is_auto_renew": 0, "is_cancel": 0})

    write_csv(data_dir / "train_v2.csv", ["msno", "is_churn"], labels)
    write_csv(data_dir / "members_v3.csv", ["msno", "city", "registered_via", "registration_init_time"], members)
    write_csv(data_dir / "transactions.csv", pipeline.TRANSACTION_COLUMNS, transactions)
    write_csv(data_dir / "user_logs.csv", pipeline.LOG_COLUMNS, logs)

    imported = pipeline.import_data()
    assert imported["labels"] == 321
    assert imported["transactions"] == 321
    assert pipeline.build_features() == 320
    with SessionLocal() as db:
        first = db.get(Customer, "M0000")
        assert first is not None
        assert first.amount_paid == 149 and first.plan_days == 30
        assert first.cancel_flag is False and first.transactions_90d == 1
        assert first.listening_days_30d == 2 and first.songs_30d == 24
        assert db.get(Customer, "INELIGIBLE") is None

    trained = pipeline.train()
    assert trained["train_rows"] > 100 and trained["holdout_rows"] > 20
    assert 0 <= trained["metrics"][trained["winner"]]["pr_auc"] <= 1
    scored = pipeline.score()
    assert scored["scored"] == 320
    summary = dashboard()
    assert summary["source"] == "kkbox" and summary["total"] == 320
    assert len(summary["customers"]) == 100
    filtered = customers(q="", segment="Manual renewal", min_risk=0, limit=10, offset=0)
    assert filtered["total"] > 0 and all(row["segment"] == "Manual renewal" for row in filtered["customers"])
    assert model_metrics()["version"] == trained["version"]
    sample = summary["customers"][0]
    result = scenario(sample["id"], Scenario(listeningDays=10, autoRenew=True))
    assert 0 <= result["risk"] <= 1
    print("PostgreSQL import, cutoff, eligibility, training, scoring, dashboard, and scenario: OK")
