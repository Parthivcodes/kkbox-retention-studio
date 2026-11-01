import math
import random

from sqlalchemy import select

from .db import Customer, SessionLocal, init_db, record_run


def seed():
    init_db()
    with SessionLocal() as db:
        if db.scalar(select(Customer.msno).limit(1)):
            return
        rng = random.Random(42)
        rows = []
        for i in range(1, 241):
            listen = rng.randint(0, 28)
            prior = min(30, max(0, listen + rng.randint(-9, 12)))
            auto = rng.random() > 0.38
            cancel = rng.random() < 0.11
            tenure = rng.randint(15, 1300)
            amount = rng.choice([99, 129, 149, 179, 199, 299])
            days_since = rng.randint(0, 35) if listen else rng.randint(30, 60)
            z = -2.4 + (30 - listen) * 0.055 + max(0, prior - listen) * 0.055 + (not auto) * 0.8 + cancel * 1.3 + days_since * 0.025 - min(tenure, 700) * 0.0008
            risk = 1 / (1 + math.exp(-z))
            rows.append(Customer(
                msno=f"DEMO-{i:04d}", source="demo", city=rng.randint(1, 15),
                registered_via=rng.choice([3, 4, 7, 9]), tenure_days=tenure,
                plan_days=rng.choice([30, 90, 180]), auto_renew=auto,
                cancel_flag=cancel, amount_paid=amount, transactions_90d=rng.randint(1, 4),
                listening_days_30d=listen, listening_days_prior_30d=prior,
                songs_30d=listen * rng.randint(4, 27), total_seconds_30d=listen * rng.randint(1200, 6600),
                days_since_listen=days_since, label=int(rng.random() < risk),
                risk=round(risk, 4), model_version="demo-rules-v1",
            ))
        db.add_all(rows)
        db.commit()
    record_run("seed", "success", "240 synthetic demo customers")


if __name__ == "__main__":
    seed()
