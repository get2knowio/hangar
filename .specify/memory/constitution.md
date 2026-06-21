<!--
SYNC IMPACT REPORT
==================
Version change: (template / unversioned) → 1.0.0
Bump rationale: Initial ratification of a concrete project constitution from the
template. MAJOR baseline because this is the first governed version.

Modified principles:
  - [PRINCIPLE_1_NAME] → I. Provider-Agnostic Core (No Platform Privileged)
  - [PRINCIPLE_2_NAME] → II. Human-Triggered, PR-First Remediation
  - [PRINCIPLE_3_NAME] → III. Secure by Default, Fail Closed at the Edge (NON-NEGOTIABLE)
  - [PRINCIPLE_4_NAME] → IV. Declarative, Data-Driven Checks & Policy
  - [PRINCIPLE_5_NAME] → V. Homelab Simplicity & Single-Stack Deployment (YAGNI)
Added principles (beyond template's 5 slots):
  - VI. Observability, Resilience & Rate-Limit Discipline
  - VII. Typed Contracts & Test Discipline

Added sections:
  - "Technology & Architecture Constraints" (was [SECTION_2_NAME])
  - "Development Workflow & Quality Gates" (was [SECTION_3_NAME])

Removed sections: none

Templates requiring updates:
  ✅ .specify/templates/plan-template.md — Constitution Check gate is generic
     ("Gates determined based on constitution file"); no edit required, gate
     resolves against these principles at plan time.
  ✅ .specify/templates/spec-template.md — aligned; no constitution-mandated
     section added/removed.
  ✅ .specify/templates/tasks-template.md — aligned; principle-driven task
     categories (security hardening, observability, tests-optional) already
     representable.
  ⚠ README.md / docs/quickstart.md — do not yet exist; create per Principle V
     and Governance when scaffolding begins (deployment + stand-up-from-README).

Follow-up TODOs: none. RATIFICATION_DATE set to first adoption date (2026-06-21).
-->

# Hangar Constitution

Hangar is a self-hosted, single-operator control plane that gives a repo owner a standing,
fleet-wide view across multiple connected providers — surfacing live activity and hygiene
drift, and letting the operator remediate in place. This constitution governs how Hangar is
built so that it stays safe to run against real write-capable provider credentials, honest
about its multi-provider promise, and trivial to stand up in a homelab.

## Core Principles

### I. Provider-Agnostic Core (No Platform Privileged)

The domain core MUST be expressed in the provider-neutral vocabulary of the PRD (Fleet,
Provider, Provider connection, Repo, Check, Policy, Finding, Remediation) and MUST NOT
encode any one platform's concepts into shared code. All platform access MUST flow through
the `RepoProvider` interface (interrogate, correct, subscribe). A Hangar instance MUST be
able to hold multiple provider connections at once — including multiple of the same type
(e.g., two GitHub orgs, or a GitHub org plus a Gitea server) — and every Repo, Finding, and
Remediation MUST be attributed to its originating connection. Checks MUST reference
provider-declared *capabilities*, never hard-coded platform branches, so that a remediation
GitHub can auto-correct but Gitea can only deep-link degrades cleanly per connection.

**Rationale**: GitHub is the MVP adapter and Gitea the fast-follower; treating the second
adapter as a refactor instead of a configuration step is the failure this principle exists
to prevent. Adding a provider connection MUST be configuration, not a code change.

### II. Human-Triggered, PR-First Remediation

Hangar observes and nudges; it MUST NOT autonomously mutate repos. Every API correction
MUST be explicitly initiated by the operator. Anything that touches repository *contents*
MUST go through a pull request — never a direct push, never a force-push. Settings-only
changes MAY use a scoped PATCH. Every correction MUST be idempotent and MUST be written to
an audit log recording connection, actor, action, timestamp, and resulting PR/URL. When a
connection lacks the write scopes a remediation needs, that remediation MUST collapse to a
deep-link for that connection rather than failing or silently escalating privilege.

**Rationale**: Hangar holds write credentials across someone's whole fleet. Safety,
reversibility, and a complete audit trail are non-negotiable properties of every mutation.

### III. Secure by Default, Fail Closed at the Edge (NON-NEGOTIABLE)

Access to Hangar is a homelab construct, decoupled from provider credentials. Hangar MUST
NOT implement its own login or use any provider as its identity gate. It MUST support
forward-auth behind a reverse proxy (Traefik `ForwardAuth` delegating to Authentik or
equivalent), reading a configurable identity header (`HANGAR_FORWARD_AUTH_USER_HEADER`,
default `Remote-User`; Authentik uses `X-authentik-username`).

The following are mandatory and testable:
- `HANGAR_FORWARD_AUTH` MUST be explicitly set (`enabled` or `disabled`); if unset, Hangar
  MUST refuse to start and tell the operator to choose. No silent default.
- Identity headers MUST be trusted only from the proxy. Hangar MUST bind to the proxy's
  internal network by default and MUST refuse to bind to a non-private/public interface
  unless `HANGAR_ALLOW_PUBLIC_BIND` is explicitly set. Anti-spoofing (trusted-proxy
  CIDR and/or shared-secret header) MUST be enforced wherever identity headers are honored.
- In `disabled` mode Hangar MUST emit a prominent startup warning.
- All provider credentials (App keys, webhook secrets, tokens) MUST be encrypted at rest.
- Provider connections MUST request only the scopes their enabled remediations require
  (least privilege, per connection).

**Rationale**: A write-capable control plane that trusts a forgeable header, or that quietly
runs wide-open, is a credential-theft incident waiting to happen. These rules close that gap.

### IV. Declarative, Data-Driven Checks & Policy

Checks are data, not UI. A Check MUST be a declarative definition (id, detection method,
pass/fail/unknown semantics, supported remediation tiers, and the capabilities it requires).
Adding or changing a check MUST NOT require touching the dashboard. Policy MUST be a
serializable schema of `{check_id, params, severity}`; the MVP ships a single fleet-wide
policy, but the representation MUST be defined so that Phase-1 multi-policy assignment (by
language/topic/tag/repo set, with precedence/merge rules) is additive, not a rewrite.

**Rationale**: The product's promise is that a new best practice is added as a definition,
not a code/UI change. Baking the catalog into the frontend breaks that promise permanently.

### V. Homelab Simplicity & Single-Stack Deployment (YAGNI)

Hangar MUST deploy as a single Docker Compose stack runnable on a modest homelab host, with
all configuration supplied via environment variables and secret mounts. Default to the
zero-ops choice: SQLite is the MVP datastore (Postgres is a documented upgrade path, not a
day-one requirement). The stack MUST carry the labels its ecosystem expects (Traefik routing
+ TLS + `ForwardAuth` attachment when access is enabled; `homepage.*` tile; `hola-*` fleet
metadata). New infrastructure, services, or dependencies MUST be justified against this
footprint; complexity that does not earn its keep MUST be rejected (YAGNI). A second person
MUST be able to clone the repo and stand Hangar up against their own providers from the
README alone.

**Rationale**: The deployment target is one operator's homelab, not a SaaS platform. Every
extra container or moving part is a cost the operator pays forever.

### VI. Observability, Resilience & Rate-Limit Discipline

Hangar MUST expose a `/health` endpoint, emit structured logs, and surface a visible
last-sync timestamp per connection so the operator can trust what they see. It MUST survive
provider API/webhook outages by serving the last good cached snapshot rather than erroring
or showing blanks. Provider access MUST be rate-limit-disciplined: per-connection token
budgets, conditional requests (ETags), and webhook-driven updates to reduce polling — Hangar
MUST NOT hammer a provider API on page load.

**Rationale**: A dashboard the operator cannot trust, or one that gets an instance
rate-limited, is worse than no dashboard. Trust and good API citizenship are features.

### VII. Typed Contracts & Test Discipline

The backend is Python/FastAPI; the frontend is React + TypeScript + shadcn/ui. The
boundary between them MUST be a typed, versioned API contract (e.g., OpenAPI), and frontend
types MUST derive from or be validated against that contract — no hand-drifted duplicate
type definitions. Python MUST be type-annotated and the codebase MUST pass its configured
linters and type checkers in CI. Automated tests are REQUIRED for: the `RepoProvider`
contract (each adapter), remediation idempotency and PR-not-push behavior, forward-auth
mode resolution (including fail-closed and header-trust paths), and check evaluation logic.
Tests SHOULD be written alongside or before the code they cover; behavior in Principles
II and III MUST NOT ship without tests.

**Rationale**: A multi-adapter system with write access and security-critical auth modes
cannot be refactored with confidence unless its contracts and dangerous paths are pinned by
tests and types.

## Technology & Architecture Constraints

- **Backend**: Python with FastAPI; provider adapters in Python. `githubkit` is the
  candidate GitHub client (async, typed, GitHub App + webhook support) — confirm at ADR.
- **Frontend**: React + TypeScript + shadcn/ui (Tailwind). This supersedes the PRD §8 open
  question of server-rendered vs SPA: Hangar ships an SPA on this stack.
- **Datastore**: SQLite by default; Postgres as a documented, non-default upgrade path.
- **Background work**: a scheduled per-connection poller plus a webhook receiver; ETag
  conditional requests for rate-limit health.
- **Deployment**: a single Docker Compose stack, env/secret-driven, fronted by Traefik with
  `ForwardAuth` (Authentik as the reference SSO), `homepage.*` and `hola-*` labels, bound to
  the proxy's internal network unless `HANGAR_ALLOW_PUBLIC_BIND` is set.
- **GitHub connection mechanism** (App vs token/OAuth) and exact per-remediation scope sets
  are deferred to ADRs but MUST satisfy Principles II and III when chosen.

## Development Workflow & Quality Gates

- **Spec-driven flow**: features proceed through the Specify pipeline (constitution → spec →
  plan → tasks → implement). Each `/speckit-plan` MUST pass the Constitution Check gate
  against these principles before Phase 0; re-check after Phase 1 design.
- **Constitution Check**: any plan that violates a principle MUST record the violation and
  its justification in the plan's Complexity Tracking table, or be revised to comply.
  Principles I, II, and III are not waivable by Complexity Tracking — they are gates.
- **Code review**: every PR MUST be reviewed for principle compliance. Reviewers MUST
  explicitly confirm that any remediation code is human-triggered, PR-first, idempotent, and
  audit-logged, and that any auth/credential code preserves fail-closed and header-trust
  guarantees.
- **CI gates**: lint, type-check, and the Principle-VII required test suites MUST pass before
  merge.
- **Docs**: README and quickstart MUST stay accurate enough for a stranger to stand Hangar
  up from scratch (Principle V); deployment/auth env vars MUST be documented when changed.

## Governance

This constitution supersedes other practices where they conflict. Amendments MUST be made by
a pull request that updates this file, states the rationale, and bumps the version per the
policy below; the change is adopted when that PR merges.

Versioning policy (semantic):
- **MAJOR**: backward-incompatible governance change — a principle removed or redefined in a
  way that invalidates existing compliant work.
- **MINOR**: a new principle or section added, or material expansion of existing guidance.
- **PATCH**: clarifications, wording, and non-semantic refinements.

Compliance review: the Constitution Check in the plan template is the primary enforcement
point; PR review is the secondary one. Dependent templates (`plan-template.md`,
`spec-template.md`, `tasks-template.md`) MUST be kept consistent with amendments as part of
the amending PR. Unjustified complexity MUST be rejected; justified exceptions (other than
the non-waivable gates above) MUST be recorded in the relevant plan's Complexity Tracking.

**Version**: 1.0.0 | **Ratified**: 2026-06-21 | **Last Amended**: 2026-06-21
