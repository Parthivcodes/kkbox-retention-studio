# Retention Studio

An end-to-end churn intelligence system built for the [KKBox WSDM churn challenge](https://www.kaggle.com/competitions/kkbox-churn-prediction-challenge/data). The app runs immediately with **synthetic demo data**; official KKBox files can be imported locally once downloaded from Kaggle. Demo results are never presented as measured KKBox outcomes.

The frontend uses a midnight blue, cyan, and violet identity. Its scroll choreography is built with CSS, `IntersectionObserver`, and `requestAnimationFrame`: flowing SVG trails, parallax hero layers, section reveals, staggered cards, an interactive three-scene signal journey, hover lighting, a progress rail, and reduced-motion support. No paid animation library or service is required.

## Stack

| Layer | Technology | Job |
|---|---|---|
| Data store | PostgreSQL | Customers, features, predictions, pipeline runs |
| Processing | SQL + pandas | Aggregate history and prepare model inputs |
| ML | scikit-learn + HistGradientBoosting | Baseline and candidate churn models |
| Orchestration | Dagster | Import, feature, train, and score assets |
| API | FastAPI | Dashboard and customer endpoints |
| UI | Next.js + React + TypeScript | Retention Studio dashboard |
| Packaging | Docker Compose | Local PostgreSQL, API, UI |

## Quick start

With Docker installed, run `docker compose up --build` and open http://localhost:3000. The API is at http://localhost:8000/docs and the Dagster asset UI is at http://localhost:3001. On first start, PostgreSQL is seeded with synthetic demo customers and predictions so the interface is usable immediately.

For a frontend preview without Docker or a database, run `npm install` and `npm run dev` in `frontend`. It falls back to clearly labeled local synthetic data when the API is unavailable. For the full local stack, set `DATABASE_URL`, install `backend/requirements.txt`, run `python -m app.seed_demo` from `backend`, then `uvicorn app.main:app --reload`.

## Import KKBox data

1. Download the competition files from Kaggle after accepting its terms.
2. Put `train_v2.csv`, `members_v3.csv`, `transactions.csv`, and `user_logs.csv` in `data/kkbox/`. The `_v2` transaction and log files are optional.
3. Set `DATA_DIR` to that folder and run `python -m app.pipeline import`, `python -m app.pipeline features`, `python -m app.pipeline train`, then `python -m app.pipeline score` from `backend`.
4. Alternatively run the Dagster assets in `backend/app/orchestration.py`.

Raw files are excluded from Git. The import reads large event files in chunks and uses PostgreSQL `COPY` for the filtered records. This first version uses the February 2017 labeled cohort, includes only members whose last pre-cutoff subscription was still active on **2017-02-01**, and uses **only records dated before that cutoff** for features. It ignores the later `_v2` event files to avoid leakage. The split is deterministic by customer into training, calibration, and holdout partitions; it is **not** a future-month evaluation. The dashboard scores this historical cohort for demonstration, including members used for training. A real deployment requires a fresh, unlabeled scoring cohort and later outcome monitoring.

Training compares a logistic baseline with gradient boosting, calibrates probabilities on a separate partition, records PR-AUC, ROC-AUC, Brier score and precision at the highest-risk 5% and 10%, and saves the selected model. If MLflow is installed, it records metrics and the model artifact locally. `GET /model/metrics` returns the latest holdout report. Batch scoring writes predictions back to PostgreSQL in chunks.

The API provides `GET /dashboard` for summary cards and the highest-risk 100 members, `GET /customers` for paginated prefix search and risk or segment filters, `GET /customers/{id}` for a member, and `POST /customers/{id}/scenario` for a model-input what-if calculation. The frontend currently searches within the dashboard's top 100; the paginated endpoint is available for the next UI iteration.

To run the isolated integration test against a disposable PostgreSQL database, set `TEST_DATABASE_URL` to a database URL whose name ends in `_test`, then run `python tests/integration.py` from `backend`. The test creates generated KKBox-shaped files and replaces data in that test database.

## Scientific limits

- The source's `is_churn` label means a member failed to renew within 30 days after expiry. It is not a 30-day-from-today cancellation label.
- The member-level reasons are descriptive signals, not model feature attributions or causes. The what-if view changes model inputs; it does not predict the causal effect of an intervention.
- Risk-weighted paid amount is a ranking aid, not expected saved revenue. Campaign effectiveness needs randomized treatment data.
- The demo mode is synthetic. The source badge in the UI identifies the current dataset.

