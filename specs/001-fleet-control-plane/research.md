# Phase 0 Research: Fleet Control Plane (Hangar MVP)

Resolves the open/deferred decisions the constitution and spec parked for ADR/planning. Each entry: **Decision · Rationale · Alternatives considered**. Items here feed Technical Context in `plan.md`; none remain `NEEDS CLARIFICATION`.

## 1. GitHub connection mechanism (App vs OAuth/PAT)

**Decision**: **GitHub App** installation per connection. The App declares fine-grained, least-privilege permissions; per-connection it stores the installation id and a per-installation token minted on demand. Webhooks are delivered to Hangar's receiver with a per-App secret.

**Rationale**: Satisfies Constitution III (least privilege, per-connection scopes) and VI (webhook-driven updates, higher rate limits than PATs). A GitHub App cleanly separates "what Hangar may do" (App permissions) from "where" (installations = connections), and supports multiple installations (= multiple connections of the same type, FR-022). `githubkit` has first-class App + installation-token + webhook support.

**Alternatives considered**: OAuth app (user-scoped, coarser, ties identity to a provider — violates the decoupling in Principle III); classic/fine-grained PAT (operationally simple but coarse scopes, lower rate limits, manual rotation — kept only as the **Gitea** path via scoped token, read-only at MVP).

## 2. GitHub client library

**Decision**: **`githubkit`** (async, fully typed, GitHub App + webhook verification).

**Rationale**: Constitution names it as the candidate; it is async (fits FastAPI + the poller), typed (Principle VII), and supports App auth, installation tokens, conditional requests (ETag), and webhook signature verification out of the box.

**Alternatives considered**: PyGithub (sync, untyped-ish, no native async); raw `httpx` against the REST/GraphQL API (more control but reimplements auth/pagination/typing).

## 3. Datastore & migrations

**Decision**: **SQLite by default** on a mounted volume, accessed via **SQLAlchemy 2.x async** with **Alembic** migrations; the identical models run on **Postgres** via a documented `DATABASE_URL` override and a Compose `postgres` profile.

**Rationale**: Constitution V (zero-ops default, Postgres as documented upgrade path). SQLAlchemy + Alembic gives one model layer across both engines and real migrations. SQLite comfortably serves the ~500-repo MVP target (read-mostly, cached snapshots).

**Alternatives considered**: Raw SQL/`sqlite3` (no migrations, engine-coupled); Tortoise/Piccolo (smaller ecosystems); Postgres-by-default (violates the zero-ops default).

## 4. Background sync (poller + webhook) & scheduling

**Decision**: **APScheduler** async scheduler running an in-process **per-connection poll** on a configurable cadence, plus a **FastAPI webhook receiver** for near-real-time GitHub events. Reads are served from a **normalized cached snapshot**; poll/webhook reconcile to the most recent known state per repo. Polls use **ETag conditional requests** and a **per-connection token budget**; on provider outage the last good snapshot is served and the connection's `last_sync` marks staleness.

**Rationale**: Single-process in-stack scheduling keeps the Compose footprint to one service (Principle V) while meeting VI (webhook-driven, rate-limit-disciplined, outage-resilient). No external broker/queue needed at MVP scale.

**Alternatives considered**: Celery/RQ + Redis broker (extra containers — YAGNI at ~500 repos); cron container (coarser, no shared state); polling-only (rate-limit pressure, fails VI).

## 5. Credential encryption at rest

**Decision**: **`cryptography` Fernet (AES-128-CBC + HMAC)** envelope encryption of all provider secrets (App private key, webhook secrets, tokens) in the DB. The key comes from **`HANGAR_SECRET_KEY`** supplied via secret mount/env; Hangar refuses to start writable connections if it is absent.

**Rationale**: Principle III mandates encryption at rest with no bespoke crypto. Fernet is a vetted, misuse-resistant primitive; key-by-secret-mount fits the env/secret-driven deployment (Principle V). Key rotation is a documented re-encrypt step.

**Alternatives considered**: SQLCipher (whole-DB encryption; heavier, still needs a key); external KMS/Vault (extra infra — YAGNI for a homelab); OS keyring (not container-friendly).

## 6. Forward-auth enforcement model

**Decision**: FastAPI middleware resolves the access mode from **`HANGAR_FORWARD_AUTH`** at startup: unset → **refuse to start** with a clear message (fail-closed, FR-029); `enabled` → read identity from **`HANGAR_FORWARD_AUTH_USER_HEADER`** (default `Remote-User`; Authentik `X-authentik-username`), trusting it **only** when the request's source is within **`HANGAR_TRUSTED_PROXY_CIDR`** and/or carries a shared-secret header; optional single-identity pin (`HANGAR_FORWARD_AUTH_ALLOWED_USER`). `disabled` (network-trust) → admit all but emit a **prominent startup warning** and use the configured operator label as audit actor. Bind to the internal interface unless **`HANGAR_ALLOW_PUBLIC_BIND`** is set.

**Rationale**: Directly encodes the non-negotiable Principle III rules; everything is env-driven and testable (the required auth-mode test suite, Principle VII).

**Alternatives considered**: App-native login (forbidden by III); trusting the header unconditionally (the exact spoofing failure III exists to prevent).

## 7. Audit "actor" across access modes (from clarification)

**Decision**: The audit `actor` is **always non-null**: in forward-auth mode it is the proxy-injected identity; in disabled mode it is **`HANGAR_OPERATOR`** (default `local-operator`). Audit entries are **retained even when their connection is removed**, with connection attribution denormalized onto the entry so the immutable trail survives.

**Rationale**: Encodes Session 2026-06-21 clarifications; preserves SC-008 ("100% recorded") and Principle II's complete, immutable audit trail in every mode and after connection removal.

**Alternatives considered**: nullable actor / cascade-delete audit on connection removal (both rejected in clarification — violate audit completeness/immutability).

## 8. Remediation lifecycle & idempotency (from clarification)

**Decision**: Findings carry the four-state model the prototype already implements — `pass` / `fail` / `unknown`, plus a **`remediation pending`** overlay while a Hangar-authored PR is open (prototype `effStatus`: `working` → `pr_open`/`pending` → `fixed`). **Idempotency for PR-based corrections is keyed on an existing open Hangar-authored PR** for that `(repo, check)`; re-trigger surfaces the existing PR instead of opening a duplicate. Settings corrections are idempotent by desired-state convergence. Each correction writes one audit entry.

**Rationale**: Encodes the clarifications and FR-015/FR-005a; the prototype is the working reference for the state machine and is the binding UI behavior.

**Alternatives considered**: 3-state + "fail with PR link" (loses the in-flight signal — rejected in clarification); optimistic flip to pass on PR open (false pass — rejected).

## 9. MVP writable-correction catalog

**Decision**: At MVP the **writable** corrections are: enable Dependabot/security alerts (settings PATCH), set description/topics (settings PATCH), and **PR-based** add/update of `dependabot.yml` (incl. cooldown), `LICENSE`, `SECURITY.md`, `CODEOWNERS`, issue/PR templates, and release-automation config (`release-please`). Every other catalog check (FR-009) ships **report and/or deep-link** at MVP. This matches the prototype's per-check `action` field (`patch` / `pr` / `link` / `report`).

**Rationale**: Mirrors the spec Assumptions and the prototype's `CHECKS` data exactly, keeping the writable surface small, safe, and PR-first (Principle II).

**Alternatives considered**: Auto-correcting more checks at MVP (larger write scope, more risk — deferred).

## 10. Frontend type generation & UI fidelity

**Decision**: Generate TypeScript types from `contracts/openapi.yaml` with **`openapi-typescript`** at build time; the SPA consumes them via a thin typed client + **TanStack Query** for cached fetching. The visual system is **lifted verbatim from `docs/prototype/Hangar.dc.html`**: the `:root` CSS variables become Tailwind theme tokens; **Public Sans** (UI) + **JetBrains Mono** (numerals/IDs) typography; status-only color (`--pass/--warn/--fail/--unknown`); light/dark via the same token swap; the five screens, connection switcher, toast, and remediation controls reproduced as React components. See `contracts/ui-spec.md`.

**Rationale**: Principle VII (no hand-drifted types) + the user's explicit instruction to fully adhere to the prototype. Generating types from the contract keeps FE/BE in lockstep; pinning tokens to the prototype guarantees visual fidelity.

**Alternatives considered**: Orval/openapi-generator (heavier); hand-written types (forbidden by VII); re-designing the UI (contradicts the instruction).

## 11. Check detection heuristics (per-check, deferred to design)

**Decision**: Each check's `pass/fail/unknown` semantics are fixed by the spec; the **detection heuristic** is specified per check in `data-model.md` / the check module docstrings during implementation, using read-only provider interrogation (files of interest, settings, rulesets, workflows, org policy). A check returns **`unknown`** whenever the required capability/scope is absent or a file can't be read — never a false pass/fail.

**Rationale**: Spec Assumptions defer heuristics to design while fixing behavior; `unknown`-on-insufficient-scope is already modeled in the prototype (`effStatus`).

**Alternatives considered**: Hard-coding heuristics in the spec (rejected — premature); a rules DSL (YAGNI at MVP).
