import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import case, desc, func, select

from .db import Customer, ModelRun, PipelineRun, SessionLocal, init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Retention Studio API", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["*"])


def segment(c: Customer):
    if c.cancel_flag:
        return "Cancellation signal"
    if c.listening_days_30d < c.listening_days_prior_30d - 5:
        return "Listening decline"
    if not c.auto_renew:
        return "Manual renewal"
    if c.tenure_days < 90:
        return "New member"
    return "Steady listener"


def reasons(c: Customer):
    found = []
    if c.cancel_flag:
        found.append("Cancellation flag in last transaction")
    if not c.auto_renew:
        found.append("Auto-renew is off")
    if c.listening_days_30d < c.listening_days_prior_30d - 5:
        found.append("Listening days fell versus prior month")
    if c.days_since_listen > 14:
        found.append("Long gap since last listening day")
    if c.tenure_days < 90:
        found.append("Early membership stage")
    return found or ["No strong risk signal in available features"]


def serialize(c: Customer):
    return {
        "id": c.msno, "risk": c.risk, "segment": segment(c), "reasons": reasons(c),
        "autoRenew": c.auto_renew, "cancelFlag": c.cancel_flag,
        "tenureDays": c.tenure_days, "planDays": c.plan_days,
        "amountPaid": c.amount_paid, "listeningDays": c.listening_days_30d,
        "priorListeningDays": c.listening_days_prior_30d,
        "songs": c.songs_30d, "daysSinceListen": c.days_since_listen,
        "source": c.source, "modelVersion": c.model_version,
    }


@app.get("/health")
def health():
    return {"status": "ok"}


def segment_expression():
    return case(
        (Customer.cancel_flag.is_(True), "Cancellation signal"),
        (Customer.listening_days_30d < Customer.listening_days_prior_30d - 5, "Listening decline"),
        (Customer.auto_renew.is_(False), "Manual renewal"),
        (Customer.tenure_days < 90, "New member"),
        else_="Steady listener",
    )


@app.get("/dashboard")
def dashboard():
    with SessionLocal() as db:
        source = "kkbox" if db.scalar(select(func.count()).select_from(Customer).where(Customer.source == "kkbox", Customer.risk.is_not(None))) else "demo"
        where = (Customer.source == source, Customer.risk.is_not(None))
        total, high_risk, average, weighted_paid = db.execute(select(
            func.count(Customer.msno),
            func.sum(case((Customer.risk >= 0.65, 1), else_=0)),
            func.avg(Customer.risk),
            func.sum(Customer.risk * Customer.amount_paid),
        ).where(*where)).one()
        if not total:
            return {"source": "empty", "total": 0, "highRisk": 0, "avgRisk": 0, "revenueAtRisk": 0, "segments": [], "customers": [], "runs": []}
        customers = db.scalars(select(Customer).where(*where).order_by(desc(Customer.risk), Customer.msno).limit(100)).all()
        segment_name = segment_expression().label("name")
        segments = db.execute(select(segment_name, func.count()).where(*where).group_by(segment_name).order_by(desc(func.count()))).all()
        runs = db.scalars(select(PipelineRun).order_by(desc(PipelineRun.created_at)).limit(5)).all()
        return {
            "source": source,
            "total": total, "highRisk": int(high_risk or 0),
            "avgRisk": round(float(average or 0), 3),
            "revenueAtRisk": round(float(weighted_paid or 0)),
            "segments": [{"name": name, "count": count} for name, count in segments],
            "customers": [serialize(c) for c in customers],
            "runs": [{"stage": r.stage, "status": r.status, "at": r.created_at.isoformat()} for r in runs],
        }


@app.get("/model/metrics")
def model_metrics():
    with SessionLocal() as db:
        run = db.scalar(select(ModelRun).order_by(desc(ModelRun.created_at)).limit(1))
        if run is None:
            raise HTTPException(404, "No trained model yet")
        return {"version": run.version, **json.loads(run.metrics_json)}


@app.get("/customers/{customer_id}")
def customer(customer_id: str):
    with SessionLocal() as db:
        c = db.get(Customer, customer_id)
        if not c:
            raise HTTPException(404, "Customer not found")
        return serialize(c)


@app.get("/customers")
def customers(
    q: str = Query(default="", max_length=80),
    segment: str = Query(default="", max_length=40),
    min_risk: float = Query(default=0, ge=0, le=1),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
):
    with SessionLocal() as db:
        source = "kkbox" if db.scalar(select(func.count()).select_from(Customer).where(Customer.source == "kkbox", Customer.risk.is_not(None))) else "demo"
        filters = [Customer.source == source, Customer.risk.is_not(None), Customer.risk >= min_risk]
        if q:
            filters.append(Customer.msno.ilike(f"{q}%"))
        if segment:
            filters.append(segment_expression() == segment)
        total = db.scalar(select(func.count()).select_from(Customer).where(*filters)) or 0
        rows = db.scalars(select(Customer).where(*filters).order_by(desc(Customer.risk), Customer.msno).offset(offset).limit(limit)).all()
        return {"source": source, "total": total, "offset": offset, "limit": limit, "customers": [serialize(row) for row in rows]}


class Scenario(BaseModel):
    listeningDays: int = Field(ge=0, le=30)
    autoRenew: bool


@app.post("/customers/{customer_id}/scenario")
def scenario(customer_id: str, scenario: Scenario):
    with SessionLocal() as db:
        c = db.get(Customer, customer_id)
        if not c:
            raise HTTPException(404, "Customer not found")
        if c.source == "demo":
            import math
            base = max(0.001, min(0.999, c.risk or 0.5))
            z = math.log(base / (1 - base))
            z += (c.listening_days_30d - scenario.listeningDays) * 0.055
            z += (int(c.auto_renew) - int(scenario.autoRenew)) * 0.8
            risk = 1 / (1 + math.exp(-z))
        else:
            from .model import load_model, feature_row
            model = load_model()
            if model is None:
                raise HTTPException(503, "Trained model is unavailable")
            row = feature_row(c)
            row["listening_days_30d"] = scenario.listeningDays
            row["auto_renew"] = int(scenario.autoRenew)
            risk = float(model.predict_proba(row)[0, 1])
        return {"risk": round(risk, 4), "baseline": c.risk, "note": "Model input simulation; not a causal estimate of an intervention."}
