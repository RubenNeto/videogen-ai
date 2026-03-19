FROM python:3.12-slim

# ── System packages ───────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-liberation \
    fonts-freefont-ttf \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python deps ───────────────────────────────────────────
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ── App code ──────────────────────────────────────────────
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# ── Dirs para output ─────────────────────────────────────
RUN mkdir -p /app/output/videos /app/output/temp

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV OUTPUT_DIR=/app/output/videos
ENV TEMP_DIR=/app/output/temp
ENV DATABASE_URL=sqlite+aiosqlite:////app/output/videogen.db

# Railway injeta PORT automaticamente
EXPOSE $PORT

CMD uvicorn backend.main:app \
    --host 0.0.0.0 \
    --port ${PORT:-8080} \
    --workers 1 \
    --log-level info \
    --forwarded-allow-ips="*"
