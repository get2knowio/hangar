# Implementation Plan: Fleet Control Plane (Hangar MVP)

**Branch**: `001-fleet-control-plane` | **Date**: 2026-06-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-fleet-control-plane/spec.md`

**UI reference (normative)**: `docs/prototype/Hangar.dc.html` (chosen direction **02 · Clean Developer SAAS** from `docs/prototype/Directions.dc.html`) and `docs/prototype/screenshots/`. The shipped UI MUST match this prototype — its five screens, layout, design tokens, typography, status-only color, light/dark theme, connection switcher, remediation controls, and toast — pixel-for-intent. See [contracts/ui-spec.md](./contracts/ui-spec.md).

## Summary

Hangar is a single-operator, self-hosted control plane that aggregates a **fleet** (the union of repositories across one or more provider connections) into one dashboard, scores each repo against a declarative best-practice **policy**, and lets the operator remediate drift in place along a Report → Deep-link → API-correction spectrum — every content change delivered as a pull request, never a push.

**Technical approach**: A provider-agnostic Python/FastAPI backend exposes a typed, versioned OpenAPI contract consumed by a React + TypeScript + shadcn/ui SPA built to the `docs/prototype` design. All platform access flows through a `RepoProvider` interface (interrogate / correct / subscribe) with GitHub as the MVP adapter (`githubkit`, GitHub App) and a Gitea adapter designed-for but deferred. A per-connection scheduled poller plus a webhook receiver keep normalized repo snapshots fresh (ETag-conditional, rate-limit-disciplined); checks are declarative data evaluated into Findings; remediations are human-triggered, idempotent, and audit-logged. Persistence is SQLite by default (Postgres as a documented upgrade path) with provider credentials encrypted at rest. The whole thing deploys as a single Docker Compose stack behind Traefik `ForwardAuth`, fail-closed unless the access mode is explicitly chosen.

## Technical Context

**Language/Version**: Python 3.12 (backend); TypeScript 5.x on Node 20 (frontend)

**Primary Dependencies**:
- Backend: FastAPI, Uvicorn, Pydantic v2, SQLAlchemy 2.x (async) + Alembic, `githubkit` (async, typed GitHub App + webhooks), APScheduler (per-connection poller), `cryptography` (Fernet, credential encryption at rest), `structlog` (structured logs), `httpx`.
- Frontend: React 18, Vite, TypeScript, shadcn/ui + Tailwind CSS, TanStack Query (data fetching/caching), `openapi-typescript` (types generated from the OpenAPI contract — no hand-drifted types).

**Storage**: SQLite by default (file on a mounted volume); Postgres as a documented, non-default upgrade path. Schema managed by Alembic; the same SQLAlchemy models target both engines.

**Testing**: pytest + pytest-asyncio + respx/HTTP mocks (backend; provider-contract, remediation, auth-mode, check-evaluation suites per Constitution VII); Vitest + React Testing Library (frontend units); Playwright (end-to-end across the five screens, asserting the prototype's flows).

**Target Platform**: Linux x86_64 homelab host running Docker Compose, behind a Traefik reverse proxy with a forward-auth SSO layer (Authentik reference). Frontend served as static assets; SPA talks to the FastAPI service over the internal Docker network.

**Project Type**: Web application (FastAPI backend + React SPA frontend), packaged as a single Compose stack.

**Performance Goals**: Cached dashboard usable in < 5 s (SC-001) for a fleet of up to ~500 repositories across a handful of connections; opening any screen issues **zero** bursts of live provider API calls (SC-010) — reads serve the cached snapshot.

**Constraints**: Fail-closed access (refuse to start if `HANGAR_FORWARD_AUTH` unset); identity header trusted only from the proxy; bind to the internal network unless `HANGAR_ALLOW_PUBLIC_BIND` set; all provider credentials encrypted at rest; least-privilege per-connection scopes; content corrections via PR only (never push/force-push); every correction idempotent and audit-logged; survive provider outages by serving the last good snapshot; single Docker Compose footprint (YAGNI on new infra).

**Scale/Scope**: Up to ~500 repos / handful of connections (MVP target). 5 screens (Overview, Hygiene scorecard, Catalog & policy, Providers & access, Repo drill-down) + light/dark theme, connection switcher, toast. 23-check MVP catalog (the full FR-009 set), of which a curated subset ships writable API corrections at MVP (see Assumptions / research.md). The `docs/prototype` seeds 20 of these as illustrative data; the catalog is data (FR-008), so the remaining three (CI-workflow-green, Actions-pinned-to-SHA, workflow-permissions-least-privilege) are added as definitions without any UI change.

## Constitution Check

*GATE: evaluated against `.specify/memory/constitution.md` v1.0.0. Re-checked after Phase 1 design.*

| # | Principle | How this plan satisfies it | Status |
|---|-----------|----------------------------|--------|
| I | Provider-Agnostic Core | Domain uses PRD vocabulary only; all platform access via `RepoProvider` (interrogate/correct/subscribe); connections carry declared **Capabilities**; checks reference capabilities, never platform branches; multiple connections incl. same-type; everything attributed to its connection. Adding Gitea = a new adapter + config, no shared-code change. | PASS |
| II | Human-Triggered, PR-First Remediation | Every correction is operator-initiated (no autonomous mutation); content changes go through a PR (never push/force-push); settings via scoped PATCH; idempotency keyed on an existing open Hangar PR; audit log records connection/actor/action/timestamp/PR-URL; missing write scope collapses to deep-link per connection. | PASS (non-waivable gate met) |
| III | Secure by Default, Fail Closed (NON-NEGOTIABLE) | `HANGAR_FORWARD_AUTH` must be `enabled`/`disabled` or the app refuses to start; identity header (`HANGAR_FORWARD_AUTH_USER_HEADER`, default `Remote-User`) trusted only from a trusted-proxy CIDR / shared secret; internal-network bind unless `HANGAR_ALLOW_PUBLIC_BIND`; prominent warning in disabled mode; credentials encrypted at rest; least-privilege per-connection scopes. | PASS (non-waivable gate met) |
| IV | Declarative, Data-Driven Checks & Policy | Checks are declarative definitions (id, detection, pass/fail/unknown, remediation tiers, required capabilities); adding/changing a check is data, not dashboard code; Policy is serializable `{check_id, params, severity}`; single fleet-wide policy at MVP, representation future-proofed for multi-policy. | PASS |
| V | Homelab Simplicity & Single-Stack (YAGNI) | One Docker Compose stack, env/secret-driven; SQLite default, Postgres documented-not-required; Traefik + `ForwardAuth` + `homepage.*` + `hola-*` labels; internal bind; README stand-up by a stranger. No new infra beyond app + proxy. | PASS |
| VI | Observability, Resilience & Rate-Limit Discipline | `/health` endpoint; structured logs; visible per-connection last-sync; serve last good cached snapshot on outage; per-connection token budgets + ETag conditional requests + webhook-driven updates; no API bursts on page load. | PASS |
| VII | Typed Contracts & Test Discipline | Typed, versioned OpenAPI contract; FE types generated from it (no duplicates); Python type-annotated, lint + type-check in CI; required tests for provider contract, remediation idempotency/PR-not-push, forward-auth mode resolution (fail-closed + header-trust), and check evaluation. | PASS |

**Result**: No violations. **Complexity Tracking is empty** (no principle waived; the two-deliverable backend+frontend split is the constitution-mandated stack, not added complexity).

**Post-Phase-1 re-check**: After generating `data-model.md`, `contracts/openapi.yaml`, and `contracts/ui-spec.md`, all seven gates still PASS — the design reinforces them: the domain/providers split keeps the core provider-neutral (I); the remediation endpoint is human-triggered, PR-only, idempotent, audit-logged (II); auth config + `/me` + fail-closed startup encode the secure edge (III); the catalog/policy contract is pure data (IV); the single Compose stack + SQLite default hold (V); `/health` + per-connection `last_sync` + cached reads hold (VI); the OpenAPI contract with generated FE types + the named test suites hold (VII). No new entries in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/001-fleet-control-plane/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions resolving the deferred ADR-level unknowns
├── data-model.md        # Phase 1 — entities, fields, relationships, state machines
├── quickstart.md        # Phase 1 — runnable validation guide (the five-screen acceptance walk)
├── contracts/
│   ├── openapi.yaml      # Phase 1 — typed, versioned HTTP API contract (FE types derive from this)
│   └── ui-spec.md        # Phase 1 — normative UI contract bound to docs/prototype
└── tasks.md             # Phase 2 — created by /speckit-tasks (NOT here)
```

### Source Code (repository root)

```text
backend/
├── src/hangar/
│   ├── domain/              # Provider-neutral core: Fleet, Repo, Check, Policy, Finding, Remediation, Capability
│   │   ├── models.py        # Domain dataclasses / Pydantic models (PRD vocabulary only)
│   │   ├── checks/          # Declarative check definitions (data + detection fns), one module per group
│   │   ├── policy.py        # Serializable {check_id, params, severity}; hygiene/effStatus evaluation
│   │   └── remediation.py   # Tier resolution, idempotency, PR-vs-settings orchestration
│   ├── providers/           # Adapters behind the RepoProvider interface
│   │   ├── base.py          # RepoProvider Protocol: interrogate / correct / subscribe + capability set
│   │   ├── github/          # MVP adapter (githubkit, GitHub App, webhooks, ETag)
│   │   └── gitea/           # Designed-for, stub/deferred (read + deep-link capabilities only)
│   ├── api/                 # FastAPI routers (one per screen domain) — the OpenAPI surface
│   ├── services/            # Sync poller, webhook receiver, audit log, snapshot cache
│   ├── auth/                # Forward-auth middleware: mode resolution, header trust, fail-closed bind
│   ├── persistence/         # SQLAlchemy models, repositories, Alembic migrations, credential encryption
│   ├── config.py            # Env/secret settings (HANGAR_*), startup validation
│   └── main.py              # App factory, /health, structured logging, lifespan (scheduler)
└── tests/
    ├── contract/            # RepoProvider contract suite (run against each adapter)
    ├── integration/         # Sync, remediation idempotency/PR-not-push, auth-mode resolution
    └── unit/                # Check evaluation, policy roll-up, tier resolution

frontend/
├── src/
│   ├── app/                 # Router + shell (topbar, sidebar, theme provider, toast host)
│   ├── screens/             # Overview, Scorecard, Catalog, Providers, RepoDetail (1:1 with prototype)
│   ├── components/          # shadcn/ui-based primitives + Hangar widgets (StatTile, RepoTable, ScorecardMatrix, CheckRow, RemediationControl, ConnSwitcher, AttentionFeed, AuditLog)
│   ├── lib/                 # api client, generated types, design tokens, status→color/glyph maps
│   └── styles/              # Tailwind config + CSS variables mirroring the prototype :root tokens
└── tests/                   # Vitest unit + Playwright e2e (five-screen acceptance flows)

deploy/
├── docker-compose.yml       # Single stack: hangar app (+ optional Postgres profile); Traefik labels, ForwardAuth, homepage.* + hola-* labels, internal bind
├── Dockerfile               # Multi-stage: build SPA → serve via FastAPI/static
└── .env.example             # Documented HANGAR_* env vars + secret mounts

README.md                    # Stand-up-from-scratch guide (Principle V / SC-006)
```

**Structure Decision**: Web application (Constitution VII mandates Python/FastAPI backend + React/TS/shadcn frontend), so a two-deliverable `backend/` + `frontend/` layout plus a `deploy/` stack. The backend is split **domain / providers / services / auth / persistence** to keep Principle I's provider-neutral core physically separate from adapter code, so adding Gitea touches only `providers/gitea/` + config. The frontend mirrors the prototype's five screens one-to-one.

## Complexity Tracking

> No Constitution Check violations. Table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
