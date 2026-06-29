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

## Run it locally

Hangar is **fail-closed**: it refuses to start unless `HANGAR_FORWARD_AUTH` is set. For
local work use `HANGAR_FORWARD_AUTH=disabled` (no SSO gate — you'll see a loud startup
warning; fine on your own machine).

### Fastest: demo mode, no GitHub App needed

The quickest way to "fire it up and click around." `HANGAR_SEED_DEMO_DATA=true` loads the
prototype's sample fleet on first boot, so every screen is populated without configuring a
real provider. Run the backend and frontend in two terminals.

**Terminal 1 — backend** (from `backend/`):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # first time only
pip install -e '.[dev]'                                # first time only

export HANGAR_FORWARD_AUTH=disabled
export HANGAR_SEED_DEMO_DATA=true
export HANGAR_SECRET_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
uvicorn hangar.main:app --reload                       # API + /health on http://127.0.0.1:8000
```

**Terminal 2 — frontend** (from `frontend/`):

```bash
cd frontend
npm install            # first time only
npm run gen:api        # generate TS types from the OpenAPI contract (first time / after contract edits)
npm run dev            # SPA on http://127.0.0.1:5173, proxies /api -> :8000
```

Open **http://127.0.0.1:5173**. You should land on a populated overview; the scorecard,
repo detail, and providers screens all work against the seeded fleet. The SQLite db is
written to `backend/hangar.db` — delete it to reset (the seed reloads on next boot).

> Demo connections have no real credential, so remediations are *simulated* (no live PRs).
> To exercise real detection/remediation, add a real GitHub connection (see below) and run
> with `HANGAR_SEED_DEMO_DATA=false`.

### Whole app in one process (built SPA served by the backend)

Mirrors production wiring (one Uvicorn process serves the API **and** the built SPA) without
Docker:

```bash
cd frontend && npm install && npm run gen:api && npm run build   # produces frontend/dist
cd ../backend && pip install -e '.[dev]'
export HANGAR_FORWARD_AUTH=disabled HANGAR_SEED_DEMO_DATA=true
export HANGAR_SECRET_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
export HANGAR_STATIC_DIR="$(pwd)/../frontend/dist"
uvicorn hangar.main:app                                          # full app on http://127.0.0.1:8000
```

### Run the published image (adopters)

The fastest way to try Hangar — pulls the prebuilt multi-arch image from GHCR
(`ghcr.io/get2knowio/hangar`), no source checkout or build required. Uses the
self-contained [`deploy/docker-compose.example.yml`](deploy/docker-compose.example.yml)
(no Traefik, no external network):

```bash
cp deploy/.env.example deploy/.env        # then edit deploy/.env (optional for a first look)
docker compose -f deploy/docker-compose.example.yml up -d
# open http://127.0.0.1:8000
```

It boots in `disabled` access mode on the loopback interface — fine for kicking the
tyres locally. **Before exposing Hangar to a network, set `HANGAR_ACCESS_MODE` to
`forward-auth` or `oidc`** (`disabled` means no auth). Set `HANGAR_SECRET_KEY` (generate
it with the command [below](#generate-the-credential-encryption-key)) before adding a real
GitHub connection, and `HANGAR_SEED_DEMO_DATA=true` to explore with offline sample data.
Pin a release in production via `HANGAR_IMAGE=ghcr.io/get2knowio/hangar:0.1.0`. To add
Postgres, uncomment `HANGAR_POSTGRES_*` in `deploy/.env` and run with `--profile postgres`.

### Full container stack (Docker Compose, build from source)

Builds the SPA + backend into one image and runs it the way it deploys behind Traefik +
forward-auth (the homelab reference). One-time setup:

```bash
cp deploy/.env.example deploy/.env
# In deploy/.env set at minimum:
#   HANGAR_FORWARD_AUTH=disabled
#   HANGAR_SEED_DEMO_DATA=true            # for a populated demo; false for real connections
#   HANGAR_SECRET_KEY=<paste the output of the command below>
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'

# The compose file attaches to a shared Traefik network named `proxy`. Create it once
# (harmless locally even without Traefik running):
docker network create proxy
```

Then:

```bash
docker compose -f deploy/docker-compose.yml up --build
```

The app is published on `127.0.0.1:8000` only (internal bind) — open
**http://127.0.0.1:8000**. Real external access is meant to come through Traefik + SSO;
the Traefik/`homepage`/`hola` labels in the compose file are inert until that proxy exists.
To use Postgres instead of SQLite:

```bash
# in deploy/.env: HANGAR_POSTGRES_HOST=postgres and HANGAR_POSTGRES_PASSWORD=hangar
docker compose -f deploy/docker-compose.yml --profile postgres up --build
```

---

## Configuration (environment / secrets)

All settings use the `HANGAR_` prefix and are read from the environment (no in-app config
UI). Full list with comments lives in [`deploy/.env.example`](deploy/.env.example).

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `HANGAR_ACCESS_MODE` | **yes**¹ | — | `forward-auth` \| `oidc` \| `disabled`. The canonical access-mode selector. |
| `HANGAR_FORWARD_AUTH` | **yes**¹ | — | Legacy selector: `enabled` (=forward-auth) or `disabled`. Honored when `HANGAR_ACCESS_MODE` is unset. |
| `HANGAR_FORWARD_AUTH_USER_HEADER` | no | `Remote-User` | Identity header the proxy injects. Authentik: `X-authentik-username`. |
| `HANGAR_FORWARD_AUTH_ALLOWED_USER` | no | — | Optional single-identity pin: admit only this user. |
| `HANGAR_TRUSTED_PROXY_CIDR` | recommended | — | Identity header trusted only from this CIDR, e.g. `172.16.0.0/12` (FR-030). |
| `HANGAR_TRUSTED_PROXY_SECRET` | no | — | Optional shared secret; proxy sends it as `X-Hangar-Proxy-Secret`. |
| `HANGAR_OIDC_ISSUER` | oidc | — | OIDC issuer base URL (discovery `…/.well-known/openid-configuration`). |
| `HANGAR_OIDC_CLIENT_ID` / `HANGAR_OIDC_CLIENT_SECRET` | oidc | — | Confidential-client credentials registered at your IdP. |
| `HANGAR_OIDC_REDIRECT_URL` | recommended (oidc) | derived | e.g. `https://hangar.<domain>/auth/callback`. Set it (or run uvicorn `--proxy-headers`) behind TLS. |
| `HANGAR_OIDC_SCOPES` | no | `openid email profile` | Scopes requested at login. |
| `HANGAR_OIDC_USERNAME_CLAIM` | no | `email` | ID-token claim used as the audit actor. |
| `HANGAR_OIDC_ALLOWED_USERS` / `HANGAR_OIDC_ALLOWED_GROUPS` | no | — | Optional allowlist (email/sub, or group via `HANGAR_OIDC_GROUPS_CLAIM`). Empty ⇒ admit any authenticated user. |
| `HANGAR_OIDC_POST_LOGOUT_REDIRECT_URL` | no | — | Optional RP-initiated logout target at the IdP. |
| `HANGAR_SESSION_SECRET` | oidc² | — | Signs the session cookie; falls back to `HANGAR_SECRET_KEY`. |
| `HANGAR_SESSION_MAX_AGE_SECONDS` / `HANGAR_SESSION_COOKIE_SECURE` | no | `28800` / `true` | Session lifetime; set `_SECURE=false` only for local http dev. |
| `HANGAR_SESSION_COOKIE_NAME` | no | `hangar_session` | Name of the OIDC session cookie (rarely changed). |
| `HANGAR_ALLOW_PUBLIC_BIND` | no | unset | Must be set to bind a non-private/public interface; otherwise refused. |
| `HANGAR_OPERATOR` | no | `local-operator` | Audit actor used in `disabled` mode. |
| `HANGAR_SECRET_KEY` | **yes** (real providers) | — | Fernet key; encrypts provider credentials at rest (FR-032). |
| `HANGAR_BASE_URL` | recommended (Connect with GitHub) | derived | Instance browser URL for the GitHub App manifest callbacks. LAN/VPN URLs are valid (browser redirects; no inbound). |
| `HANGAR_HOST` / `HANGAR_PORT` | no | `127.0.0.1` / `8000` | Bind host/port for startup safety checks. |
| `HANGAR_POSTGRES_HOST` | no | unset | Set to switch to Postgres (takes precedence over `HANGAR_DATABASE_URL`). |
| `HANGAR_POSTGRES_PASSWORD` | with `_HOST` | — | Postgres password; required when `HANGAR_POSTGRES_HOST` is set (fail-closed). |
| `HANGAR_POSTGRES_PORT` / `_DB` / `_USER` | no | `5432` / `hangar` / `hangar` | Remaining Postgres connection parts. |
| `HANGAR_POSTGRES_SSLMODE` | no | unset | libpq sslmode (`require`/`verify-full`/…), forwarded to asyncpg's `ssl` arg. |
| `HANGAR_DATABASE_URL` | no | `sqlite+aiosqlite:///./hangar.db` | Full SQLAlchemy URL escape hatch (used only when no `HANGAR_POSTGRES_HOST`). |
| `HANGAR_POLL_INTERVAL_SECONDS` | no | `300` | Per-connection poll ceiling (ETag/webhook-driven). |
| `HANGAR_STALE_AFTER_SECONDS` | no | `900` | Age after which a cached snapshot is flagged "stale" in the UI. |
| `HANGAR_GITHUB_HTTP_TIMEOUT_SECONDS` | no | `30` | Per-request timeout for provider calls, so one hung request can't stall the poll cycle. |
| `HANGAR_GITHUB_MAX_CONCURRENCY` | no | `8` | Max concurrent provider sub-requests per repo interrogation (lower it if you hit GitHub's secondary rate limit). |
| `HANGAR_WEBHOOK_SECRET` | no | — | HMAC secret for inbound provider webhooks; webhooks are refused (fail-closed) when unset. |
| `HANGAR_SEED_DEMO_DATA` | no | `false` | Load sample fixtures on first boot (offline demo). Production runs against real connections. |
| `HANGAR_STATIC_DIR` | no³ | — (image: `/app/static`) | Directory of the built SPA served at `/`. Set by the container image; don't override in a container. |
| `HANGAR_DOMAIN` | compose | `example.com` | Base domain for the Traefik router rule; used by `docker-compose.yml` only. |
| `HANGAR_IMAGE` | compose | `ghcr.io/get2knowio/hangar:latest` | Published image tag; used by `docker-compose.example.yml` only. |

¹ Exactly one access mode must be chosen — set `HANGAR_ACCESS_MODE` **or** the legacy
`HANGAR_FORWARD_AUTH`. If neither is set, Hangar refuses to start (fail-closed, FR-029).
² `oidc` mode also requires a session-signing secret — a dedicated `HANGAR_SESSION_SECRET`,
or it reuses `HANGAR_SECRET_KEY`.
³ Required only when running the backend **outside** a container (it must point at the built
SPA, e.g. `frontend/dist`); the container image sets it for you.

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

### One-click: Connect with GitHub (recommended)

Open **Providers → Add connection → Connect with GitHub**. Hangar creates *your own*
GitHub App via the App-manifest flow, then sends you to GitHub's install screen to pick the
org and repos — no App ID, installation ID, or PEM to copy. It captures the credentials
automatically and starts watching the selected repos.

- Set **`HANGAR_BASE_URL`** to your instance's browser URL (e.g. `https://hangar.lan`). It's
  only used to build the manifest's callback URLs. These are **browser redirects** — GitHub
  never connects inbound — so a **LAN/VPN-only** Hangar works fine (no public ingress needed).
  When unset it's derived from the request.
- **GitHub Enterprise** is supported: in the dialog set **GitHub host** to your GHES instance
  (`https://ghe.example.com`) or GHEC data-residency tenant (`https://acme.ghe.com`). Hangar
  derives the right API host (`…/api/v3` for GHES, `api.<tenant>.ghe.com` for GHEC) and install
  URL automatically. github.com is the default.
- The App is created under your user and can be installed on any org you administer; it
  requests write permissions so it can open fix PRs. Re-connecting another org reuses the same
  App. Webhooks ship **off**; the poller keeps snapshots fresh.

The manual paths below remain available (e.g. to reuse an App you already manage, or a PAT).

### Manual: bring your own App or token

1. Create a GitHub App (org or user settings → Developer settings → GitHub Apps).
2. Note the **App ID**, generate a **private key** (`.pem`), and set a **webhook secret**.
3. Set the webhook URL to `https://hangar.<your-domain>/api/v1/webhooks/<connection_id>`.
4. Grant **least-privilege** repository permissions for the remediations you intend to
   enable — e.g. *Contents: Read & write* (to open fix PRs), *Pull requests: Read & write*,
   *Administration / Repository settings: Read & write* only where settings-tier corrections
   are used, and read access to *Metadata*, *Actions*, *Dependabot* for detection. Subscribe
   to the repository / push / pull-request events you want to drive freshness.
5. **Install** the App on the org/user whose repos you want in the fleet, and note the
   **installation ID** (in the installation's settings URL).
6. Add the connection. Hangar mints short-lived installation tokens from the App key via
   `githubkit` (real GitHub App auth — no PAT). `POST /api/v1/providers` with:

   ```json
   {
     "provider_type": "github",
     "label": "gh:your-org",
     "scope": "org · N repos",
     "app_id": "123456",
     "installation_id": 7654321,
     "credential": "<contents of the .pem private key>",
     "writable": true
   }
   ```

   `credential` (the private-key PEM) is encrypted at rest with `HANGAR_SECRET_KEY`.
   Omit `writable` (or set `false`) for a read-only connection — write tiers are granted
   only when you opt in (least-privilege). Set `HANGAR_WEBHOOK_SECRET` to enable inbound
   webhooks (verified by HMAC; refused when unset).

Reads use conditional requests (`If-None-Match`/ETag), so a poll that finds nothing
changed costs no quota. Content changes are always delivered as pull requests; Hangar
never pushes or force-pushes.

---

## Choosing an access mode

Hangar gates access one of three ways — pick with `HANGAR_ACCESS_MODE`
(`forward-auth` | `oidc` | `disabled`); the legacy `HANGAR_FORWARD_AUTH` (`enabled`/`disabled`)
still works when `HANGAR_ACCESS_MODE` is unset. Either way, **identity is decoupled from your
provider credentials** — Hangar never uses GitHub/Gitea as the login.

### OIDC login

Use `HANGAR_ACCESS_MODE=oidc` when you want Hangar to handle login itself (no forward-auth
proxy). Hangar is a confidential OpenID Connect client (Authorization Code + PKCE) against
your own IdP — Authentik, Keycloak, etc. — and keeps the session in a signed, httpOnly cookie.

1. At your IdP, register Hangar as a **confidential** application; redirect URI
   `https://hangar.<domain>/auth/callback`. Note the issuer URL, client id, and client secret.
2. Set `HANGAR_ACCESS_MODE=oidc`, `HANGAR_OIDC_ISSUER`, `HANGAR_OIDC_CLIENT_ID`,
   `HANGAR_OIDC_CLIENT_SECRET`, a `HANGAR_SESSION_SECRET` (or reuse `HANGAR_SECRET_KEY`), and —
   behind a TLS proxy — `HANGAR_OIDC_REDIRECT_URL` (or run uvicorn with `--proxy-headers`).
3. Optionally restrict who may sign in with `HANGAR_OIDC_ALLOWED_USERS` /
   `HANGAR_OIDC_ALLOWED_GROUPS` (empty ⇒ any user your IdP authenticates).

OIDC still wants **TLS at the proxy**, but does **not** need a Traefik `ForwardAuth`
middleware — Hangar is the auth gate. The SPA shows a sign-in screen until you authenticate;
the sidebar gets a **Sign out** control. For local http dev set `HANGAR_SESSION_COOKIE_SECURE=false`.

### Forward-auth / Traefik notes

Hangar is meant to run behind a reverse proxy that authenticates the user and injects an
identity header. The reference is **Traefik + Authentik**:

- Set `HANGAR_ACCESS_MODE=forward-auth` (or legacy `HANGAR_FORWARD_AUTH=enabled`) and attach
  Traefik's forward-auth middleware to the
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
  compose profile and set the discrete vars in `deploy/.env`: `HANGAR_POSTGRES_HOST=postgres`
  plus `HANGAR_POSTGRES_PASSWORD` (the `_PORT`/`_DB`/`_USER` parts default to the bundled
  service). Setting `HANGAR_POSTGRES_HOST` switches Hangar to Postgres and **takes precedence
  over** `HANGAR_DATABASE_URL` (which is why the image's SQLite default doesn't get in the
  way). `HANGAR_DATABASE_URL` remains a full-URL escape hatch for non-standard setups. The
  `asyncpg` driver ships in the image, so no rebuild is needed; the same SQLAlchemy models and
  Alembic migrations target both engines. (For local Postgres testing outside Docker, install
  the driver with `pip install -e '.[dev,postgres]'`.)

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
