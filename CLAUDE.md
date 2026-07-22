# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What Hangar is

A self-hosted, single-operator **fleet control plane**: it aggregates repos across one or
more provider connections (GitHub today, Gitea designed-for), scores each against a
declarative best-practice **policy**, and remediates hygiene drift in place — every content
change delivered as a **pull request, never a push**. It runs as one Docker Compose stack
behind a forward-auth reverse proxy. Full product detail: `README.md` and `prd.md`.

Governance is enforced, not aspirational: read `.specify/memory/constitution.md` — its
principles are gates, and several were added after two code-review rounds caught recurring
defects. The "Invariants" section below is the working distillation; the constitution is the
source of truth.

## Commands

Backend (run from `backend/`):

```bash
pip install -e '.[dev]'                  # install with dev tools
export HANGAR_FORWARD_AUTH=disabled      # required: app is fail-closed and won't start unset
export HANGAR_SECRET_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
uvicorn hangar.main:app --reload         # API + /health on :8000

pytest                                   # full suite
pytest tests/integration/test_remediation_pr_first.py   # one file
pytest -k webhook_signature              # one test by name
ruff check src tests                     # lint
ruff format                              # format
mypy                                     # type-check (config targets the hangar package)
alembic upgrade head                     # apply migrations
alembic revision --autogenerate -m "..."  # new migration after model changes
```

Frontend (run from `frontend/`):

```bash
npm install
npm run gen:api          # regenerate src/lib/api-types.ts from the OpenAPI contract
npm run dev              # SPA on :5173, proxies /api -> :8000
npm test                # vitest (npm test -- -t "name" for one); npm run test:watch
npm run e2e             # Playwright
npm run lint            # eslint, zero-warnings
npm run build           # tsc --noEmit && vite build  (also the typecheck gate)
```

Full Docker/Compose, env-var, GitHub-App, and forward-auth setup is in `README.md`.

## Architecture

The backend (`backend/src/hangar/`) is strictly layered; the dependency direction is
`api → services → {domain, providers, persistence}`, and `domain` knows nothing about any
platform.

- **`domain/`** — the provider-neutral core. `models.py` (`Repo`, `ProviderConnection`,
  `Check`, `Capability`, `RemediationKind`, …), `checks/` (the declarative check **catalog**,
  split by group: supply_chain, release, governance, security, project_meta), `policy.py`,
  `remediation.py`. No GitHub/Gitea strings live here.
- **`providers/`** — the **only** seam to a platform (`base.py` defines the `RepoProvider`
  Protocol: `interrogate` / `correct` / `subscribe` + `deep_link` / `pr_url`). `registry.py`
  maps `provider_type → adapter` and falls back to `demo.py` (offline simulation) for a
  connection with no stored credential. `github/` holds the live adapter + `detection.py`
  (turns live reads into pass/fail/unknown per check); `gitea/` is the deferred adapter.
  Adding a provider = a new adapter module + one registry entry; the core gets no new branch.
- **`services/`** — orchestration. `sync.py` is the APScheduler per-connection poller; the
  read services (`overview`, `scorecard`, `repo_detail`) evaluate the catalog against the
  **cached** snapshot; `connections`, `webhooks`, `audit` round it out.
- **`persistence/`** — async SQLAlchemy (`db.py`, `models.py`, `repositories.py`), Fernet
  credential encryption (`crypto.py`), `seed.py`. Alembic migrations are packaged inside the
  app at `backend/src/hangar/migrations/` (applied on startup by `db.apply_migrations`).
- **`auth/forward_auth.py`** — the outermost security middleware. **`config.py`** —
  settings + `validate_startup` (the fail-closed gate). **`main.py`** — app factory: startup
  gate → seed → scheduler lifespan, the HMAC-verified webhook receiver, and the SPA mount.

Frontend (`frontend/src/`): `screens/` (route pages), `app/` (shell/layout), `components/`,
`lib/` (`api.ts` client, `api-types.ts` generated, `status.ts`). The built SPA is served as
static assets by the backend process in production.

Two key request flows:
1. **Reads never hit the provider.** The poller interrogates repos in the background (with
   conditional/ETag requests) and upserts normalized snapshots; page loads read cached
   snapshots and evaluate the catalog. Don't add a synchronous provider call to a read path.
2. **Remediation** is operator-triggered → service attaches the decrypted credential →
   `provider.correct()` opens a PR (idempotent) → an audit entry is written → the endpoint
   returns *that* entry.

## Invariants (these are gates — see the constitution)

- **Provider seam is the only platform boundary.** No platform host/URL/identifier format in
  `domain`/`services`/core — build provider-specific strings via `provider.pr_url()` /
  `deep_link()`. Checks reference declared **capabilities**, never `if provider == "github"`.
- **Checks are data.** Add/change a check in `domain/checks/`, never in the frontend or a
  dashboard service. The 23-check catalog is the FR-009 set.
- **Honest state — no fakes.** An undeterminable check is `unknown` (capability-gated), never
  a fabricated pass/fail or a blanket `unknown` where data is available. No hardcoded
  "synced"/status values; no fabricated audit or "PR merged" outcomes. Demo/seed data is
  opt-in and **off** by default (`HANGAR_SEED_DEMO_DATA=false`).
- **Connection-scoped everything.** Persistence keys, caches, and overlays are scoped by
  connection; same-named repos across connections must not collide. Webhook lookups resolve
  by `(identifier, connection_id)`, never identifier alone.
- **Fail closed.** Startup refuses if `HANGAR_FORWARD_AUTH` is unset; credential paths refuse
  to act anonymously or with a half-configured credential; webhooks verify HMAC and refuse
  when the secret is unset. Identity headers are trusted only from the proxy CIDR. No
  undocumented env var may weaken a security gate.
- **Remediation is PR-first.** Human-triggered, idempotent, audit-logged; never a push or
  force-push.
- **Typed contracts, no drift.** The OpenAPI contract
  (`specs/001-fleet-control-plane/contracts/openapi.yaml`) is the boundary. Frontend types
  are generated (`npm run gen:api`) — never hand-write a duplicate, and never parse a
  human-display string for logic (expose a structured field instead). Keep shared values
  (tier labels via `domain.models.tier_label`, provider names via `providers.base.provider_name`)
  single-sourced.
- **Resilience.** Sync isolates failures per repo (one repo's error never rolls back the
  batch); a provider sub-error degrades that resource to `unknown`, not an aborted snapshot.
- **Every defect fixed in review lands with a regression test.** Required suites cover the
  RepoProvider contract, remediation idempotency/PR-not-push, forward-auth modes, check
  evaluation, cross-connection isolation, and the conditional-request/304 path.

## Spec-driven workflow

This repo uses Spec Kit. Feature design lives under `specs/001-fleet-control-plane/`; the
`/speckit-*` commands drive constitution → spec → plan → tasks → implement, and git
auto-commit hooks are configured in `.specify/extensions.yml`. The block below is managed by
`speckit-agent-context-update` — leave it intact.

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
at specs/001-fleet-control-plane/plan.md
<!-- SPECKIT END -->
