# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Hangar — multi-stage image (Constitution V: a single, self-contained stack).
#
# Stage 1 (node):   build the Vite + React SPA  ->  /frontend/dist
# Stage 2 (build):  build the backend wheel with uv, so hatch-vcs can derive the
#                   version from git tags. This stage is discarded.
# Stage 3 (python): install that wheel, copy the built SPA into a static dir, and
#                   serve everything from one Uvicorn process.
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
FROM node:26-slim AS frontend
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

# ---- Stage 2: build the backend wheel --------------------------------------
# The version is derived from git tags by hatch-vcs (backend/pyproject.toml,
# [tool.hatch.version] source = "vcs"), so this stage needs the real .git. It is
# a build stage only — the history never reaches the runtime image below.
FROM python:3.14-slim AS backend-build

# uv is the package manager and the build front-end (portfolio standard).
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /bin/

# setuptools_scm shells out to git to resolve the version.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY .git ./.git
COPY backend ./backend
# The checkout is owned by a different uid than the build user; without this git
# refuses to read it and setuptools_scm silently falls back to a wrong version.
RUN git config --global --add safe.directory /build \
    && cd backend \
    && uv build --wheel --out-dir /dist \
    && ls -1 /dist

# ---- Stage 3: backend runtime ---------------------------------------------
FROM python:3.14-slim AS runtime

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

# Install the wheel built in the stage above. Include the optional `postgres`
# extra so the same image can target Postgres via HANGAR_DATABASE_URL without a
# rebuild. The Alembic migrations live inside the package
# (backend/src/hangar/migrations), so they install with it and the app applies
# them on startup (hangar.persistence.db.apply_migrations).
COPY --from=backend-build /dist /tmp/dist
RUN pip install "$(ls /tmp/dist/*.whl)[postgres]" \
    && rm -rf /tmp/dist

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
