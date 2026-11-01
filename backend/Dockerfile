FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN mkdir -p /app/models /app/dagster-home /app/mlruns
CMD ["sh", "-c", "python -m app.seed_demo && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
