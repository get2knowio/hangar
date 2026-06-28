<!--
SYNC IMPACT REPORT
==================
Version change: 1.1.0 → 1.2.0
Bump rationale: MINOR. Principle III is broadened to permit OIDC (app-native
OpenID Connect login) as an explicit, operator-selected alternative to forward-auth.
This is a material expansion of existing guidance — forward-auth remains a
first-class reference mode and using a *provider* (GitHub/Gitea) as the identity
gate stays forbidden — so no prior compliant work is invalidated (MINOR, not MAJOR).

Modified principles:
  - III. Secure by Default, Fail Closed at the Edge — the absolute "MUST NOT
    implement its own login" is replaced by "MUST support one of: forward-auth |
    OIDC | disabled, chosen explicitly". OIDC is added with its own fail-closed
    requirements (confidential client, PKCE, full ID-token validation, signed
    session cookie, optional allowlist). The reverse-proxy IdP and the OIDC IdP are
    the same class of homelab SSO; the ban on *provider*-as-identity is unchanged.

Prior amendment (1.0.0 → 1.1.0) history retained below in the principle bodies
(connection-scoped isolation, fail-closed credential paths, Honest State, etc.).

Removed sections: none

Templates requiring updates:
  ✅ .specify/templates/plan-template.md — Constitution Check gate is generic; no edit.
  ✅ README.md — OIDC login section + HANGAR_ACCESS_MODE / HANGAR_OIDC_* documented.
  ✅ deploy/.env.example — OIDC + session vars added.

Follow-up TODOs: none. RATIFICATION_DATE unchanged (2026-06-21);
LAST_AMENDED_DATE set to 2026-06-28.
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

Connection isolation is a correctness property at every layer, not just an attribution label:
- Persistence keys, caches, and overlays MUST be connection-scoped. Same-named resources
  across connections (e.g., two `acme/api` repos in different orgs) MUST NOT collide,
  clobber, or bleed state into each other. Lookups from external events (webhooks) MUST
  resolve by `(identifier, connection_id)`, never by identifier alone.
- No platform host, domain, URL, or identifier format may be hard-coded in shared/core code.
  Provider-specific rendering — PR URLs, deep links, host derivation — MUST go through the
  `RepoProvider` interface (e.g., `provider.pr_url()`), so a GitHub-shaped string never leaks
  into a Gitea connection's output.

**Rationale**: GitHub is the MVP adapter and Gitea the fast-follower; treating the second
adapter as a refactor instead of a configuration step is the failure this principle exists
to prevent. Adding a provider connection MUST be configuration, not a code change. Two
review rounds both caught cross-connection clobber and hard-coded `github.com` URLs — these
rules make those defects gate failures, not stylistic notes.

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
NOT use any provider (e.g., GitHub or Gitea) as its identity gate. It MUST support an
operator-selected access mode — one of **`forward-auth`**, **`oidc`**, or **`disabled`**:
- `forward-auth` (reference): behind a reverse proxy (Traefik `ForwardAuth` delegating to
  Authentik or equivalent), reading a configurable identity header
  (`HANGAR_FORWARD_AUTH_USER_HEADER`, default `Remote-User`; Authentik uses
  `X-authentik-username`).
- `oidc`: app-native OpenID Connect login against the operator's own identity provider
  (Authentik, Keycloak, …) — the same class of homelab SSO a forward-auth proxy would
  delegate to. When enabled it MUST be a confidential Authorization-Code-with-PKCE client,
  MUST fully validate the ID token (signature via JWKS, `iss`/`aud`/`exp`/`nonce`) using a
  vetted library rather than hand-rolled crypto, MUST keep identity in a signed, httpOnly
  session cookie, and MAY restrict admission to an allowlist (by email/sub/group claim,
  analogous to `HANGAR_FORWARD_AUTH_ALLOWED_USER`).

The following are mandatory and testable:
- An access mode MUST be chosen explicitly (`HANGAR_ACCESS_MODE` = `forward-auth|oidc|disabled`,
  or the legacy `HANGAR_FORWARD_AUTH` = `enabled|disabled`); if none is set, Hangar MUST
  refuse to start and tell the operator to choose. No silent default. `oidc` mode MUST
  additionally fail closed when its required settings (issuer, client id/secret, session
  signing secret) are missing.
- Identity headers MUST be trusted only from the proxy. Hangar MUST bind to the proxy's
  internal network by default and MUST refuse to bind to a non-private/public interface
  unless `HANGAR_ALLOW_PUBLIC_BIND` is explicitly set. Anti-spoofing (trusted-proxy
  CIDR and/or shared-secret header) MUST be enforced wherever identity headers are honored.
- In `disabled` mode Hangar MUST emit a prominent startup warning.
- All provider credentials (App keys, webhook secrets, tokens) MUST be encrypted at rest.
- Provider connections MUST request only the scopes their enabled remediations require
  (least privilege, per connection). Capabilities default to read-only; write tiers are
  granted only when the operator declares the credential writable.

Fail-closed extends to every credential-consuming and untrusted-input path, not just the
startup gate:
- A credentialed call MUST refuse to act anonymously. If no credential is attached, or a
  credential is half-configured (e.g., a GitHub App missing `app_id`/`installation_id`, or a
  PEM that would otherwise be misused as a token), the call MUST raise — never silently fall
  back to an anonymous request, a 401, or a degraded guess. The decrypted credential MUST be
  threaded to the adapter *before* the provider call, so live actions do not 500 mid-flight.
- All untrusted input MUST be validated and contained at the boundary: filesystem paths
  (e.g., SPA static serving) MUST be confined to their root via realpath containment to block
  traversal; inbound webhooks MUST verify their HMAC signature against the configured secret
  and MUST fail closed (refuse, do not process) when that secret is unset.
- Secret/signature comparisons MUST be constant-time. Auth exemptions MUST be the narrowest
  exact path prefixes (e.g., `/assets/`, the HMAC-authenticated webhook path), never broad
  prefixes that also match siblings.
- No undocumented environment variable, flag, or code path may weaken or override a security
  gate (the fail-closed bind, forward-auth, HMAC verification). Every security-relevant knob
  MUST be documented; a hidden escape hatch is a violation even if it defaults to safe.

**Rationale**: A write-capable control plane that trusts a forgeable header, or that quietly
runs wide-open, is a credential-theft incident waiting to happen. Both review rounds found
anonymous fallbacks, unverified webhooks, path traversal, a non-constant-time compare, and an
undocumented bind override — every one of these turns a "secure by default" claim into a lie,
so they are enumerated here as hard rules.

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

Resilience is per-unit, and conditional requests MUST be sound:
- Sync MUST isolate failures per repo: one repo's error MUST NOT roll back or abort already-
  synced repos, nor block the connection's `last_sync_at`. Commit/isolate at the repo grain.
- A provider sub-error (403/404 on one resource) MUST degrade that resource's determination
  to `unknown` (see Principle VIII) — it MUST NOT abort the whole snapshot.
- Conditional-request (ETag/304) handling MUST be sound: a 304 may only suppress re-fetching
  the *exact* resource that ETag covers. A 304 MUST NOT drop, stale, or silently blank a
  determination derived from a resource that was not itself revalidated. If sub-resources are
  not covered by the primary ETag, they MUST be fetched fresh each poll.
- Cache, poll, and frontend `staleTime` cadences MUST be mutually coherent (the UI MUST NOT
  refetch faster than the backend produces new snapshots).
- Fleet-scale read paths MUST avoid N+1 queries and redundant recomputation: aggregate with
  grouped queries, and compute a derived matrix/rollup in a single pass rather than rescanning.

**Rationale**: A dashboard the operator cannot trust, or one that gets an instance
rate-limited, is worse than no dashboard. The review rounds found a single repo failure
rolling back the whole sync, a 403 aborting a snapshot, a 304 dropping fresh data, N+1 card
queries, and a staleTime/poll mismatch — resilience and efficiency are correctness here, not
polish.

### VII. Typed Contracts & Test Discipline

The backend is Python/FastAPI; the frontend is React + TypeScript + shadcn/ui. The
boundary between them MUST be a typed, versioned API contract (e.g., OpenAPI), and frontend
types MUST derive from or be validated against that contract — no hand-drifted duplicate
type definitions. This applies on both sides: enums and result shapes shared across the
boundary (e.g., remediation kind, finding status, remediate result) MUST be derived from the
generated contract types on the backend and the frontend, never re-declared by hand.

Two further rules keep behavior honest and maintainable:
- Logic MUST read structured fields, never parse human-display strings. If a decision needs a
  count or status, the API MUST expose it as a structured field (e.g., `ci_failing`,
  `critical_alerts`); deriving it by parsing a rendered string like "N critical" is forbidden.
- Shared derived values MUST have a single canonical definition (DRY). Tier labels, provider
  names, and similar maps MUST live in one place and be imported, not copied per layer.

Python MUST be type-annotated and the codebase MUST pass its configured linters and type
checkers in CI. Automated tests are REQUIRED for: the `RepoProvider` contract (each adapter),
remediation idempotency and PR-not-push behavior, forward-auth mode resolution (including
fail-closed and header-trust paths), check evaluation logic, cross-connection isolation
(Principle I), and the conditional-request/304 path (Principle VI). Tests SHOULD be written
alongside or before the code they cover; behavior in Principles II, III, and VIII MUST NOT
ship without tests, and every defect fixed in review MUST land with a regression test.

**Rationale**: A multi-adapter system with write access and security-critical auth modes
cannot be refactored with confidence unless its contracts and dangerous paths are pinned by
tests and types. Review caught hand-written duplicates of generated types, urgency logic that
parsed a display string, and triplicate label/name maps — all avoidable with these rules.

### VIII. Honest State — No Fakes, Stubs, or Fabricated Results (NON-NEGOTIABLE)

Every value Hangar shows or records MUST reflect reality. The product's worth is operator
trust; a plausible-looking fake is worse than an honest gap.

- No hardcoded or placeholder value may stand in for real computed state. A timestamp like
  `last_sync_at`, a "synced" flag, or any status MUST come from the actual event, never a
  literal baked in to look populated.
- Every check determination MUST be computed from real provider reads, OR honestly reported
  as `unknown` *only* because the connection genuinely lacks the capability/scope to decide
  (capability-gated, per Principle I). A blanket `unknown` returned where the data is in fact
  available is a violation — checks MUST NOT ship as stubs that always return `unknown`.
- Remediation MUST NOT fabricate outcomes. It MUST NOT record a "PR merged" pass, an audit
  entry, or a success when no such action occurred (e.g., marking merged with no open Hangar
  PR MUST return an error, not a fabricated pass). An audit entry MUST correspond to an action
  that actually happened, and `/remediate` MUST return the exact entry it produced, not the
  newest row by guess (race-safe).
- Demo/seed data MUST be opt-in and OFF by default (`HANGAR_SEED_DEMO_DATA=false`), so a
  default deployment runs against real connections. Demo providers exist only as an explicit
  offline/test harness and MUST NOT clobber real data.
- Frontend calls MUST surface real outcomes: a non-2xx response MUST reject and raise an error
  toast, never resolve as a false success.

**Rationale**: The single largest theme across both review rounds was scaffolding that looked
done — a hardcoded "synced" value, demo data on by default, checks that always returned
`unknown`, an adapter that faked auth, and remediation that could fabricate a merged-PR pass.
Each one silently lies to the operator who is trusting Hangar with fleet-wide write
credentials. "It compiles and the UI is populated" is not "it works"; this principle makes the
difference a hard gate.

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
  Principles I, II, III, and VIII are not waivable by Complexity Tracking — they are gates.
- **Code review**: every PR MUST be reviewed for principle compliance. Reviewers MUST
  explicitly confirm that any remediation code is human-triggered, PR-first, idempotent, and
  audit-logged, and that any auth/credential code preserves fail-closed and header-trust
  guarantees.
- **Code Review Checklist (learned from review rounds)**: reviewers MUST actively check for
  the defect classes that two prior reviews surfaced, because these recur and pass casual
  inspection:
  1. **Fakes/stubs (VIII)**: hardcoded "done" values, demo data on by default, checks that
     always return `unknown`, fabricated audit/PR-merged results, frontend swallowing non-2xx.
  2. **Fail-closed gaps (III)**: anonymous fallback on a missing/half-configured credential,
     credential not threaded before the provider call, unverified or non-fail-closed webhooks,
     path traversal, non-constant-time compares, over-broad auth exemptions, undocumented
     overrides of a security gate.
  3. **Cross-connection isolation (I)**: persistence keys/overlays/caches not scoped by
     connection; same-named resources colliding; lookups by identifier without `connection_id`.
  4. **Provider leaks (I)**: hardcoded platform host/URL/format in core instead of via the
     provider interface.
  5. **Resilience & conditional requests (VI)**: a single repo/sub-resource failure aborting or
     rolling back a batch; a 304 dropping a determination it didn't actually cover.
  6. **Typed contracts & DRY (VII)**: hand-drifted duplicates of generated types, logic parsing
     a display string, duplicated label/name maps.
  7. **Efficiency (VI)**: N+1 queries on fleet endpoints, redundant multi-pass computation,
     cache/poll/staleTime cadence mismatch.
- **CI gates**: lint, type-check, and the Principle-VII required test suites MUST pass before
  merge. Each defect fixed in review MUST land with a regression test.
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

**Version**: 1.2.0 | **Ratified**: 2026-06-21 | **Last Amended**: 2026-06-28
