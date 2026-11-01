from dagster import Definitions, asset

from .pipeline import build_features, import_data, score, train


@asset
def kkbox_import():
    return import_data()


@asset(deps=[kkbox_import])
def customer_features():
    return build_features()


@asset(deps=[customer_features])
def churn_model():
    return train()


@asset(deps=[churn_model])
def risk_scores():
    return score()


defs = Definitions(assets=[kkbox_import, customer_features, churn_model, risk_scores])
