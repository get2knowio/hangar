# Phase 1 Data Model: Fleet Control Plane (Hangar MVP)

Entities derive from the spec's **Key Entities**, the Session 2026-06-21 clarifications, and the working prototype (`docs/prototype/Hangar.dc.html`). Validation rules cite the FR they enforce. Domain models are provider-neutral (Constitution I); persistence is SQLAlchemy on SQLite/Postgres.

## Entity overview & relationships

```text
ProviderConnection 1───* Repo 1───* Finding *───1 Check
        │                  │                         │
        │                  └──* PullRequestSnapshot   └──(belongs to) Policy (via PolicyEntry)
        │                  └──* AlertSnapshot
        └──* AuditLogEntry (retained after connection removal; attribution denormalized)
Capability *───* Check (a Check requires capabilities; a Connection declares capabilities)
Remediation 1───1 Finding (current in-flight/applied correction)
```

## Provider

The adapter *type* (not a stored row at MVP — a registered code unit). Declares the set of **Capabilities** it can support.

- `id`: `github` | `gitea`
- `declared_capabilities`: set of Capability ids it *can* offer (a connection may hold a subset based on granted scopes)
- Implements `RepoProvider`: `interrogate(repo) → snapshot`, `correct(repo, remediation) → result`, `subscribe(events)` (Constitution I)

## Capability

Provider-declared ability a Check references to resolve its remediation tier per connection (FR-010).

- `id`: e.g. `read_settings`, `read_files`, `read_alerts`, `read_org_policy`, `write_settings`, `open_pull_request`, `deep_link`, `subscribe_webhooks`
- A **Check** lists `required_capabilities` for each tier; a **Connection** has `granted_capabilities` (capped by its scopes). Tier resolves to the highest the connection supports, else degrades (write → deep-link → report).

## ProviderConnection

A configured instance of a provider (FR-021–FR-026). The unit of attribution.

| Field | Type | Notes / Validation |
|-------|------|--------------------|
| `id` | str (slug) | e.g. `gh-main`, `gh-labs`, `gitea` |
| `label` | str | e.g. `gh:get2knowio` (prototype `label`) |
| `provider_type` | enum `github`\|`gitea` | FR-025 |
| `scope` | str | org / user / explicit allowlist (e.g. `org · 9 repos`) |
| `auth_mode` | str | `GitHub App #4471`, `Scoped token` (prototype `mode`) |
| `credential_ref` | encrypted blob | App key / token / webhook secret — **encrypted at rest** (FR-032); Fernet |
| `granted_capabilities` | set[Capability] | drives per-connection remediation tiers (FR-010, FR-026) |
| `writes` | bool (derived) | `write_settings`/`open_pull_request` granted → read+write, else read-only/deep-link (FR-018, FR-026) |
| `last_sync_at` | datetime | visible staleness indicator (FR-036) |
| `created_at` | datetime | |

- **Invariant**: multiple connections may coexist, incl. multiple of the same `provider_type` (FR-022).
- **Removal**: deletes the connection's Repos, Findings, and cached snapshots from the fleet view; **retains its AuditLogEntries** (clarification; see below).

## Repo

A watched repository with a normalized snapshot (FR-001, FR-034).

| Field | Type | Notes |
|-------|------|-------|
| `id` | str | repo name/slug (prototype `id`, e.g. `hangar`) |
| `connection_id` | FK → ProviderConnection | attribution (FR-023) |
| `description` | str | prototype `desc` |
| `default_branch` | str | |
| `open_prs` | int | dashboard signal |
| `dependabot_prs` | int | bot-PR flag (FR-002) |
| `ci_status` | enum `pass`\|`fail`\|`none` | default-branch CI |
| `alerts` | `{critical,high,moderate,low: int}` | security/dependency alerts by severity |
| `release_pending_days` | int \| null | unreleased-commit age vs threshold |
| `snapshot_settings` | json | settings/rulesets/files of interest used by checks |
| `last_evaluated_at` | datetime | |

- A repo discovered in a connected scope is auto-evaluated on the next sync, zero per-repo setup (FR-034, SC-003).
- Same logical repo via two connections → two Repo rows, each attributed and evaluated independently (Edge Cases).

## Check

A declarative best-practice rule (FR-008) — **data, not UI** (Constitution IV). MVP catalog of **23** (the full FR-009 set), grouped: Supply chain, Release, Governance, Security, Project meta. (The `docs/prototype` seeds 20 illustratively; the 3 additions — CI-workflow-green, Actions-pinned-to-SHA, workflow-permissions-least-privilege — are added as data definitions, not UI.)

| Field | Type | Notes |
|-------|------|-------|
| `id` | str | e.g. `cooldown`, `license`, `branch_protection` (prototype `CHECKS[].id`) |
| `label` | str | human label |
| `group` | enum (5 groups) | |
| `detection` | fn ref | how pass/fail/unknown is determined (heuristic per research.md §11) |
| `remediation_tier` | enum `patch`\|`pr`\|`link`\|`report` | prototype `action`; resolves per connection via capabilities (FR-010) |
| `required_capabilities` | set[Capability] | gate for each tier |
| `has_target` | bool | e.g. `cooldown` (target days) |

## Policy & PolicyEntry

One editable, fleet-wide policy at MVP (FR-019); representation future-proofed for multi-policy (FR-020).

- **Policy**: `id`, `name`, `entries: list[PolicyEntry]`. (MVP: exactly one, fleet-wide.)
- **PolicyEntry**: `{check_id, params (e.g. {target: 7}), severity}` — serializable (FR-019). `enabled` toggles a check in/out of the active policy (prototype `policy[id].enabled`).
- **Future (additive, not built)**: `assignment` (by language/topic/tag/repo-set) + precedence/merge — schema leaves room; not implemented at MVP (FR-020).

## Finding

Result of evaluating one Check against one Repo (FR-005, FR-005a).

| Field | Type | Notes |
|-------|------|-------|
| `repo_id` + `check_id` | composite key | one per (repo, enabled check) |
| `connection_id` | FK | attribution (FR-023) |
| `status` | enum `pass`\|`fail`\|`unknown` | FR-005; `unknown` = scope/read insufficient, never false pass/fail (FR-005, Edge Cases) |
| `remediation_pending` | bool (overlay) | true while a Hangar-authored PR for this check is open (FR-005a) |
| `evidence` | str | supporting evidence (prototype `EVID`) |
| `available_remediations` | list[tier] | resolved per connection (FR-010, FR-018) |
| `open_pr_url` | str \| null | link when `remediation_pending` (FR-005a) |

**Effective-status rule** (prototype `effStatus`): if a Remediation exists → `working` (submitting) / `pending` (PR open) / `pass` (fixed); else `fail` if check fails, `unknown` if unknown, else `pass`. **Hygiene %** = passing enabled checks ÷ enabled checks (prototype `hygiene`); color: ≥85 pass, ≥65 warn, else fail.

## Remediation

An action that resolves a Finding (FR-011–FR-018). State machine (prototype `remediations`):

```text
                 fire() [writable]                      markMerged()/re-eval
none ── trigger ──▶ working ──(settings)──▶ fixed (pass)
                       │
                       └──(pr)──▶ pr_open (remediation pending) ──▶ fixed (pass)
none ── trigger ──▶ deep-link (read-only or link tier) ──▶ (external)
```

| Field | Type | Notes |
|-------|------|-------|
| `repo_id` + `check_id` | key | |
| `kind` | enum `report`\|`deep_link`\|`settings_patch`\|`config_pr` | FR-011–FR-013 |
| `state` | enum `working`\|`pr_open`\|`fixed` | |
| `pr_url` | str \| null | for `config_pr` (FR-014: PR only, never push/force-push) |
| `idempotency_key` | str | `(repo,check)` + open-Hangar-PR existence (FR-015) |

- **Invariants**: operator-initiated only, never autonomous (FR-017, AS-8); content changes via PR only (FR-014); idempotent re-trigger surfaces the existing open PR (FR-015); missing write scope → only report+deep-link offered (FR-018).

## AuditLogEntry

Immutable record of one API correction (FR-016). **Append-only.**

| Field | Type | Notes |
|-------|------|-------|
| `id` | str | |
| `timestamp` | datetime | prototype `t` |
| `connection_label` | str (denormalized) | retained after connection removal (clarification) |
| `actor` | str | **always non-null**: proxy identity (forward-auth) or `HANGAR_OPERATOR` (disabled) (clarification) |
| `repo_id` | str | |
| `check_label` | str | prototype `check` |
| `action`/`result` | str | e.g. `PR #143 opened`, `Settings applied`, `PR merged`, `Opened in GitHub` |
| `pr_url` | str \| null | resulting PR/URL (FR-016) |

- **Retention**: survives connection removal with attribution denormalized (clarification). Never updated or deleted (immutable, Constitution II).

## Fleet (derived)

The union of all Repos across all connections, optionally filtered by active connection (prototype `visibleRepos`). Roll-ups: fleet compliance figure + per-check passing/failing counts (FR-006); "Top drift" = checks with most failures (prototype `scRollup`).

## Access configuration (not persisted — env/secret at startup)

`HANGAR_FORWARD_AUTH` (enabled|disabled, **required** or fail-closed — FR-029), `HANGAR_FORWARD_AUTH_USER_HEADER` (default `Remote-User`), `HANGAR_FORWARD_AUTH_ALLOWED_USER` (optional pin), `HANGAR_TRUSTED_PROXY_CIDR`, `HANGAR_ALLOW_PUBLIC_BIND`, `HANGAR_OPERATOR`, `HANGAR_SECRET_KEY`, `DATABASE_URL` (optional Postgres). Resolved and validated at startup (FR-027–FR-032).
