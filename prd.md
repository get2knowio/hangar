---
type: project-note
project: hangar
status: draft
updated: 2026-06-19
tags: [hangar, prd, homelab, github, gitea, supply-chain, devex]
---

# Hangar — Product Requirements Document

> **Working name:** *Hangar* (the place the fleet is housed and serviced). Alternates worth a look: *Marshal* (directs and orders the fleet — leans into enforcement) and *Preflight* (a preflight checklist is literally a hygiene checklist — leans into the checks). Provisional; rename freely.

A self-hosted control plane that gives a repo owner a single standing view across a fleet of repositories — spanning one or more connected providers — surfacing both the *live* activity that needs attention (issues, PRs, releases, dependency/security alerts) and the *hygiene* posture of each repo against a defined best-practice policy, and letting them remediate drift in place, from report through deep-link through scoped API corrections.

---

## 1. Problem

A maintainer running a portfolio of repos (your `get2knowio` org is the motivating case) has no standing, fleet-level answer to two recurring questions:

1. **What needs my attention right now?** Open PRs piling up, Dependabot PRs waiting to merge, failing CI on main, security alerts by severity, repos with unreleased commits sitting too long. Today this is N browser tabs and tribal memory.
2. **Is the fleet configured the way I want it to be?** Is Dependabot on everywhere? Is the 7-day cooldown set? Is release-please wired up? Are conventional commits enforced? Is branch protection on `main`? A LICENSE present? These best practices are decided once and then *drift* silently as repos are created and forgotten.

You recently answered (2) for a moment in time with a one-shot Claude Code prompt that configured cooldowns and Dependabot across the org. That's the right *action* but the wrong *lifecycle*: a one-shot run doesn't persist, doesn't re-check, and doesn't catch the next repo. Hangar turns that one-shot into a standing control plane: continuous visibility, a declarative definition of "good," and a path to fix what's drifted.

## 2. Goals & non-goals

**Goals**
- One screen that answers "what needs attention across the fleet" with zero clicks of setup per repo after onboarding.
- A declarative best-practice policy evaluated against every repo, producing a per-repo and fleet-wide hygiene scorecard.
- A remediation spectrum: **report** the finding, **deep-link** straight to the exact place to fix it, or perform a **scoped API correction** on the owner's behalf (always human-triggered, code changes always via PR).
- Provider-agnostic core that holds *multiple provider connections at once*: GitHub at MVP, Gitea as a fast follower, with the seam designed in from the start and no platform privileged over another.
- Deploys as a single Docker Compose stack into a homelab, hola-style (behind Traefik, with `homepage.*` tiles), runnable by any admin against their own providers.

**Non-goals (at least for MVP)**
- Not a hosted SaaS. Single-operator, self-hosted only. No multi-tenant isolation, no public sign-up.
- Not an autonomous agent. Hangar never silently mutates repos; every correction is initiated by the operator.
- Not an identity provider. Hangar does not implement its own platform login; access is delegated to the homelab edge (see §7).
- Not a CI system, not a code-review tool, not a secrets vault. It *observes and nudges*; it doesn't replace the platform's own primitives.

## 3. Target user & deployment context

A single owner/admin running Hangar in their own homelab, watching repositories across one or more connected providers. **Access to Hangar is enforced at the homelab layer, not by the app** — the reverse proxy / SSO / network boundary that already fronts the homelab decides who gets in. Hangar never treats any one provider (GitHub included) as its identity gate, because a given instance may have several providers connected at once: multiple GitHub orgs, a Gitea instance, or any mix. The product is open-sourced under the get2know brand and documented well enough that a stranger can stand it up against their own providers — but it assumes one trusted operator, a private network (Tailscale / Traefik-fronted), and a homelab footprint (one Compose stack, modest resources).

## 4. Core concepts (provider-neutral domain model)

These names are deliberately platform-agnostic so the GitHub and Gitea adapters map onto the same vocabulary:

- **Fleet** — the union of repositories Hangar watches across *all* connected providers. Each connection contributes a scope (an org, a user, or an explicit allowlist).
- **Provider** — an adapter *type* (e.g. `github`, `gitea`) implementing the `RepoProvider` interface (read interrogation + scoped corrections + event subscription).
- **Provider connection** — a *configured instance* of a provider: its credential, its scope, and its declared capabilities. An instance may hold several connections at once, including multiple of the same type (two GitHub orgs; a GitHub org plus a Gitea server). Repos, findings, and remediations are always attributed to their connection.
- **Repo** — a watched repository, with a normalized snapshot (metadata, settings, activity, files of interest).
- **Check** — a single evaluable best-practice rule (e.g., "Dependabot enabled", "cooldown ≥ 7d", "branch protection on default"). Each check declares: how to detect it, what a pass/fail/unknown looks like, and what remediation tier(s) it supports.
- **Policy** — an ordered set of checks with target values. MVP: one fleet-wide policy. Later: multiple policies assignable by language/topic/tag.
- **Finding** — the result of evaluating one check against one repo, with status, evidence, and available remediations.
- **Remediation** — an action that resolves a finding: a deep-link, or a scoped API correction (a settings PATCH or a config PR).

## 5. Functional requirements

### 5.1 Fleet overview (the front door)
A dashboard that, across the whole fleet (all connections), surfaces actionable signal sorted by urgency: open PRs (with Dependabot/security PRs flagged), failing default-branch CI, open security/Dependabot alerts by severity, stale issues, and "release pending" repos (unreleased commits past a threshold). Per-repo drill-down, with the originating provider connection always visible. The overview is the thing the admin opens with coffee.

### 5.2 Hygiene scorecard
For each repo, evaluate the active policy and render a compliance view (per-check pass/fail/unknown + evidence), plus a fleet roll-up (e.g., "9/12 repos compliant; 3 missing cooldown"). Filter and sort by check, by repo, by connection, by failing-only.

### 5.3 Check catalog (initial)
Grouped; each check notes its likely remediation tier — **(L)** deep-link, **(A)** API correction via PR/PATCH, **(R)** report-only. Tiers are evaluated per connection, since a provider may support auto-correction on one platform and only deep-linking on another.

- **Supply chain / dependencies:** Dependabot alerts enabled (A); Dependabot version-updates configured via `dependabot.yml` (A, PR); package-manager **cooldown** configured to target (e.g. 7d) (A, PR); lockfile present (R); dependency review enabled (A/L).
- **Release management:** release-please / "please release" configured (manifest + config present) (A, PR); conventional-commits enforced (detect via commitlint config or a PR-title-lint workflow) (A/L); CHANGELOG present/automated (R); recent-release health / unreleased-commit age (R).
- **Governance:** branch protection or ruleset on the default branch — required reviews, required status checks, no force-push (A/L); CODEOWNERS present (A, PR); default branch name (R).
- **Security posture:** SECURITY.md present (A, PR); secret scanning + push protection enabled (A/L); code scanning (CodeQL) enabled (A/L); org 2FA-required (R/L); signed/attested releases (R).
- **Project meta:** LICENSE present (A, PR); README present (R); description, topics, homepage set (A); issue/PR templates present (A, PR).
- **CI/CD supply-chain:** CI workflow present and green on default branch (R); Actions pinned to SHAs (R); workflow `permissions:` least-privilege (R).

The catalog is data, not a fixed list baked into the UI — adding a check should not require touching the dashboard. (At MVP the catalog can ship as built-in definitions; the requirement is that the *shape* is declarative so the policy model in 5.5 can reference checks by id.)

### 5.4 Remediation spectrum
Every finding offers the highest-safety remediation that fits it:
- **Report** — show the finding and its evidence. Always available.
- **Deep-link** — a one-click jump to the exact GitHub/Gitea page to fix it (the specific branch-protection settings page, the security & analysis tab, etc.). The fallback for anything not cleanly or safely automatable.
- **API correction** — a scoped, human-triggered action: a settings PATCH (enable Dependabot alerts, set description/topics) or a **PR** that adds/updates a config file (`dependabot.yml`, release-please config, LICENSE, SECURITY.md, CODEOWNERS). Anything touching repo contents goes through a PR — never a direct push, never a force.

Every API correction is logged (which connection, who, what, when, resulting PR/URL) and is idempotent. Hangar degrades gracefully: if write scopes weren't granted for a connection, corrections collapse to deep-links for that connection.

### 5.5 Policy model
MVP ships a single, editable fleet-wide policy: a named set of checks with target values. The representation is defined now (a YAML/JSON schema of `{check_id, params, severity}`) even though only one policy exists, so that the Phase-1 work — multiple policies assignable by language, topic/tag, or explicit repo set, with a defined precedence/merge rule — is additive rather than a rewrite.

## 6. Provider abstraction
A `RepoProvider` interface defines the contract every platform adapter implements:
- **Interrogate** — list repos in scope; fetch normalized metadata, settings, activity, and "files of interest" (e.g., `dependabot.yml`).
- **Correct** — perform the scoped settings PATCH / open the config PR for a given remediation.
- **Subscribe** — register for and normalize platform events (push, PR, release, alert, repo/settings changes).

A Hangar instance holds a *collection of provider connections* and may run several at once — including multiple of the same type — with the fleet being their union; nothing in the core privileges one platform. GitHub is the MVP adapter. Gitea is the fast-follow adapter and the forcing function that keeps the core honest. Checks reference *capabilities* a provider declares it supports, so a check that GitHub can auto-correct but Gitea can only deep-link degrades cleanly per provider and per connection.

## 7. Access & provider credentials
Two distinct concerns, deliberately decoupled. This is the correction that keeps the multi-provider model honest: **the way in is a homelab construct; talking to a platform is a provider construct.**

### 7.1 Access to Hangar — homelab-enforced, forward-auth by default
Hangar does not own a login and does not use any provider as its identity gate. It leans on the pattern most self-hosted tools converge on once they outgrow per-app logins: **forward-auth at the reverse proxy.** Traefik's `ForwardAuth` middleware delegates the challenge/redirect dance to an SSO layer (Authelia, Authentik, oauth2-proxy, Tinyauth, Pocket ID) or to network identity (Tailscale); on a valid session the proxy injects an identity header and the request reaches Hangar. Hangar's own auth code stays near-zero — it either trusts that the request arrived through the proxy, or reads the injected header to know *who*.

A single environment variable selects the mode (names illustrative):

- **`HANGAR_FORWARD_AUTH=enabled`** — Hangar trusts a configured identity header. The header name is configurable via **`HANGAR_FORWARD_AUTH_USER_HEADER`** (default `Remote-User`) so it works across providers without code changes: Authelia `Remote-User`, Authentik `X-authentik-username`, oauth2-proxy `X-Forwarded-User`, Tailscale `Tailscale-User-Login`. An optional **`HANGAR_FORWARD_AUTH_ALLOWED_USER`** pins a single expected identity as belt-and-suspenders. This is the recommended posture: sit behind Traefik and authenticate cleanly.
- **`HANGAR_FORWARD_AUTH=disabled`** — no app auth; Hangar trusts the network. Intended for a private LAN / tailnet / VPN where the operator accepts "if you can reach it, you're in" — the normal homelab trust-the-network stance. Someone can deploy this way and run wide open internally on purpose.

**Fail closed by default.** Because the disabled mode is a real security decision, the access mode is not silently defaulted: if `HANGAR_FORWARD_AUTH` is unset, Hangar refuses to start and tells the operator to choose. Wide-open is allowed, but only as a conscious choice.

**The header-spoofing footgun (load-bearing).** Any app that trusts identity headers must guarantee those headers can *only* come from the trusted proxy — otherwise a client that reaches Hangar directly can send `Remote-User: paul` and walk in. Mitigations, layered: bind Hangar to the proxy's internal Docker network and never publish its port directly; optionally pin a trusted-proxy source (IP/CIDR) or require a shared secret header from the proxy. Because Hangar holds provider *write* credentials, this matters more here than for a read-only dashboard — so in `disabled` mode Hangar logs a prominent startup warning and refuses to bind to a non-private/public interface without an explicit **`HANGAR_ALLOW_PUBLIC_BIND`** override.

A thin local bootstrap-admin-secret (a login without running any proxy at all) is deferred to a possible later option, not MVP. The whole point of this design is that entry stays symmetric across providers — a Gitea-only operator never has to authenticate through GitHub.

### 7.2 Provider connections — per-provider credentials, many at once
Each connected provider carries its own credential and scope, managed on a Providers surface:
- *GitHub* — whatever GitHub mechanism gives Hangar the read interrogation and scoped writes it needs. A GitHub App installation is the strong candidate (fine-grained least-privilege permissions, webhooks, high rate limits; verify exact permission set at ADR stage). Multiple GitHub connections — different orgs or installations — may coexist.
- *Gitea* — the analogous mechanism (OAuth2 app / scoped token) on the Gitea side; MVP fast-follow.

Request only the scopes the enabled remediations need; if writes aren't granted for a connection, that connection runs read-only with deep-link remediation. All credentials (App private keys, webhook secrets, tokens) are encrypted at rest, and every correction is attributed to the connection that performed it and written to an audit log. The complexity here lives in the *provider* layer, where it belongs — not in the front door.

## 8. Architecture & runtime
- **Core (Python).** A FastAPI service plus provider adapters in Python, where your GitHub tooling already lives. (`githubkit` is a strong candidate over PyGithub here — async, typed, first-class GitHub App + webhook support — flagged for the ADR.)
- **Background sync.** A scheduled poller refreshes repo snapshots on a cadence, per connection; a **webhook receiver** pushes near-real-time updates and cuts polling pressure. Conditional requests (ETags) keep the rate-limit budget healthy.
- **Datastore.** SQLite for the MVP (zero-ops, one fewer container, fits the homelab ethos); Postgres as the documented upgrade path if event volume or future job state warrants it. ADR decision.
- **Frontend.** Either server-rendered (FastAPI + HTMX/Jinja — minimal JS, very homelab-appropriate) or a small SPA. ADR decision; the dashboard is read-mostly with a handful of action buttons, which favors server-rendered.
- **Deployment.** A single Docker Compose stack deployed via the hola CLI: Traefik labels for routing/TLS and (when access is enabled) the `ForwardAuth` middleware attachment; `homepage.*` labels for the dashboard tile; `hola-*` labels for fleet metadata. All config via env / secret mounts, including the `HANGAR_FORWARD_AUTH*` access toggles and per-connection provider credentials. Hangar binds only to the proxy's internal network unless explicitly overridden.

## 9. Non-functional requirements
- **Rate-limit discipline** — per-connection token budgets + conditional requests + smart polling; never hammer an API on page load.
- **Security** — secrets encrypted at rest; access enforced at the homelab edge via forward-auth (env-toggled, fail-closed when unconfigured), with identity headers trusted only from the proxy — Hangar binds to the internal network and won't expose itself publicly without an explicit override; least-privilege per-connection scopes; an audit log of every correction.
- **Resilience** — survives API/webhook outages by serving the last good cached snapshot; remediations are idempotent and PR-based for anything touching code.
- **Observability** — structured logs, a `/health` endpoint, visible last-sync timestamps per connection so the admin trusts what they're seeing.
- **Footprint** — comfortable on a modest homelab host alongside other services.

## 10. Roadmap

**MVP (Phase 0)** — GitHub adapter with a multi-connection-ready provider model; homelab-edge access (forward-auth env-toggle, configurable identity header, network-only opt-out, fail-closed when unset); fleet overview; single fleet-wide policy + hygiene scorecard; report + deep-link everywhere; a curated set of safe API corrections (enable Dependabot alerts; PR-based `dependabot.yml` with cooldown, LICENSE, SECURITY.md, CODEOWNERS, release-please config); background sync + webhooks; homelab Compose deploy.

**Phase 1 (fast follows)** — Gitea adapter; multiple concurrent connections exercised end-to-end; multiple policies assignable by language/topic/tag with precedence rules; broader correction catalog; optional OSSF Scorecard integration for the security subset; trend/history of compliance over time.

**Phase 2 (later)** — notifications (homepage tile state, ntfy/Slack/email) for new high-severity findings; **Claude Code remediation dispatch** as a third correction channel for fixes too complex for a templated PR (reusing your existing prompt pattern); import/export of policy-as-code; optional bootstrap-admin login for proxy-less deployments.

## 11. Open decisions (for ADR stage)
- **Homelab access integration** — *settled at §7*: forward-auth header trust, env-var toggled, configurable header name, network-only as the explicit (and loud) opt-out, fail-closed when unconfigured. ADR to formalize the toggle states and pin the anti-spoofing mechanism (trusted-proxy CIDR vs. shared-secret header) and whether Tailscale identity is treated as a first-class mode.
- **GitHub connection mechanism** — GitHub App (recommended) vs. simpler token/OAuth-App, and how multiple concurrent GitHub connections are modeled and stored.
- **Build vs. wrap OSSF Scorecard** for the security-posture checks vs. a fully custom engine. *(Verify current Scorecard check set before deciding.)*
- **Exact provider permission sets** mapped per enabled remediation, for true least privilege. *(Needs verification against the current GitHub App permission catalog and Gitea token scopes.)*
- **Detection heuristics per soft check** — how exactly to detect "conventional commits enforced," "cooldown configured," "release-please configured." Define a detection method per check. *(Confirm current `dependabot.yml` cooldown syntax.)*
- **Datastore** (SQLite vs Postgres), **frontend** (server-rendered vs SPA), **GitHub client lib** (githubkit vs PyGithub).
- **Policy schema** — finalize the YAML/JSON shape now so Phase-1 assignment is non-breaking.

## 12. Success criteria
- The admin opens one screen and within seconds knows what needs attention across the whole fleet, regardless of how many providers feed it.
- The fleet's hygiene compliance is a single visible number, and every failing check has a one-click path to fix or to the exact place to fix it.
- Onboarding a new repo requires no per-repo setup — it joins the fleet and is evaluated automatically.
- Adding a second provider connection (a Gitea server, a second GitHub org) is a configuration step, not a code change.
- A new best-practice check can be added as a definition, not a UI change.
- A second person can clone the repo and stand Hangar up against their own providers from the README alone.
