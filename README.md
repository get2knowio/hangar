# Hangar

**Hangar** is a self-hosted, single-operator *fleet control plane* for your repositories.
It aggregates every repo across one or more provider connections (GitHub today, Gitea
designed-for) into one dashboard, scores each repo against a declarative best-practice
**policy**, and lets you remediate hygiene drift in place — every content change delivered
as a **pull request, never a push**.

It is provider-agnostic at its core, fail-closed behind a reverse-proxy SSO layer, and
built to run as a single Docker Compose stack on a modest homelab host.

> **Just want to run it?** → [**CONTRIBUTING.md**](CONTRIBUTING.md) has quickstart, the full
> configuration reference, GitHub-App / Gitea setup, access modes, and deployment.

---

## Why Hangar

A maintainer running a portfolio of repos has no standing, fleet-level answer to two
recurring questions:

1. **What needs my attention right now?** Open PRs piling up, dependency-bot PRs waiting to
   merge, failing CI on `main`, security alerts by severity, repos with unreleased commits
   sitting too long. Today that's *N* browser tabs and tribal memory.
2. **Is the fleet configured the way I want it to be?** Is Dependabot on everywhere? Is the
   update cooldown set? Is release-please wired up? Is branch protection on `main`? Is there
   a LICENSE, a SECURITY.md, CODEOWNERS? These best practices are decided once and then
   **drift silently** as repos are created and forgotten.

You can answer (2) for a *moment in time* with a one-shot script that configures cooldowns
and Dependabot across an org. That's the right *action* but the wrong *lifecycle*: a one-shot
run doesn't persist, doesn't re-check, and doesn't catch the next repo. **Hangar turns that
one-shot into a standing control plane** — continuous visibility, a declarative definition of
"good," and a path to fix what's drifted.

### What Hangar is *not*

- **Not a hosted SaaS.** Single-operator, self-hosted only — no multi-tenancy, no sign-up.
- **Not an autonomous agent.** Hangar never silently mutates a repo; every correction is
  operator-triggered, and every code change ships as a pull request.
- **Not an identity provider.** Access is delegated to your homelab edge (forward-auth) or an
  OIDC IdP — Hangar never treats a git provider as its login.
- **Not a CI system, code-review tool, or secrets vault.** It *observes and nudges*; it
  doesn't replace the platform's own primitives.

---

## How it works

```
 connect a provider ──▶ poll & interrogate ──▶ score against policy ──▶ remediate (PR-first)
 (GitHub App / token)   (background, cached,    (23-check catalog,       (operator-triggered,
                         ETag-conditional)       pass/fail/unknown)        audit-logged)
```

- **Reads never hit the provider live.** A background poller interrogates each repo with
  conditional (ETag) requests and stores a normalized snapshot; page loads read the cache and
  evaluate the catalog. A poll that finds nothing changed costs no API quota.
- **Every connection is scoped and attributed.** Repos, findings, and remediations always
  carry their originating provider connection — two same-named repos across connections never
  collide.
- **Honest state.** A signal Hangar can't determine (missing scope, or a platform that has no
  equivalent) is reported as `unknown` — never a fabricated pass or fail.

The **core concepts** are deliberately platform-neutral so GitHub and Gitea map onto the same
vocabulary: a **Fleet** is the union of watched repos; a **Provider connection** is one
configured credential + scope; a **Check** is one evaluable rule; a **Policy** is an ordered
set of checks; a **Finding** is one check evaluated against one repo; a **Remediation** is the
action that resolves it.

---

## What Hangar validates — the check catalog

Hangar evaluates a fleet-wide **policy** of **23 checks**, grouped into five areas. Each check
declares a **remediation tier** — how far Hangar can go toward fixing it — evaluated *per
connection*, since a provider may support auto-correction on one platform and only a deep-link
on another:

| Tier | Badge | What Hangar does |
|------|-------|------------------|
| **Report** | `Report` | Surfaces the finding and its evidence. No action to take on Hangar's side. |
| **Deep-link** | `Deep-link` | Sends you straight to the exact settings page to fix it — used when Hangar can't safely synthesize the change. |
| **PR** | `API · PR` | Opens a fix **pull request** (adds a config/file). Human-triggered, idempotent, never a push. |
| **API** | `API` | Applies a **scoped settings change** via the provider API (e.g. toggling a repo setting). |

Write tiers always **degrade gracefully**: a check whose native tier is PR or API collapses to
deep-link, then report, when a connection lacks the capability (a read-only connection, or a
platform without that setting).

### Supply chain
| Check | Tier | Passes when |
|-------|------|-------------|
| **Dependabot alerts enabled** | `API` | Vulnerability alerts are turned on for the repo. |
| **Version updates configured** | `API · PR` | A **Dependabot** (`.github/dependabot.yml`) *or* **Renovate** (`renovate.json`, `.renovaterc`, …) update config is present. |
| **Update cooldown ≥ target** | `API · PR` | An update cooldown is configured to the target (default **7 days**) — Dependabot `cooldown` or Renovate `minimumReleaseAge`. |
| **Lockfile present** | `Report` | A dependency lockfile is committed. |
| **Dependency review enabled** | `Deep-link` | The dependency-review action is wired into CI. |
| **Actions pinned to SHA** | `Deep-link` | Workflows pin actions to immutable commit SHAs, not mutable tags. |

### Release
| Check | Tier | Passes when |
|-------|------|-------------|
| **release-please configured** | `API · PR` | A release-please manifest/config is present. |
| **Conventional commits enforced** | `Deep-link` | A commitlint config or PR-title-lint workflow enforces conventional commits. |
| **CHANGELOG automated** | `Report` | A CHANGELOG / automated release notes exist. |
| **Release health / commit age** | `Report` | The latest release isn't lagging too far behind `main`. |
| **CI workflow green on default** | `Report` | Default-branch CI is configured and passing. |

### Governance
| Check | Tier | Passes when |
|-------|------|-------------|
| **Branch protection on default** | `Deep-link` | A protection ruleset guards the default branch. |
| **CODEOWNERS present** | `API · PR` | A CODEOWNERS file exists. |
| **Default branch = main** | `Report` | The default branch is `main`. |

### Security
| Check | Tier | Passes when |
|-------|------|-------------|
| **SECURITY.md present** | `API · PR` | A SECURITY.md policy exists. |
| **Secret scanning + push protection** | `Deep-link` | Secret scanning and push protection are enabled. |
| **Code scanning (CodeQL)** | `Deep-link` | A CodeQL / code-scanning workflow is configured. |
| **Org 2FA required** | `Deep-link` | The owning org enforces two-factor auth. |
| **Workflow permissions least-privilege** | `Deep-link` | `GITHUB_TOKEN` isn't left at write-all; a least-privilege permissions block is set. |

### Project meta
| Check | Tier | Passes when |
|-------|------|-------------|
| **LICENSE present** | `API · PR` | A LICENSE file is at the repo root. |
| **README present** | `Report` | A README exists. |
| **Description & topics set** | `Deep-link` | The repo has a description and topics. |
| **Issue / PR templates** | `API · PR` | `.github/ISSUE_TEMPLATE` (and/or PR template) exists. |

> **Checks are data.** The catalog lives in `backend/src/hangar/domain/checks/` — adding or
> changing a rule is a data edit there, never dashboard code. **Detection** (which repos
> pass / fail / unknown) is done by the provider adapters from read-only interrogation.

---

## Repo-level overrides — `.hangar.json`

Not every check applies to every repo, and a deliberate gap shouldn't drag a repo's score
forever. A watched repo can carry a `.hangar.json` at the **root of its default branch** to
tell Hangar how to treat it. Today it supports one thing: **ignoring checks** the repo
intentionally doesn't satisfy.

```json
{
  "version": 1,
  "ignore": [
    { "check": "dependabot_alerts", "reason": "Internal tool, no external deps" },
    "code_scanning"
  ]
}
```

- Each `ignore` entry is either an object `{ "check": "<id>", "reason": "<optional>" }` or a
  bare `"<id>"` string. `check` must be a catalog check **id** (the `id="…"` in the catalog,
  e.g. `dependabot_alerts`, `cooldown`, `branch_protection`); unknown ids are ignored.
- A suppressed check is shown **honestly** — it renders as `⊘ Suppressed` (with your reason as
  its evidence), offers no remediation, and is **excluded from the score denominator**: it
  neither passes nor fails, so the repo is neither penalized *nor* credited for it. Repo detail
  reads e.g. `18/20 scored · 2 suppressed`.
- Reading the file needs the connection's **file-read** capability; a connection without it
  simply sees no suppressions (nothing is guessed). Malformed JSON is ignored safely — the repo
  is still interrogated. Suppressions are picked up on the **next sync** after you commit the
  file, and the check is re-scored when you remove it.

This keeps the score meaningful: it reflects the checks you've actually decided *should* apply
to a given repo, per repo, in version control — not a blanket global waiver.

---

## Providers

- **GitHub** — the live adapter. Connect in two clicks with the built-in **Connect with
  GitHub** flow (Hangar creates *your own* least-privilege GitHub App — no tokens to paste),
  or bring your own App / PAT. GitHub Enterprise (GHES and GHEC data-residency) is supported.
- **Gitea** — a first-class provider; because Gitea's REST API is GitHub-shaped, the same
  23-check catalog, scorecard, and PR-first remediation apply. Signals OSS Gitea has no
  equivalent for (alerts, secret/code scanning, workflow-permissions, org 2FA) honestly report
  `unknown` rather than a fabricated result.

Setup for both — including least-privilege scopes, webhooks, and Enterprise hosts — is in
[**CONTRIBUTING.md**](CONTRIBUTING.md#github-app-setup).

---

## Security posture

- **Fail-closed by default.** Hangar refuses to start unless an access mode is chosen; webhook
  receivers refuse deliveries when no HMAC secret is set; credential paths refuse to act
  anonymously or half-configured.
- **Identity is decoupled from your provider credentials.** Access is enforced at the homelab
  edge via **forward-auth** (Traefik + Authentik reference) or by Hangar acting as an **OIDC**
  client against your own IdP. A git provider is never the login.
- **Least-privilege, encrypted at rest.** Write scopes are requested only for writable
  connections; stored credentials (App keys, tokens, webhook secrets) are Fernet-encrypted with
  `HANGAR_SECRET_KEY`.
- **Remediation is PR-first.** Content changes are always pull requests — Hangar never pushes
  or force-pushes — and every correction is operator-triggered and written to an audit log.

Details and configuration: [**CONTRIBUTING.md → Choosing an access mode**](CONTRIBUTING.md#choosing-an-access-mode).

---

## Documentation

- [**CONTRIBUTING.md**](CONTRIBUTING.md) — run, configure, develop, and deploy Hangar.
- Design & scope under [`specs/001-fleet-control-plane/`](specs/001-fleet-control-plane/):
  [spec](specs/001-fleet-control-plane/spec.md) ·
  [plan](specs/001-fleet-control-plane/plan.md) ·
  [research](specs/001-fleet-control-plane/research.md) ·
  [data model](specs/001-fleet-control-plane/data-model.md) ·
  [OpenAPI contract](specs/001-fleet-control-plane/contracts/openapi.yaml) ·
  [UI contract](specs/001-fleet-control-plane/contracts/ui-spec.md) ·
  [quickstart](specs/001-fleet-control-plane/quickstart.md).
- [Product requirements](prd.md) · Governance: [constitution](.specify/memory/constitution.md).

---

## License

See repository for license details.
