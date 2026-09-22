# eminidatabase Control Plane backend (FastAPI). Same image runs three
# processes in docker-compose.prod.yml — the HTTP API (uvicorn), the job
# worker (app.worker), and the scheduler (app.scheduler) — they share code
# and dependencies, only the command differs.

FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --uid 1000 eminidatabase \
    && mkdir -p /srv/app/certs \
    && chown -R eminidatabase:eminidatabase /srv/app
USER eminidatabase

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/srv/app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
