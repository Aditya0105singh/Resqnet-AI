# syntax=docker/dockerfile:1
# Single container: FastAPI serves the API, the WebSocket and the built frontend on port 8000.

FROM node:20-slim AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# /research renders the repository's docs at build time
COPY docs/ /app/docs/
RUN npx tsc -b && npx vite build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RESQNET_DB=/var/lib/resqnet/resqnet.db
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY data/ data/
COPY docs/ docs/
COPY --from=web /app/frontend/dist frontend/dist
RUN useradd --system --uid 10001 resqnet && mkdir -p /var/lib/resqnet && chown resqnet /var/lib/resqnet
USER resqnet
WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status == 200 else 1)"
CMD ["python", "-m", "uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
