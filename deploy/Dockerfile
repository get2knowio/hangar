# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Hangar — multi-stage image (Constitution V: a single, self-contained stack).
#
# Stage 1 (node):  build the Vite + React SPA  ->  /frontend/dist
# Stage 2 (python): install the FastAPI backend, copy the built SPA into a
#                   static dir, and serve everything from one Uvicorn process.
#
# The backend exposes the API under /api/v1/* and a root /health for the
# container healthcheck, and serves the built SPA as static assets from the same
# Uvicorn process: create_app() -> _mount_spa() serves /app/static at / (with an
# index.html fallback for client-side routes), driven by HANGAR_STATIC_DIR (set
# below). The SPA is built here and copied to /app/static so that mount is live
# with no extra wiring. If the frontend has not produced a dist/ yet, stage 1
# falls back to an empty dir so the build never fails and the mount no-ops.
#
# Build context is the REPOSITORY ROOT (see docker-compose.yml `build.context`).
# ---------------------------------------------------------------------------

# ---- Stage 1: build the SPA ------------------------------------------------
FROM node:20-slim AS frontend
WORKDIR /frontend

# Install deps first for layer caching. `npm ci` requires a lockfile; if the
# frontend is still in flux (no package.json/lock yet) we tolerate that and
# emit an empty dist so the python stage always has something to copy.
COPY frontend/package*.json ./
RUN if [ -f package-lock.json ]; then npm ci; \
    elif [ -f package.json ]; then npm install; \
    else echo "no frontend package.json yet — skipping install"; fi

COPY frontend/ ./
RUN if [ -f package.json ]; then npm run build; fi; \
    mkdir -p /frontend/dist

# ---- Stage 2: backend runtime ---------------------------------------------
FROM python:3.12-slim AS runtime

# Predictable, unbuffered Python; no .pyc clutter; pip without a cache layer.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# curl is used by the compose healthcheck (hits /health).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install the backend. Copy the package metadata + source, then `pip install`.
# Include the optional `postgres` extra so the same image can target Postgres
# via HANGAR_DATABASE_URL without a rebuild. The Alembic migrations live inside
# the package (backend/src/hangar/migrations), so they install with it and the
# app applies them on startup (hangar.persistence.db.apply_migrations).
COPY backend/pyproject.toml ./backend/pyproject.toml
COPY backend/src ./backend/src
RUN pip install "./backend[postgres]"

# Copy the built SPA into a static dir the app can serve. Always present
# (empty if the SPA wasn't built) so this layer never fails the build.
COPY --from=frontend /frontend/dist ./static

# Run as a non-root user (defense in depth). The named volume mounted at
# /data (see compose) holds the SQLite db + state and is chowned to this user.
RUN useradd --create-home --uid 10001 hangar \
    && mkdir -p /data \
    && chown -R hangar:hangar /app /data
USER hangar

# Default DB location lives on the mounted volume (SQLite). To use Postgres, set
# the discrete HANGAR_POSTGRES_* vars in the env_file — HANGAR_POSTGRES_HOST takes
# precedence over this default. A full HANGAR_DATABASE_URL also overrides it.
ENV HANGAR_DATABASE_URL="sqlite+aiosqlite:////data/hangar.db" \
    HANGAR_STATIC_DIR="/app/static"

# The container always binds 0.0.0.0 INTERNALLY; the host-level internal bind
# (publishing the port only on 127.0.0.1) and HANGAR_ALLOW_PUBLIC_BIND are
# handled at the compose/host layer, not here. HANGAR_HOST is left to the app
# default for its own startup safety checks.
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "hangar.main:app", "--host", "0.0.0.0", "--port", "8000"]
