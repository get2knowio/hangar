---
description: "Task list for Fleet Control Plane (Hangar MVP)"
---

# Tasks: Fleet Control Plane (Hangar MVP)

**Input**: Design documents from `/specs/001-fleet-control-plane/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/openapi.yaml](./contracts/openapi.yaml), [contracts/ui-spec.md](./contracts/ui-spec.md), [quickstart.md](./quickstart.md)

**Tests**: Constitution v1.0.0 **Principle VII makes specific test suites REQUIRED** (not optional): the `RepoProvider` contract per adapter, remediation idempotency + PR-not-push, forward-auth mode resolution (fail-closed + header-trust), and check evaluation. Those test tasks are marked **[REQUIRED]**. Other test tasks (broader e2e/units) are included to honor the UI-fidelity instruction.

**UI fidelity (user instruction)**: every frontend task MUST match `docs/prototype/Hangar.dc.html` (direction 02 · Clean Developer SAAS) per [contracts/ui-spec.md](./contracts/ui-spec.md). The prototype wins on any conflict.

**Organization**: Tasks grouped by user story (priority order P1→P5) for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1–US5 (user story phases only)
- Exact file paths included. Backend root `backend/src/hangar/`, frontend root `frontend/src/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Monorepo scaffold, toolchains, and the prototype design system.

- [X] T001 Create monorepo structure (`backend/`, `frontend/`, `deploy/`) per [plan.md](./plan.md) project structure
- [X] T002 Initialize backend Python 3.12 project in `backend/pyproject.toml` with FastAPI, Uvicorn, Pydantic v2, SQLAlchemy 2.x (async), Alembic, githubkit, APScheduler, cryptography, structlog, httpx, pytest, pytest-asyncio, respx
- [X] T003 [P] Initialize frontend in `frontend/` (Vite + React 18 + TypeScript, Tailwind CSS, shadcn/ui, TanStack Query, openapi-typescript, Vitest, Playwright)
- [X] T004 [P] Configure backend lint/type/format (ruff + mypy/pyright) in `backend/pyproject.toml` and frontend (eslint + prettier + tsc) in `frontend/`
- [X] T005 [P] Add CI workflow `.github/workflows/ci.yml` running backend lint+type+pytest and frontend lint+type+vitest (Constitution VII gates)
- [X] T006 [P] Lift prototype design tokens into `frontend/src/styles/tokens.css` and `frontend/tailwind.config.ts` — the `:root` light/dark CSS variables, Public Sans + JetBrains Mono fonts, status-only color (per [contracts/ui-spec.md](./contracts/ui-spec.md))
- [X] T007 [P] Wire OpenAPI type generation: script in `frontend/package.json` running `openapi-typescript ../specs/001-fleet-control-plane/contracts/openapi.yaml -o frontend/src/lib/api-types.ts` (no hand-drifted types — Constitution VII)
- [X] T008 [P] Status→glyph/color + hygiene-threshold helpers in `frontend/src/lib/status.ts` mirroring the prototype `viz`/`hygColor`

**Checkpoint**: Toolchains build; design tokens and generated types available.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Provider-neutral core, persistence, a read-only GitHub connection feeding a cached snapshot, and the app shell — everything every story needs.

**⚠️ CRITICAL**: No user-story phase can begin until this phase is complete.

### Backend core

- [X] T009 Settings/config in `backend/src/hangar/config.py` — parse all `HANGAR_*` env + secret mounts and `DATABASE_URL`; typed settings object (no enforcement logic yet — US5 adds fail-closed/bind)
- [X] T010 Persistence engine in `backend/src/hangar/persistence/db.py` — async SQLAlchemy session/engine (SQLite default, `DATABASE_URL` override) + Alembic init in `backend/alembic/`
- [X] T011 [P] Credential encryption util in `backend/src/hangar/persistence/crypto.py` — Fernet encrypt/decrypt keyed on `HANGAR_SECRET_KEY`
- [X] T012 [P] Provider-neutral domain models in `backend/src/hangar/domain/models.py` — Fleet, ProviderConnection, Repo, Check, Policy/PolicyEntry, Finding, Remediation, Capability, AuditLogEntry (per [data-model.md](./data-model.md))
- [X] T013 [P] `RepoProvider` Protocol + Capability set in `backend/src/hangar/providers/base.py` — `interrogate` / `correct` / `subscribe` + `declared_capabilities` (Constitution I)
- [X] T014 [P] Declarative check catalog (**all 23 FR-009 checks** — the prototype's 20 seed + CI-workflow-green, Actions-pinned-to-SHA, workflow-permissions-least-privilege; 5 groups; tiers `patch`/`pr`/`link`/`report`; `required_capabilities`; evidence) in `backend/src/hangar/domain/checks/` (one module per group) — data only (Constitution IV, FR-009)
- [X] T015 Policy + evaluation engine in `backend/src/hangar/domain/policy.py` — default fleet-wide policy, `effStatus`, per-repo hygiene %, fleet roll-up (mirrors prototype `buildPolicy`/`effStatus`/`hygiene`)
- [X] T016 SQLAlchemy persistence models + repositories in `backend/src/hangar/persistence/models.py` + initial Alembic migration (connections, repos, findings, remediations, audit, policy)
- [X] T017 GitHub adapter **read path** in `backend/src/hangar/providers/github/adapter.py` — githubkit App auth + `interrogate` (repos, settings, rulesets, files of interest, alerts, CI) + capability declaration + ETag conditional requests
- [X] T018 Sync service in `backend/src/hangar/services/sync.py` — APScheduler per-connection poller → normalized snapshot cache + `last_sync`; reconcile to most-recent state; per-connection token budget; **newly discovered repos in a connected scope are auto-evaluated on the next sync with zero per-repo setup (FR-034, SC-003)**
- [X] T019 FastAPI app factory in `backend/src/hangar/main.py` — `/health`, structlog structured logging, lifespan (scheduler start/stop), API router mount under `/api/v1`, error handling
- [X] T020 [REQUIRED][P] `RepoProvider` contract test suite in `backend/tests/contract/test_repoprovider_contract.py` — runnable against any adapter (Constitution VII)
- [X] T021 [REQUIRED][P] Check-evaluation unit tests in `backend/tests/unit/test_check_eval.py` — pass/fail/unknown semantics + hygiene roll-up (Constitution VII)

### Frontend shell

- [X] T022 App shell + router in `frontend/src/app/` — topbar (logo, breadcrumb), sidebar (Fleet nav + Access footer), routes for the five screens
- [X] T023 [P] Theme provider (light/dark token swap, persisted) + toast host in `frontend/src/app/` (prototype `toggleTheme`/toast)
- [X] T024 [P] Typed API client + TanStack Query provider in `frontend/src/lib/api.ts` using generated `api-types.ts`
- [X] T025 [P] Shared widgets scaffold in `frontend/src/components/` — StatTile, ConnectionBadge, HygieneBar, TierBadge, StatusGlyph (tokens-driven)
- [X] T026 `GET /api/v1/health` + `GET /api/v1/me` endpoints in `backend/src/hangar/api/system.py` (sidebar access badge + connection sync state)

**Checkpoint**: One GitHub connection syncs into a cached snapshot; shell renders with theme + nav; contract/eval tests green.

---

## Phase 3: User Story 1 - See what needs attention across the whole fleet (Priority: P1) 🎯 MVP

**Goal**: A single dashboard aggregating live signal across the fleet, urgency-sorted, with connection attribution and drill-in.

**Independent Test**: Connect one provider scope, sync, open the dashboard → all repos' live signal appears aggregated and urgency-sorted, each attributed to its connection and drillable (spec US1 Independent Test).

### Tests

- [X] T027 [P] [US1] Contract test for `GET /fleet/overview` in `backend/tests/contract/test_overview_api.py` (stats, repo rows, urgency-sorted feed, connection filter)
- [X] T028 [P] [US1] Playwright e2e `frontend/tests/e2e/overview.spec.ts` — six stat tiles, repo table with bot-PR flag + conn badge, attention feed ordering, row drill-in (matches prototype)

### Implementation

- [X] T029 [US1] Overview aggregation in `backend/src/hangar/services/overview.py` — six stat tiles, repo rows (PRs/CI/alerts/release/hygiene), attention feed sorted critical→CI→release→high-alert→bot-PRs (prototype `feed`)
- [X] T030 [US1] `GET /api/v1/fleet/overview` (with `connection` filter) in `backend/src/hangar/api/fleet.py`
- [X] T031 [P] [US1] Webhook receiver in `backend/src/hangar/services/webhooks.py` — verify signature, update snapshot on PR/CI/alert events (FR-033)
- [X] T032 [US1] Overview screen in `frontend/src/screens/Overview.tsx` — stat-tile grid, repo table (hygiene bar, conn badge, `🤖` bot flag), attention feed (left-border tone), drill-in nav
- [X] T033 [P] [US1] Connection switcher in `frontend/src/components/ConnSwitcher.tsx` (topbar) — All vs per-connection, re-scopes the view (prototype `visibleRepos`)
- [X] T034 [P] [US1] AttentionFeed + RepoTable components in `frontend/src/components/`
- [X] T035 [US1] Sidebar Overview urgency badge (CI-fail + critical-alert count) wired to live data in `frontend/src/app/Sidebar.tsx`
- [X] T036 [US1] Drill-in routing from rows/feed to `/repos/:id` (repo detail rendered minimally here; fully built in US3)

**Checkpoint**: Overview is a usable, demoable read-only MVP against a single GitHub connection.

---

## Phase 4: User Story 2 - Hygiene scorecard (Priority: P2)

**Goal**: Per-repo × per-check scorecard with evidence, a fleet roll-up figure, filters, and a data-driven catalog/policy surface.

**Independent Test**: With an active policy, evaluate a mixed-compliance fleet → correct per-check pass/fail/unknown with evidence, correct roll-up number, working filters/sorts (spec US2 Independent Test).

### Tests

- [X] T037 [P] [US2] Contract test for `GET /fleet/scorecard` in `backend/tests/contract/test_scorecard_api.py` (matrix cells, roll-up, failing-only, unknown handling)
- [X] T038 [P] [US2] Playwright e2e `frontend/tests/e2e/scorecard.spec.ts` — matrix glyphs, failing-only dimming, top-drift chips, catalog toggle recomputes

### Implementation

- [X] T039 [US2] Scorecard aggregation in `backend/src/hangar/services/scorecard.py` — matrix cells per (repo,check), fleet compliance figure, per-check pass/fail counts, top-drift (prototype `scRows`/`scRollup`)
- [X] T040 [US2] `GET /api/v1/fleet/scorecard` (`failing_only`, `connection`) in `backend/src/hangar/api/fleet.py`
- [X] T041 [P] [US2] `GET /api/v1/catalog` + `GET/PATCH /api/v1/policy` in `backend/src/hangar/api/catalog.py` — toggle check / set target; persist policy (FR-019, FR-020)
- [X] T042 [US2] Scorecard screen in `frontend/src/screens/Scorecard.tsx` — sticky repo column (hygiene%+name+conn badge), grouped check columns, per-cell glyph, legend, drill-in
- [X] T043 [P] [US2] ScorecardMatrix + FailingOnlyToggle + TopDriftChips components in `frontend/src/components/` (failing-only dims passing cells to 0.12 opacity); support filter/sort by check, repository, and connection in addition to failing-only (FR-007)
- [X] T044 [P] [US2] Catalog & policy screen in `frontend/src/screens/Catalog.tsx` — grouped checks, enable toggles, tier badges, cooldown target input, per-check pass-rate bar; edits recompute scorecard live (Constitution IV, SC-005)
- [X] T045 [US2] Sidebar Scorecard urgency badge (repos < 65% hygiene) in `frontend/src/app/Sidebar.tsx`

**Checkpoint**: Scorecard + catalog work independently; toggling a check as data recomputes compliance with no UI code change.

---

## Phase 5: User Story 3 - Fix drift in place via the remediation spectrum (Priority: P3)

**Goal**: From any finding, offer Report / Deep-link / human-triggered API correction (settings PATCH or config PR), idempotent and audit-logged; read-only connections collapse to deep-link.

**Independent Test**: Trigger an API correction → applied as a PR (content) or scoped settings change, audit-logged with connection/actor/action/timestamp/result, re-run produces no duplicate; a read-only connection offers only report+deep-link (spec US3 Independent Test).

### Tests

- [X] T046 [REQUIRED][P] [US3] Integration test remediation **idempotency** in `backend/tests/integration/test_remediation_idempotency.py` — re-trigger surfaces existing open Hangar PR, no duplicate (FR-015)
- [X] T047 [REQUIRED][P] [US3] Integration test **PR-not-push** in `backend/tests/integration/test_remediation_pr_first.py` — content corrections open a PR, never a direct/force push (FR-014); and assert idle Hangar performs **zero autonomous mutations** with no operator action (FR-017, AS-8)
- [X] T048 [REQUIRED][P] [US3] Integration test **read-only collapse** in `backend/tests/integration/test_remediation_readonly.py` — missing write scope → only report+deep-link (FR-018)
- [X] T049 [P] [US3] Playwright e2e `frontend/tests/e2e/remediation.spec.ts` — Open fix PR → working → PR open → Mark merged → pass; toast + audit entry

### Implementation

- [X] T050 [US3] GitHub adapter **correct path** in `backend/src/hangar/providers/github/adapter.py` — settings PATCH, config-file PR (open PR only), deep-link URL builder
- [X] T051 [US3] Remediation service in `backend/src/hangar/domain/remediation.py` — per-capability tier resolution, state machine working→pr_open→fixed, idempotency key (existing open Hangar PR), markMerged, deep-link recording (prototype `fire`/`deep`/`markMerged`)
- [X] T052 [P] [US3] Audit-log service in `backend/src/hangar/services/audit.py` — append-only `AuditLogEntry` (connection, actor, action, timestamp, PR/URL); actor resolution hook (FR-016)
- [X] T053 [US3] `POST /api/v1/repos/{id}/checks/{check}/remediate` in `backend/src/hangar/api/repos.py` — kinds report/deep_link/settings_patch/config_pr; 403→deep-link collapse; returns state+pr_url+audit+idempotent_hit
- [X] T054 [US3] `GET /api/v1/repos/{id}` repo-detail in `backend/src/hangar/api/repos.py` — activity strip (PRs, CI, alerts) + grouped policy checks with resolved remediation controls (prototype `buildCtl`)
- [X] T055 [US3] Repo drill-down screen in `frontend/src/screens/RepoDetail.tsx` — header (name, conn badge, read-only pill, big hygiene%), Open-PRs list (dependabot `⚙`/human `↗`), CI + Security cards, grouped checks
- [X] T056 [P] [US3] RemediationControl component in `frontend/src/components/RemediationControl.tsx` — Report only / Open in {provider} ↗ / Enable / Open fix PR → PR #n open ↗ + Mark merged; toast on action (prototype controls). Every failing finding offers ≥1 remediation path — Report always available (SC-002)
- [X] T057 [US3] Finding "remediation pending" overlay (`◐`, open-PR link) surfaced in `frontend/src/screens/Scorecard.tsx` and `frontend/src/screens/RepoDetail.tsx` (FR-005a)

**Checkpoint**: Full Report→Deep-link→API-correction spectrum works, idempotent, audit-logged, PR-first.

---

## Phase 6: User Story 4 - Run several provider connections at once (Priority: P4)

**Goal**: Multiple connections (incl. same type, and Gitea) as configuration; the fleet is their union; per-connection capabilities drive remediation tiers; removal retains audit.

**Independent Test**: Add a 2nd connection via config only → its repos merge into the fleet, attribution preserved, per-connection capability differences resolve remediation tiers — no code change/rebuild (spec US4 Independent Test).

### Tests

- [X] T058 [REQUIRED][P] [US4] `RepoProvider` contract test run against the **Gitea** adapter in `backend/tests/contract/test_gitea_contract.py` (Constitution I/VII)
- [X] T059 [P] [US4] Integration test multi-connection union + attribution + removal-retains-audit in `backend/tests/integration/test_multi_connection.py` (FR-022, FR-023, clarification)

### Implementation

- [X] T060 [US4] Connection persistence + management service in `backend/src/hangar/services/connections.py` — multiple connections (incl. same type), encrypted credentials, add/remove; removal drops repos/findings/snapshots, **retains audit (denormalized attribution)**
- [X] T061 [P] [US4] Gitea adapter stub in `backend/src/hangar/providers/gitea/adapter.py` — `interrogate` + deep-link only (read-only capabilities), behind `RepoProvider` (FR-025)
- [X] T062 [US4] Per-connection capability → tier resolution wired through findings (write tiers degrade to deep-link per connection) in `backend/src/hangar/domain/remediation.py` (FR-010)
- [X] T063 [US4] Generalize sync poller (T018) to iterate all configured connections with independent `last_sync`/budgets
- [X] T064 [US4] `GET /api/v1/providers`, `POST /api/v1/providers`, `DELETE /api/v1/providers/{id}`, `GET /api/v1/providers/audit` in `backend/src/hangar/api/providers.py`
- [X] T065 [US4] Providers & access screen in `frontend/src/screens/Providers.tsx` — access banner, connection cards (type/write pills, scope/auth/repos/remediation grid), + Add connection, audit-log table
- [X] T066 [US4] Finalize connection switcher (T033) to list all connections with write/read dots; every screen attributes items to connection (FR-023)

**Checkpoint**: Fleet is a real multi-connection union; adding/removing connections is configuration; Gitea degrades cleanly.

---

## Phase 7: User Story 5 - Reach Hangar securely through the homelab edge (Priority: P5)

**Goal**: Forward-auth enforced at the edge, fail-closed when unset, proxy-only header trust, internal bind, disabled-mode warning, credentials encrypted at rest.

**Independent Test**: Unset access mode → refuses to start; forward-auth → valid proxy header admitted, forged direct header rejected; disabled → prominent warning + refuses public bind without override (spec US5 Independent Test).

### Tests

- [X] T067 [REQUIRED][P] [US5] Auth-mode resolution tests in `backend/tests/integration/test_auth_mode.py` — unset → refuse start (fail-closed, FR-029); disabled → warning + public-bind refusal (FR-030, FR-031)
- [X] T068 [REQUIRED][P] [US5] Header-trust tests in `backend/tests/integration/test_auth_header_trust.py` — header honored only from trusted-proxy CIDR/secret; forged direct request rejected (FR-030, SC-007)
- [X] T069 [REQUIRED][P] [US5] Credential encryption-at-rest test in `backend/tests/integration/test_credential_encryption.py` — stored provider secrets are ciphertext (FR-032)

### Implementation

- [X] T070 [US5] Forward-auth middleware in `backend/src/hangar/auth/forward_auth.py` — mode resolution, configurable identity header (`HANGAR_FORWARD_AUTH_USER_HEADER`), trusted-proxy CIDR / shared-secret enforcement, optional single-identity pin (FR-027, FR-028, FR-030)
- [X] T071 [US5] Fail-closed startup gate + bind policy in `backend/src/hangar/config.py`/`main.py` — refuse to start if `HANGAR_FORWARD_AUTH` unset; disabled-mode prominent warning; internal bind unless `HANGAR_ALLOW_PUBLIC_BIND` (FR-029, FR-030, FR-031)
- [X] T072 [US5] Audit actor resolution in `backend/src/hangar/services/audit.py` — proxy identity in forward-auth, `HANGAR_OPERATOR` (default `local-operator`) in disabled mode; always non-null (clarification, FR-016)
- [X] T073 [P] [US5] Enforce credential encryption on the connection persistence path (Fernet via T011) and least-privilege scope capture per connection in `backend/src/hangar/services/connections.py` (FR-026, FR-032)
- [X] T074 [US5] Wire real access state into `frontend/src/screens/Providers.tsx` access banner + sidebar Access footer (from `/me` + `/providers.access`)

**Checkpoint**: Hangar is safe to run against real write credentials behind the homelab edge.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Deployment, resilience, observability, full UI fidelity, and end-to-end validation.

- [X] T075 [P] Deployment stack `deploy/docker-compose.yml` — single stack, Traefik routing+TLS+`ForwardAuth` labels, `homepage.*` tile + `hola-*` fleet metadata, internal-network bind, optional `postgres` profile (Constitution V)
- [X] T076 [P] Multi-stage `deploy/Dockerfile` (build SPA → serve static via FastAPI) + `deploy/.env.example` documenting all `HANGAR_*` vars + secret mounts
- [X] T077 [P] `README.md` stand-up-from-scratch guide — a stranger stands Hangar up against their own providers (SC-006, Principle V)
- [X] T078 Resilience: serve last good cached snapshot during provider outage + visible staleness via `last_sync` (FR-035, FR-036, SC-009) in `backend/src/hangar/services/sync.py`
- [X] T079 Rate-limit discipline in `backend/src/hangar/providers/github/adapter.py` + `backend/src/hangar/services/sync.py` — ETag conditional + per-connection token budget; assert no live-API bursts on page load (FR-037, SC-010)
- [X] T080 [P] Observability polish — structured logs across remediation/auth/sync; `/health` reports per-connection sync state (FR-038, Constitution VI)
- [X] T081 [P] Dark-theme parity pass across `frontend/src/screens/` (all five) + empty-fleet "add a connection" state in `frontend/src/screens/Overview.tsx` (Edge Cases, UI fidelity in both themes)
- [X] T082 [P] Full Playwright prototype-flow e2e in `frontend/tests/e2e/fidelity.spec.ts` — quickstart scenarios B–F, H (UI fidelity vs `docs/prototype`)
- [X] T083 [P] Frontend unit tests in `frontend/tests/unit/` — status/hygiene helpers, urgency sort, tier resolution
- [X] T084 Performance check in `backend/tests/integration/test_overview_perf.py` — cached dashboard usable < 5s for a ~500-repo fleet (SC-001)
- [X] T085 Run [quickstart.md](./quickstart.md) validation end-to-end (all scenarios A–H) and fix gaps

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — start immediately.
- **Foundational (Phase 2)**: depends on Setup — **BLOCKS all user stories**.
- **User Stories (Phases 3–7)**: all depend on Foundational. Recommended in priority order P1→P5; US1 and US2 (read-only) can proceed in parallel once Foundational is done. US3 depends on US1/US2 findings; US4 generalizes US1–US3 to many connections; US5 is independently testable but should precede any run against real write creds.
- **Polish (Phase 8)**: depends on the user stories it touches.

### User Story Dependencies

- **US1 (P1)**: Foundational only. MVP.
- **US2 (P2)**: Foundational only (uses the policy engine from Foundational). Independent of US1.
- **US3 (P3)**: builds on findings (US2) + signal (US1); needs the GitHub correct-path.
- **US4 (P4)**: generalizes connection handling; integrates US1–US3 but each remains independently testable.
- **US5 (P5)**: independent; enabling slice for safe deployment.

### Within Each Story

- Tests (REQUIRED ones especially) before/alongside implementation; verify they fail first.
- Backend models → services → endpoints → frontend screen → wiring.

### Parallel Opportunities

- Setup: T003–T008 in parallel.
- Foundational: T011–T014, T020–T021, T023–T025 in parallel (distinct files).
- Each story's `[P]` tests run together; `[P]` components/services in distinct files run together.
- With staff: once Foundational is done, US1 and US2 proceed concurrently.

---

## Parallel Example: User Story 1

```bash
# Tests together:
Task: "Contract test for GET /fleet/overview in backend/tests/contract/test_overview_api.py"   # T027
Task: "Playwright e2e overview in frontend/tests/e2e/overview.spec.ts"                          # T028

# Independent components together:
Task: "Connection switcher in frontend/src/components/ConnSwitcher.tsx"                          # T033
Task: "AttentionFeed + RepoTable components in frontend/src/components/"                         # T034
Task: "Webhook receiver in backend/src/hangar/services/webhooks.py"                              # T031
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup → 2. Phase 2 Foundational (CRITICAL) → 3. Phase 3 US1 → **STOP & VALIDATE** the overview against a single GitHub connection → demo. This is the read-only aggregated dashboard, already standalone value.

### Incremental Delivery

Foundation → US1 (MVP, overview) → US2 (scorecard + catalog) → US3 (remediation) → US4 (multi-connection) → US5 (secure edge) → Polish (deploy/resilience/fidelity). Each story is an independently testable, demoable increment.

### Parallel Team Strategy

After Foundational: Dev A → US1, Dev B → US2 (both read-only, independent); then US3 (needs A+B), US4, US5 distributed. US5 can be built in parallel throughout since it touches the auth/config seam.

---

## Notes

- `[P]` = different files, no incomplete-task dependency. `[REQUIRED]` = Constitution VII mandates the test.
- Constitution non-waivable gates pinned by tests: II (PR-first/idempotent — T046/T047/T048) and III (fail-closed/header-trust — T067/T068/T069).
- Every frontend task is bound to `docs/prototype/` via [contracts/ui-spec.md](./contracts/ui-spec.md); the prototype wins on conflict.
- Commit after each task or logical group. Stop at any checkpoint to validate a story independently.
