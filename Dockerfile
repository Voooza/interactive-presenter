# ============================================================================
# Multi-stage Dockerfile for Interactive Presenter
#
# Stage 1 — Build the React frontend with Vite
# Stage 2 — Production image: Python + uvicorn serving FastAPI + static assets
# ============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Frontend build
# ---------------------------------------------------------------------------
FROM node:22-alpine AS frontend-build

WORKDIR /build

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: Production image
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS production

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr
# so container logs appear in real time.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python dependencies first (layer caching).
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# Copy application code.
COPY backend/ ./backend/
COPY presentations/ ./presentations/

# Copy pre-built frontend assets from stage 1.
COPY --from=frontend-build /build/dist ./frontend/dist

# The backend auto-detects frontend/dist and mounts it as static files.
ENV STATIC_DIR=/app/frontend/dist \
    PRESENTATIONS_DIR=/app/presentations

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"]

# Run with uvicorn — single worker is fine for in-memory state.
# For multi-core VPS, --workers can be increased but would require shared
# state (e.g. Redis) for the ConnectionManager.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
