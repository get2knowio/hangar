<!-- SPECKIT START -->
## Active feature: Fleet Control Plane (Hangar MVP) — branch `001-fleet-control-plane`

Read the current plan and its design artifacts before working on this feature:
- Plan: `specs/001-fleet-control-plane/plan.md`
- Spec: `specs/001-fleet-control-plane/spec.md`
- Research (decisions): `specs/001-fleet-control-plane/research.md`
- Data model: `specs/001-fleet-control-plane/data-model.md`
- API contract: `specs/001-fleet-control-plane/contracts/openapi.yaml`
- **UI contract (normative): `specs/001-fleet-control-plane/contracts/ui-spec.md`** — the shipped UI MUST match `docs/prototype/Hangar.dc.html` (direction 02 · Clean Developer SAAS) and `docs/prototype/screenshots/`.
- Quickstart/validation: `specs/001-fleet-control-plane/quickstart.md`

**Stack**: Python 3.12 + FastAPI + SQLAlchemy/Alembic (SQLite default, Postgres upgrade), `githubkit` (GitHub App + webhooks), APScheduler poller, Fernet credential encryption · React + TypeScript + Vite + shadcn/ui + Tailwind + TanStack Query (types generated from the OpenAPI contract). Single Docker Compose stack behind Traefik `ForwardAuth`.

**Non-negotiables (constitution v1.0.0)**: provider-agnostic core via `RepoProvider`; human-triggered, PR-first, idempotent, audit-logged remediation (never push/force-push); fail-closed forward-auth (`HANGAR_FORWARD_AUTH` must be set) with proxy-only header trust + internal bind; declarative checks/policy as data; SQLite/single-stack homelab simplicity; typed contracts + required test suites.
<!-- SPECKIT END -->
