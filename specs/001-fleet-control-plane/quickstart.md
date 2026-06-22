# Quickstart & Validation: Fleet Control Plane (Hangar MVP)

A runnable guide to stand Hangar up and validate the feature end-to-end against the spec's acceptance scenarios and the `docs/prototype` UI. Implementation detail lives in `tasks.md`; data shapes in [data-model.md](./data-model.md); API in [contracts/openapi.yaml](./contracts/openapi.yaml); UI fidelity in [contracts/ui-spec.md](./contracts/ui-spec.md).

## Prerequisites

- Docker + Docker Compose, or local toolchains: Python 3.12 + `uv`/`pip`, Node 20 + `pnpm`.
- A GitHub App (App id + private key + webhook secret) installed on the org/user you want to watch. (Gitea scoped token optional, read-only.)
- A reverse proxy doing forward-auth (Traefik + Authentik reference) for production-like runs; for local dev you may use `HANGAR_FORWARD_AUTH=disabled`.

## Required configuration (env / secrets)

Copy `deploy/.env.example` → `.env` and set at minimum:

```bash
HANGAR_FORWARD_AUTH=enabled            # or "disabled" — MUST be set or Hangar refuses to start (FR-029)
HANGAR_FORWARD_AUTH_USER_HEADER=Remote-User   # Authentik: X-authentik-username
HANGAR_TRUSTED_PROXY_CIDR=172.16.0.0/12       # header trusted only from the proxy (FR-030)
HANGAR_SECRET_KEY=<fernet-key>          # encrypts provider credentials at rest (FR-032)
HANGAR_OPERATOR=local-operator          # audit actor in disabled mode (clarification)
# HANGAR_ALLOW_PUBLIC_BIND=1            # only to bind a non-private interface (FR-030)
# DATABASE_URL=postgresql+asyncpg://... # optional; default is SQLite
```

## Run

```bash
# Single-stack (production-like)
docker compose -f deploy/docker-compose.yml up --build

# Local dev
cd backend && uvicorn hangar.main:app --reload      # API on :8000
cd frontend && pnpm install && pnpm dev              # SPA on :5173 (proxies /api → :8000)
```

Open the SPA; add a GitHub connection on **Providers**; let the first sync run.

## Validation scenarios (map to spec acceptance criteria)

> Each block is independently runnable. ✅ = expected outcome.

### A. Fail-closed access (FR-029, SC-007 · Story 5)
1. Unset `HANGAR_FORWARD_AUTH`, start. ✅ Process refuses to start with a message telling you to choose an access mode.
2. Set `enabled`, behind the proxy, request with the configured header. ✅ Admitted; `/api/v1/me` shows the proxy identity.
3. Hit the API **directly** (not via proxy) with a forged `Remote-User`. ✅ Rejected (header trusted only from `HANGAR_TRUSTED_PROXY_CIDR`).
4. Set `disabled`, start. ✅ Prominent startup warning; refuses to bind a public interface without `HANGAR_ALLOW_PUBLIC_BIND`.

### B. Fleet overview (FR-001–FR-004 · Story 1)
1. With a synced connection, open **Overview**. ✅ Six stat tiles, repo table, and attention feed render aggregated and urgency-sorted; bot PRs flagged `🤖`; every row shows its connection badge; matches the prototype layout.
2. Switch the connection filter to one connection. ✅ Stats, table, and feed re-scope to that connection.
3. Click a row / feed item. ✅ Drills into the repo with its originating connection visible.

### C. Hygiene scorecard (FR-005–FR-007 · Story 2)
1. Open **Scorecard**. ✅ Per-repo × per-check matrix with pass `●` / fail `✕` / unknown `○`; sticky repo column with hygiene %; group headers.
2. A check that can't be determined (scope/file). ✅ Shows `unknown` with explanation, not a false pass/fail.
3. Toggle **Failing only**. ✅ Passing cells dim; top-drift chips reflect worst checks. Roll-up shows one compliance figure + per-check counts.

### D. Check catalog & policy (FR-008, FR-009, FR-019, FR-020 · Constitution IV)
1. Open **Catalog**. ✅ All 23 FR-009 checks grouped, each with tier badge + id + pass-rate bar.
2. Toggle a check off / change the cooldown target. ✅ Scorecard + hygiene recompute live with **no dashboard code change** (SC-005).

### E. Remediation spectrum (FR-011–FR-018, SC-008 · Story 3)
1. Open a repo, find a failing **PR-tier** check (e.g. LICENSE). Click **Open fix PR**. ✅ State → `working…` → `PR #n open`; a real PR is opened (never a push/force-push); toast + audit entry recorded.
2. Re-trigger the same correction. ✅ Idempotent — the existing open PR is surfaced, no duplicate (FR-015).
3. **Mark merged** (or merge upstream + re-sync). ✅ Finding flips to pass; audit records the merge.
4. A failing **settings-tier** check (e.g. enable Dependabot). Click **Enable**. ✅ Scoped settings change applied + audited.
5. A finding on a **read-only** connection. ✅ Only Report + Deep-link offered; write tier hidden (FR-018).
6. Idle Hangar. ✅ No repository is ever mutated without an explicit click (FR-017, AS-8).

### F. Multi-connection (FR-021–FR-026, SC-004 · Story 4)
1. Add a second connection (a second GitHub org and/or a Gitea token) via **Providers** — config only. ✅ Its repos merge into the unified fleet; all items stay attributed; no code change/rebuild.
2. Remove a connection. ✅ Its repos/findings/snapshots leave the fleet view; its **audit-log entries remain** (clarification).

### G. Resilience & freshness (FR-035–FR-038, SC-009, SC-010 · Constitution VI)
1. Simulate a provider outage (block the API). ✅ Overview/Scorecard still render the last good snapshot; the connection's `last_sync` shows staleness.
2. Watch provider call volume while clicking around. ✅ No bursts of live API calls on page load (reads hit the cache); `GET /api/v1/health` returns connection sync state.

### H. UI fidelity (user instruction · [ui-spec.md](./contracts/ui-spec.md))
1. Compare each screen against `docs/prototype/Hangar.dc.html` and the screenshots in **both** light and dark themes. ✅ Tokens, fonts (Public Sans + JetBrains Mono), status-only color, layout, copy, and interactions match.

## Automated test entry points (Constitution VII)

```bash
cd backend && pytest          # provider-contract, remediation idempotency/PR-not-push, auth-mode, check-eval suites
cd frontend && pnpm test      # Vitest units
cd frontend && pnpm e2e       # Playwright — the prototype flows (scenarios B–F, H)
```

## Stand-up-from-README check (SC-006)

A second person should reach a working instance using `README.md` alone. If any step here isn't in the README, that's a bug against Principle V.
