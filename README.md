# Hangar

**Hangar** is a self-hosted, single-operator *fleet control plane*. It aggregates the
repositories across one or more provider connections (GitHub today, Gitea designed-for)
into one dashboard, scores each repo against a declarative best-practice **policy**, and
lets you remediate hygiene drift in place — every content change delivered as a **pull
request, never a push**. It is provider-agnostic at its core, fail-closed behind a
reverse-proxy SSO layer, and built to run as a single Docker Compose stack on a modest
homelab host.

> Design & scope live under [`specs/001-fleet-control-plane/`](specs/001-fleet-control-plane/):
> [spec](specs/001-fleet-control-plane/spec.md) ·
> [plan](specs/001-fleet-control-plane/plan.md) ·
> [research](specs/001-fleet-control-plane/research.md) ·
> [data model](specs/001-fleet-control-plane/data-model.md) ·
> [OpenAPI contract](specs/001-fleet-control-plane/contracts/openapi.yaml) ·
> [UI contract](specs/001-fleet-control-plane/contracts/ui-spec.md) ·
> [quickstart](specs/001-fleet-control-plane/quickstart.md). Governance:
> [constitution](.specify/memory/constitution.md).

---

## Architecture

| Layer        | What it is | Where |
|--------------|-----------|-------|
| **Backend**  | Python 3.12 + FastAPI. Provider-neutral domain core, a `RepoProvider` interface (GitHub adapter via `githubkit`, GitHub App + webhooks), an APScheduler per-connection poller, SQLAlchemy + Alembic persistence, and Fernet credential encryption. Serves `/api/v1/*` and `/health`. | `backend/` (package `hangar`, entrypoint `hangar.main:app`) |
| **Frontend** | React + TypeScript + Vite SPA on shadcn/ui + Tailwind + TanStack Query. Types are generated from the OpenAPI contract (`gen:api`), so there are no hand-drifted types. Builds to `frontend/dist`. | `frontend/` |
| **Deploy**   | A single Docker Compose stack: the `hangar` app behind Traefik (`ForwardAuth` SSO, TLS), SQLite by default, optional Postgres profile, `homepage.*` + `hola-*` labels, internal bind. | `deploy/` |

The backend serves the API; the built SPA is served as static assets by the same process.
Access control is **not** Hangar's job — it sits behind a forward-auth reverse proxy
(Traefik + Authentik reference) and trusts an identity header only from the proxy.

---

## Prerequisites

Either:

- **Docker** + **Docker Compose v2** (the quickest path), or
- **Local toolchains**: Python **3.12** and Node **20**.

For production-like runs you also want:

- A **GitHub App** (App id + private key + webhook secret) installed on the org/user you
  want to watch (least-privilege scopes — see below). A read-only Gitea token is optional.
- A **reverse proxy doing forward-auth** (Traefik + Authentik reference). For local dev you
  can skip this with `HANGAR_FORWARD_AUTH=disabled`.

---

## Quickstart

### 1. Configure

```bash
cp deploy/.env.example deploy/.env
# Generate the credential-encryption key (FR-032) and paste it into HANGAR_SECRET_KEY:
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
# Edit deploy/.env: set HANGAR_FORWARD_AUTH, HANGAR_SECRET_KEY, HANGAR_DOMAIN, etc.
```

Hangar is **fail-closed**: if `HANGAR_FORWARD_AUTH` is unset it refuses to start. Use
`disabled` for a quick local look (you'll see a loud startup warning) or `enabled` behind
your proxy.

### 2a. Run with Docker Compose (production-like)

```bash
docker compose -f deploy/docker-compose.yml up --build
```

This builds the SPA, builds the backend image, and starts the `hangar` service. The port is
published on `127.0.0.1:8000` only (internal bind); real access is meant to come through
Traefik. Open the app, go to **Providers**, add a GitHub connection, and let the first sync
run. To use Postgres instead of SQLite:

```bash
# set HANGAR_DATABASE_URL=postgresql+asyncpg://hangar:hangar@postgres:5432/hangar in .env
docker compose -f deploy/docker-compose.yml --profile postgres up --build
```

### 2b. Run locally (dev)

Backend:

```bash
cd backend
pip install -e '.[dev]'
export HANGAR_FORWARD_AUTH=disabled
export HANGAR_SECRET_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
uvicorn hangar.main:app --reload          # API + /health on http://127.0.0.1:8000
```

Frontend (separate terminal):

```bash
cd frontend
npm install
npm run gen:api      # regenerate TS types from the OpenAPI contract
npm run dev          # SPA on http://127.0.0.1:5173 (proxies /api -> :8000)
```

---

## Configuration (environment / secrets)

All settings use the `HANGAR_` prefix and are read from the environment (no in-app config
UI). Full list with comments lives in [`deploy/.env.example`](deploy/.env.example).

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `HANGAR_FORWARD_AUTH` | **yes** | — | `enabled` or `disabled`. Unset ⇒ app refuses to start (fail-closed, FR-029). |
| `HANGAR_FORWARD_AUTH_USER_HEADER` | no | `Remote-User` | Identity header the proxy injects. Authentik: `X-authentik-username`. |
| `HANGAR_FORWARD_AUTH_ALLOWED_USER` | no | — | Optional single-identity pin: admit only this user. |
| `HANGAR_TRUSTED_PROXY_CIDR` | recommended | — | Identity header trusted only from this CIDR, e.g. `172.16.0.0/12` (FR-030). |
| `HANGAR_TRUSTED_PROXY_SECRET` | no | — | Optional shared secret; proxy sends it as `X-Hangar-Proxy-Secret`. |
| `HANGAR_ALLOW_PUBLIC_BIND` | no | unset | Must be set to bind a non-private/public interface; otherwise refused. |
| `HANGAR_OPERATOR` | no | `local-operator` | Audit actor used in `disabled` mode. |
| `HANGAR_SECRET_KEY` | **yes** (real providers) | — | Fernet key; encrypts provider credentials at rest (FR-032). |
| `HANGAR_HOST` / `HANGAR_PORT` | no | `127.0.0.1` / `8000` | Bind host/port for startup safety checks. |
| `HANGAR_DATABASE_URL` | no | `sqlite+aiosqlite:///./hangar.db` | DB URL. Postgres: `postgresql+asyncpg://hangar:hangar@postgres:5432/hangar`. |
| `HANGAR_POLL_INTERVAL_SECONDS` | no | `300` | Per-connection poll ceiling (ETag/webhook-driven). |
| `HANGAR_SEED_DEMO_DATA` | no | `true` | Load prototype fixtures on first boot. Set `false` for production. |
| `HANGAR_DOMAIN` | compose | `example.com` | Base domain for the Traefik router rule (`hangar.${HANGAR_DOMAIN}`). |

### Generate the credential-encryption key

```bash
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Put the output in `HANGAR_SECRET_KEY`. Keep it stable: rotating it invalidates stored
provider credentials.

---

## GitHub App setup

Hangar uses a **GitHub App** (not a personal token) so it can hold least-privilege,
per-connection scopes and receive webhooks.

1. Create a GitHub App (org or user settings → Developer settings → GitHub Apps).
2. Note the **App ID**, generate a **private key** (`.pem`), and set a **webhook secret**.
3. Set the webhook URL to `https://hangar.<your-domain>/api/v1/webhooks/<connection_id>`.
4. Grant **least-privilege** repository permissions for the remediations you intend to
   enable — e.g. *Contents: Read & write* (to open fix PRs), *Pull requests: Read & write*,
   *Administration / Repository settings: Read & write* only where settings-tier corrections
   are used, and read access to *Metadata*, *Actions*, *Dependabot* for detection. Subscribe
   to the repository / push / pull-request events you want to drive freshness.
5. **Install** the App on the org/user whose repos you want in the fleet.
6. In Hangar, open **Providers**, add a GitHub connection, and supply the App ID, the
   private key, and the webhook secret. Credentials are encrypted at rest with
   `HANGAR_SECRET_KEY`.

Content changes are always delivered as pull requests; Hangar never pushes or force-pushes.

---

## Forward-auth / Traefik notes

Hangar is meant to run behind a reverse proxy that authenticates the user and injects an
identity header. The reference is **Traefik + Authentik**:

- Set `HANGAR_FORWARD_AUTH=enabled` and attach Traefik's forward-auth middleware to the
  Hangar router (see the commented label block in
  [`deploy/docker-compose.yml`](deploy/docker-compose.yml)).
- Hangar reads the username from `HANGAR_FORWARD_AUTH_USER_HEADER` (Authentik:
  `X-authentik-username`) and trusts it **only** when the request comes from
  `HANGAR_TRUSTED_PROXY_CIDR` (and/or carries `HANGAR_TRUSTED_PROXY_SECRET`). A forged header
  sent directly to the app is rejected.
- The published port is bound to `127.0.0.1` so the app is reachable only through the proxy.
  Set `HANGAR_ALLOW_PUBLIC_BIND` only if you deliberately expose a public interface.
- `disabled` mode (no auth gate) is homelab/network-trust only and emits a prominent startup
  warning; it refuses a public bind without `HANGAR_ALLOW_PUBLIC_BIND`.

You'll need a Traefik `proxy` network and an `authentik@docker` middleware already running;
create the shared network once with `docker network create proxy`.

---

## Persistence: SQLite default, Postgres upgrade

- **SQLite** is the zero-ops default. In Docker the DB lives on the `hangar-data` named
  volume at `/data/hangar.db`.
- **Postgres** is a documented, non-default upgrade path. Run the optional `postgres`
  compose profile and point `HANGAR_DATABASE_URL` at
  `postgresql+asyncpg://hangar:hangar@postgres:5432/hangar`. The same SQLAlchemy models and
  Alembic migrations target both engines.

---

## Tests

```bash
cd backend && pytest        # provider-contract, remediation idempotency/PR-not-push,
                            # auth-mode (fail-closed/header-trust), check-evaluation suites
cd frontend && npm test     # Vitest units
cd frontend && npm run lint && npm run build
```

CI runs the same checks on every push/PR — see
[`.github/workflows/ci.yml`](.github/workflows/ci.yml).

---

## License

See repository for license details.
