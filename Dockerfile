FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       openscad \
       ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/cad ./cad

# FastAPI mounts this folder at /app/ via backend/app/static_ui.py.
COPY frontend-lite /frontend-lite

# FastAPI mounts this landing page at / via backend/app/static_ui.py (after all API routes).
COPY site /site

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
