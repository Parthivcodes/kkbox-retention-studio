"""Reproducible churn training with a held-out customer split and calibration."""
import hashlib
import os
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.frozen import FrozenEstimator
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .db import Customer

MODEL_PATH = Path(os.getenv("MODEL_PATH", "models/churn.joblib"))
NUMERIC = ["tenure_days", "plan_days", "amount_paid", "transactions_90d", "listening_days_30d", "listening_days_prior_30d", "songs_30d", "total_seconds_30d", "days_since_listen"]
CATEGORICAL = ["city", "registered_via", "auto_renew", "cancel_flag"]
FEATURES = NUMERIC + CATEGORICAL


def feature_row(c: Customer) -> pd.DataFrame:
    return pd.DataFrame([{key: int(value) if isinstance(value := getattr(c, key), bool) else value for key in FEATURES}])


@lru_cache(maxsize=2)
def _cached_model(path: str, modified_ns: int):
    return joblib.load(path)


def load_model():
    return _cached_model(str(MODEL_PATH), MODEL_PATH.stat().st_mtime_ns) if MODEL_PATH.exists() else None


def _bucket(member_id: str) -> int:
    return int.from_bytes(hashlib.sha256(member_id.encode()).digest()[:4], "big") % 10


def _top_k_precision(y_true, probabilities, share: float) -> float:
    n = max(1, round(len(probabilities) * share))
    top = pd.Series(probabilities).nlargest(n).index
    return float(pd.Series(y_true).iloc[top].mean())


def train_model(frame: pd.DataFrame):
    if len(frame) < 100 or frame["label"].nunique() < 2:
        raise ValueError("Training requires at least 100 records and both classes")
    frame = frame.sort_values("msno").reset_index(drop=True)
    buckets = frame.msno.map(_bucket)
    training, calibration, holdout = frame[buckets >= 4], frame[buckets.between(2, 3)], frame[buckets <= 1]
    max_training = int(os.getenv("MAX_TRAIN_ROWS", "150000"))
    max_calibration = int(os.getenv("MAX_CALIBRATION_ROWS", "40000"))
    max_holdout = int(os.getenv("MAX_HOLDOUT_ROWS", "40000"))
    if len(training) > max_training:
        training = training.sample(max_training, random_state=42)
    if len(calibration) > max_calibration:
        calibration = calibration.sample(max_calibration, random_state=43)
    if len(holdout) > max_holdout:
        holdout = holdout.sample(max_holdout, random_state=44)
    if any(part.label.nunique() < 2 for part in (training, calibration, holdout)):
        raise ValueError("Training, calibration, and holdout partitions each need both classes")

    results = {}
    for name, estimator in {
        "logistic": LogisticRegression(max_iter=500, class_weight="balanced"),
        "gradient_boosting": HistGradientBoostingClassifier(max_iter=150, learning_rate=0.06, random_state=42),
    }.items():
        preprocessing = ColumnTransformer([
            ("numeric", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), NUMERIC),
            ("categorical", Pipeline([("impute", SimpleImputer(strategy="most_frequent")), ("encode", OneHotEncoder(handle_unknown="ignore", sparse_output=False))]), CATEGORICAL),
        ])
        base = Pipeline([("preprocess", preprocessing), ("model", estimator)])
        base.fit(training[FEATURES], training.label)
        calibrated = CalibratedClassifierCV(FrozenEstimator(base), method="sigmoid")
        calibrated.fit(calibration[FEATURES], calibration.label)
        probabilities = calibrated.predict_proba(holdout[FEATURES])[:, 1]
        results[name] = {
            "model": calibrated,
            "pr_auc": float(average_precision_score(holdout.label, probabilities)),
            "roc_auc": float(roc_auc_score(holdout.label, probabilities)),
            "brier": float(brier_score_loss(holdout.label, probabilities)),
            "precision_at_5pct": _top_k_precision(holdout.label.to_numpy(), probabilities, 0.05),
            "precision_at_10pct": _top_k_precision(holdout.label.to_numpy(), probabilities, 0.10),
        }
    winner = max(results, key=lambda name: results[name]["pr_auc"])
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = MODEL_PATH.with_suffix(".tmp")
    joblib.dump(results[winner]["model"], temporary)
    temporary.replace(MODEL_PATH)
    return {
        "winner": winner,
        "train_rows": len(training), "calibration_rows": len(calibration), "holdout_rows": len(holdout),
        "holdout_prevalence": float(holdout.label.mean()),
        "metrics": {name: {key: value for key, value in result.items() if key != "model"} for name, result in results.items()},
        "validation": "stable customer split; not future-month validation",
    }
