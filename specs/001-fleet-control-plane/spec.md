# Feature Specification: Fleet Control Plane (Hangar MVP)

**Feature Branch**: `001-fleet-control-plane`

**Created**: 2026-06-21

**Status**: Draft

**Input**: User description: "@prd.md — Hangar: a self-hosted, single-operator control plane giving a repo owner a standing fleet-wide view across multiple connected providers, surfacing live activity and hygiene drift against a declarative best-practice policy, with a report / deep-link / scoped-API-correction remediation spectrum."

## User Scenarios & Testing *(mandatory)*

Hangar serves one persona: a single trusted operator (a maintainer running a portfolio of repositories) who watches a **fleet** — the union of all repositories across one or more connected providers — from their own homelab. The stories below are ordered as the operator's journey from "see what's happening" to "see what's drifted" to "fix it," then the foundational slices that let those work across multiple providers and behind a secure homelab edge. Each story is an independently shippable slice of value.

### User Story 1 - See what needs attention across the whole fleet (Priority: P1)

The operator opens a single dashboard with their morning coffee and, without per-repo setup, sees actionable live signal aggregated across every connected provider, sorted by urgency: open pull requests (with dependency-update and security PRs flagged), failing CI on default branches, open security/dependency alerts grouped by severity, stale issues, and repositories with unreleased commits sitting past a threshold ("release pending"). They can drill into any repository, and the originating provider connection is always visible.

**Why this priority**: This is the front door and the first of the two questions Hangar exists to answer ("What needs my attention right now?"). It replaces N browser tabs and tribal memory, and it delivers standalone value even if no other story ships — a read-only aggregated activity view is already useful.

**Independent Test**: Connect a single provider scope, let the fleet sync, open the dashboard, and confirm that live signal for every repository in scope appears in one place, sorted by urgency, with each item attributed to its connection and drillable to the repository.

**Acceptance Scenarios**:

1. **Given** a connected provider scope with several repositories, **When** the operator opens the dashboard, **Then** open PRs, failing default-branch CI, security/dependency alerts by severity, stale issues, and release-pending repositories are shown aggregated across the fleet and ordered by urgency.
2. **Given** an open pull request that is a dependency-update or security PR, **When** it appears in the dashboard, **Then** it is visually flagged as such and distinguishable from ordinary PRs.
3. **Given** any signal item in the dashboard, **When** the operator selects it, **Then** they drill into the originating repository and can see which provider connection it came from.
4. **Given** repositories drawn from more than one connection, **When** the dashboard renders, **Then** every item shows its originating connection and the operator can filter the view by connection.

---

### User Story 2 - See whether the fleet is configured the way I want (hygiene scorecard) (Priority: P2)

The operator views a hygiene scorecard: each repository is evaluated against the active fleet-wide best-practice **policy**, rendering per-check pass / fail / unknown with supporting evidence, alongside a fleet-wide roll-up that reduces compliance to a single visible number and a breakdown ("9/12 repositories compliant; 3 missing cooldown"). The operator can filter and sort by check, by repository, by connection, and by failing-only.

**Why this priority**: This answers the second core question ("Is the fleet configured the way I want it to be?") and turns the operator's one-shot configuration effort into standing, re-checked posture. It depends on a defined policy but is otherwise independent of remediation — surfacing drift is valuable on its own.

**Independent Test**: With an active policy defined, run an evaluation against a fleet that contains both compliant and non-compliant repositories, and confirm the scorecard shows correct per-check pass/fail/unknown with evidence, a correct fleet roll-up number, and working filters/sorts.

**Acceptance Scenarios**:

1. **Given** an active policy and a synced fleet, **When** the operator opens the scorecard, **Then** each repository shows every policy check as pass, fail, or unknown with evidence for the result.
2. **Given** a fleet of mixed compliance, **When** the scorecard renders, **Then** a single fleet-wide compliance figure and a per-check breakdown of how many repositories pass/fail are shown.
3. **Given** the scorecard, **When** the operator filters by "failing only" or by a specific check, repository, or connection, **Then** the view narrows to exactly the matching findings.
4. **Given** a check that cannot be determined for a repository (e.g., a file could not be read or the provider does not support that capability), **When** the scorecard renders, **Then** that check shows as "unknown" with an explanation rather than a false pass or fail.

---

### User Story 3 - Fix drift in place via the remediation spectrum (Priority: P3)

From any finding, the operator is offered the highest-safety remediation that fits it: **Report** (always available — show the finding and its evidence), **Deep-link** (one click to the exact provider page to fix it), or **API correction** (a human-triggered, scoped action — either a settings change applied directly, or a pull request that adds/updates a configuration file). Every API correction is attributed, logged, and idempotent. Anything that touches repository contents is delivered as a pull request, never a direct or forced push. If a connection lacks the write access a correction needs, that correction gracefully collapses to a deep-link for that connection.

**Why this priority**: This is the payoff that turns Hangar from a dashboard into a control plane, but it builds on findings (Story 2) and signal (Story 1). It is the highest-risk capability (it holds write credentials), so it ships after the read-mostly slices that establish trust.

**Independent Test**: Take a failing finding that supports an API correction, trigger it, and confirm the correction is applied as a pull request (for content) or a scoped settings change (for settings), recorded in the audit log with connection/actor/action/timestamp/result, and that re-running it produces no duplicate change; then take a finding on a read-only connection and confirm it offers only report + deep-link.

**Acceptance Scenarios**:

1. **Given** any finding, **When** the operator views it, **Then** "Report" is always available and shows the finding's evidence.
2. **Given** a finding whose check supports deep-linking, **When** the operator chooses Deep-link, **Then** they are taken to the exact provider page where the fix is made.
3. **Given** a finding whose check supports an API correction that touches repository contents, **When** the operator triggers it, **Then** the change is delivered as a pull request — never a direct push and never a force-push — and the resulting PR URL is shown.
4. **Given** a finding whose check supports a settings-only API correction, **When** the operator triggers it, **Then** the scoped settings change is applied and recorded.
5. **Given** any API correction, **When** it completes, **Then** an audit-log entry records the connection, actor, action, timestamp, and resulting PR/URL.
6. **Given** an API correction that has already been applied, **When** the operator triggers it again, **Then** it is idempotent (no duplicate PR, no redundant change).
7. **Given** a connection that was not granted the write access a correction requires, **When** the operator views a finding for that connection, **Then** the API-correction option is unavailable and the remediation collapses to a deep-link.
8. **Given** Hangar at rest, **When** no operator action is taken, **Then** Hangar never autonomously mutates any repository.

---

### User Story 4 - Run several provider connections at once (Priority: P4)

The operator configures one or more **provider connections** — each with its own credential, scope, and declared capabilities — on a Providers surface. An instance can hold multiple connections at once, including multiple of the same type (e.g., two GitHub organizations, or a GitHub organization plus a Gitea server). The fleet is their union; every repository, finding, and remediation is attributed to its connection. Adding a second connection is a configuration step, not a code change. Connections degrade independently: capabilities a provider declares determine which remediation tiers are available per connection.

**Why this priority**: Multi-connection is the architectural promise that keeps the product honest, but a single GitHub connection already powers Stories 1-3. This slice makes the union real and is the forcing function for provider-neutrality; the second provider type (Gitea) is a fast-follow.

**Independent Test**: With one connection working, add a second connection (a second scope of the same provider type, and/or a different provider type) through configuration only, and confirm its repositories merge into the fleet, every item remains attributed to its connection, and per-connection capability differences correctly determine available remediation tiers — all without changing or rebuilding application code.

**Acceptance Scenarios**:

1. **Given** a working connection, **When** the operator adds a second connection via configuration, **Then** repositories from both connections appear in one unified fleet without any code change or custom rebuild.
2. **Given** a fleet drawn from multiple connections, **When** any repository, finding, or remediation is shown, **Then** it is attributed to its originating connection.
3. **Given** two connections whose providers declare different capabilities for the same check, **When** findings are rendered, **Then** the available remediation tier is resolved per connection (e.g., auto-correct on one, deep-link only on the other).
4. **Given** a connection is removed, **When** the fleet next renders, **Then** that connection's repositories and findings no longer appear in the fleet view.

---

### User Story 5 - Reach Hangar securely through the homelab edge (Priority: P5)

Access to Hangar is enforced at the homelab layer, not by the app. Hangar supports forward-auth behind a reverse proxy: it trusts a configurable identity header injected by the proxy and does not implement its own login or use any provider as an identity gate. The access mode must be a conscious choice — if it is unset, Hangar refuses to start and tells the operator to choose. Identity headers are trusted only from the proxy; Hangar binds to the proxy's internal network by default and refuses to expose itself on a public/non-private interface without an explicit override. A network-trust ("disabled") mode is allowed for a private LAN/tailnet/VPN but emits a prominent startup warning. All provider credentials are encrypted at rest.

**Why this priority**: Because Hangar holds write credentials across a whole fleet, secure-by-default access is non-negotiable — but it is foundational plumbing rather than a feature the operator interacts with daily, so it is sequenced as an enabling slice that every other story depends on for safe deployment.

**Independent Test**: Start Hangar with the access mode unset and confirm it refuses to start with a clear message; start it in forward-auth mode behind a proxy and confirm a request carrying a valid identity header from the proxy is admitted while a direct (non-proxy) request carrying a forged identity header is rejected; start it in network-trust mode and confirm a prominent warning and that it refuses to bind publicly without the explicit override.

**Acceptance Scenarios**:

1. **Given** the access mode is not configured, **When** Hangar starts, **Then** it refuses to start and instructs the operator to choose an access mode (fail closed).
2. **Given** forward-auth mode behind a trusted proxy, **When** a request arrives with the configured identity header injected by the proxy, **Then** the request is admitted and the identity is known to Hangar.
3. **Given** forward-auth mode, **When** a client reaches Hangar directly (not via the proxy) and sends a forged identity header, **Then** the request is rejected (header trusted only from the proxy).
4. **Given** the configured identity-header name differs per SSO provider, **When** the operator sets the header-name configuration, **Then** Hangar reads identity from that header without any code change.
5. **Given** network-trust ("disabled") mode, **When** Hangar starts, **Then** it emits a prominent startup warning and refuses to bind to a non-private/public interface unless an explicit public-bind override is set.
6. **Given** stored provider credentials, **When** they are persisted, **Then** they are encrypted at rest.

---

### Edge Cases

- **Write scope not granted for a connection** → API corrections for that connection are hidden and collapse to deep-links; the connection runs read-only.
- **Provider API or webhook outage** → the dashboard and scorecard continue to render the last good cached snapshot rather than erroring or showing blanks; the affected connection's last-sync timestamp visibly indicates staleness.
- **Check result cannot be determined** (file unreadable, capability unsupported by the provider, ambiguous detection) → the finding is "unknown" with an explanation, never a false pass/fail.
- **Idempotent re-trigger** → triggering an already-applied correction produces no duplicate PR and no redundant change.
- **A new repository is created in a connected scope** → it joins the fleet and is evaluated on the next sync with zero per-repo setup.
- **A repository is deleted or a connection is removed** → its repositories, findings, and cached snapshots are removed from the fleet view on the next render, but the connection's immutable audit-log entries are retained (with attribution preserved) so the correction history survives removal.
- **Same logical repository visible via two connections** (e.g., a fork or mirror) → each appears attributed to its own connection and is evaluated per connection.
- **Approaching a provider's rate limit** → Hangar backs off and prefers cached/conditional data rather than hammering the API; page loads do not trigger bursts of live API calls.
- **Webhook and poll disagree** → Hangar reconciles to the most recent known state for that repository.
- **Empty fleet / no connections configured yet** → the operator is guided to add a connection rather than shown a broken/empty dashboard.
- **Direct request with spoofed identity header in network-trust mode** → mitigated by binding to the internal network and refusing public bind without explicit override.

## Clarifications

### Session 2026-06-21

- Q: What maximum fleet size (total repositories across all connections) must the MVP handle while meeting SC-001 (<5s cached dashboard) and SC-010 (no rate-limit exhaustion)? → A: Up to ~500 repositories across a handful of connections (sized for a homelab portfolio on SQLite / a modest host).
- Q: What does a finding show while a Hangar-authored remediation PR is open but not yet merged, and how is idempotency detected? → A: A distinct "remediation pending / PR open" finding state; idempotency is keyed on an existing open Hangar-authored PR for that check, so re-triggering surfaces the existing PR instead of opening a duplicate.
- Q: What populates the audit-log "actor" field in network-trust ("disabled") access mode, which has no per-request identity? → A: A configured operator label (e.g., `HANGAR_OPERATOR`, default `local-operator`); the audit `actor` is always non-null in every access mode.
- Q: When a connection is removed, what happens to its data given the immutable audit log? → A: Hide/purge its live repositories, findings, and cached snapshots, but retain its immutable audit-log entries with attribution preserved, so the audit trail survives connection removal.

## Requirements *(mandatory)*

### Functional Requirements

#### Fleet activity overview

- **FR-001**: System MUST present a single dashboard that aggregates live signal across the entire fleet (all connections) sorted by urgency, including: open pull requests, failing CI on default branches, open security/dependency alerts grouped by severity, stale issues, and repositories with unreleased commits past a configurable threshold.
- **FR-002**: System MUST flag dependency-update and security-related pull requests distinctly from ordinary pull requests.
- **FR-003**: System MUST allow the operator to drill from any signal item into the originating repository, and MUST always display the originating provider connection for each item.
- **FR-004**: System MUST allow filtering the overview by provider connection.

#### Hygiene scorecard & checks

- **FR-005**: System MUST evaluate each repository against the active policy and render a per-check result of pass, fail, or unknown, each with supporting evidence.
- **FR-005a**: System MUST additionally surface a distinct "remediation pending" state for a finding while a Hangar-authored remediation pull request for that check is open and unmerged — distinguishable from a plain fail — and MUST link to that open PR. The finding returns to pass/fail on the next evaluation after the PR is merged or closed.
- **FR-006**: System MUST produce a fleet-wide compliance roll-up that includes a single overall compliance figure and a per-check breakdown of passing/failing repository counts.
- **FR-007**: System MUST allow filtering and sorting the scorecard by check, by repository, by connection, and by failing-only.
- **FR-008**: System MUST represent each check as a declarative definition (identifier, detection method, pass/fail/unknown semantics, supported remediation tiers, and the provider capabilities it requires) such that adding or changing a check does not require modifying the dashboard.
- **FR-009**: System MUST ship the following checks at MVP, grouped by area, each declaring its remediation tier(s): Dependabot/security alerts enabled; dependency version-updates configured; package-manager cooldown configured to a target; lockfile present; dependency review enabled; release automation configured; conventional-commits enforcement; CHANGELOG present/automated; unreleased-commit age; default-branch protection (required reviews, required status checks, no force-push); CODEOWNERS present; default branch name; SECURITY.md present; secret scanning + push protection; code scanning; org 2FA-required; LICENSE present; README present; description/topics/homepage set; issue/PR templates present; CI workflow present and green on default branch; Actions pinned to commit SHAs; workflow permissions least-privilege. (The exact detection heuristic per soft check is finalized at design/ADR stage; see Assumptions.)
- **FR-010**: System MUST resolve a check's available remediation tier(s) per connection, based on the capabilities the connection's provider declares, so that a check that one provider can auto-correct and another can only deep-link degrades cleanly per connection.

#### Remediation spectrum

- **FR-011**: System MUST offer "Report" (show the finding and its evidence) for every finding, always available.
- **FR-012**: System MUST offer a deep-link that navigates to the exact provider page to fix a finding, for checks that support it.
- **FR-013**: System MUST support human-triggered, scoped API corrections of two kinds: a settings change applied directly, and a pull request that adds or updates a configuration file.
- **FR-014**: System MUST deliver any correction that touches repository contents as a pull request — never a direct push and never a force-push.
- **FR-015**: System MUST make every correction idempotent (re-triggering an already-applied correction causes no duplicate PR and no redundant change). For PR-based corrections, idempotency MUST be keyed on the existence of an open Hangar-authored pull request for that check on that repository; re-triggering MUST surface the existing PR rather than open a duplicate.
- **FR-016**: System MUST record every API correction in an audit log capturing connection, actor, action, timestamp, and resulting PR/URL. The actor MUST always be populated: in forward-auth mode it is the proxy-injected identity; in network-trust ("disabled") mode it is a configured operator label (e.g., `HANGAR_OPERATOR`, default `local-operator`).
- **FR-017**: System MUST require explicit operator initiation for every API correction and MUST NOT autonomously mutate any repository.
- **FR-018**: System MUST collapse a finding's remediation to a deep-link (hiding the API-correction option) for any connection that was not granted the write access the correction requires.

#### Policy model

- **FR-019**: System MUST provide a single, editable, fleet-wide policy at MVP, expressed as a named, serializable set of checks with target values and severities (`{check_id, params, severity}`).
- **FR-020**: System MUST define the policy representation such that future multi-policy assignment (by language, topic/tag, or explicit repository set, with precedence/merge rules) is additive rather than a rewrite.

#### Provider connections (multi-connection core)

- **FR-021**: System MUST allow the operator to configure one or more provider connections, each carrying its own credential, scope, and declared capabilities, on a Providers surface.
- **FR-022**: System MUST support holding multiple connections simultaneously, including multiple connections of the same provider type, and MUST present the fleet as their union.
- **FR-023**: System MUST attribute every repository, finding, and remediation to its originating connection.
- **FR-024**: System MUST allow adding a new provider connection as a configuration step, without any change to application code.
- **FR-025**: System MUST support GitHub as the MVP provider, with the provider abstraction designed so that an additional provider type (Gitea) can be added without privileging any platform in shared logic.
- **FR-026**: System MUST request only the access scopes that a connection's enabled remediations require (least privilege, per connection), and MUST run a connection in read-only/deep-link mode when write access is not granted.

#### Access & credentials (homelab edge)

- **FR-027**: System MUST enforce access at the homelab edge via forward-auth and MUST NOT implement its own login or use any provider as its identity gate.
- **FR-028**: System MUST trust a configurable identity header injected by the reverse proxy, with the header name configurable so it works across SSO providers without code changes, and MUST optionally support pinning a single expected identity.
- **FR-029**: System MUST require the access mode to be explicitly set; if it is unset, the system MUST refuse to start and instruct the operator to choose (fail closed). No silent default.
- **FR-030**: System MUST trust identity headers only when they arrive via the proxy, MUST bind to the proxy's internal network by default, and MUST refuse to bind to a non-private/public interface unless an explicit public-bind override is set.
- **FR-031**: System MUST support a network-trust ("disabled") access mode for private networks and MUST emit a prominent startup warning when running in that mode.
- **FR-032**: System MUST encrypt all provider credentials (keys, webhook secrets, tokens) at rest.

#### Sync, freshness & resilience

- **FR-033**: System MUST refresh repository snapshots on a per-connection cadence and MUST accept near-real-time provider events to reduce polling pressure.
- **FR-034**: System MUST evaluate a newly discovered repository in a connected scope automatically on the next sync, with no per-repo setup.
- **FR-035**: System MUST continue to serve the last good cached snapshot during a provider API or webhook outage rather than erroring.
- **FR-036**: System MUST display a visible last-sync timestamp per connection so the operator can judge data freshness.
- **FR-037**: System MUST be rate-limit-disciplined per connection (token budgeting and conditional/cached requests) and MUST NOT issue bursts of live provider API calls on page load.
- **FR-038**: System MUST expose a health endpoint and emit structured logs.

#### Deployment & portability

- **FR-039**: System MUST deploy as a single container-compose stack runnable on a modest homelab host, configured entirely via environment variables and secret mounts.
- **FR-040**: System MUST be standable-up by a second person against their own providers using the repository's README alone, with no undocumented steps.

### Key Entities

- **Fleet**: The union of all repositories Hangar watches across all connected providers. Each connection contributes a scope (an org, a user, or an explicit allowlist).
- **Provider**: An adapter type (e.g., `github`, `gitea`) that implements the interrogate / correct / subscribe contract; declares the capabilities it supports.
- **Provider connection**: A configured instance of a provider — its credential, scope, and declared capabilities. Multiple connections may coexist, including multiples of the same type. The unit to which repositories, findings, and remediations are attributed.
- **Repo**: A watched repository, with a normalized snapshot of metadata, settings, recent activity, and files of interest.
- **Check**: A single declarative best-practice rule — identifier, detection method, pass/fail/unknown semantics, supported remediation tier(s), and required provider capabilities.
- **Policy**: A named, ordered, serializable set of checks with target values and severities. One fleet-wide policy at MVP.
- **Finding**: The result of evaluating one check against one repository — status (pass/fail/unknown, plus a "remediation pending" overlay while a Hangar-authored remediation PR for that check is open), evidence, originating connection, a link to any open remediation PR, and available remediations.
- **Remediation**: An action that resolves a finding — a report, a deep-link, or a scoped API correction (settings change or configuration PR).
- **Audit-log entry**: An immutable record of one API correction — connection, actor (always populated: proxy identity in forward-auth mode, a configured operator label in disabled mode), action, timestamp, and resulting PR/URL. Retained even after its connection is removed, with connection attribution preserved.
- **Capability**: A provider-declared ability that a check references to determine which remediation tier is available per connection.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From a single screen, the operator can identify what needs attention across the entire fleet within seconds (dashboard reaches a usable state in under 5 seconds from cached data) for a fleet of up to ~500 repositories across a handful of connections, regardless of how many provider connections feed it.
- **SC-002**: Fleet hygiene compliance is expressed as a single visible figure, and 100% of failing checks offer at least one remediation path (Report always; deep-link or API correction wherever the connection supports it).
- **SC-003**: Onboarding a new repository requires zero per-repo configuration — a repository created in a connected scope is evaluated automatically within one sync cycle.
- **SC-004**: Adding a second provider connection (a second GitHub organization, or a Gitea server) is accomplished through configuration only, with no change or rebuild of application code.
- **SC-005**: A new best-practice check can be added as a data definition without modifying the dashboard UI.
- **SC-006**: A second person can clone the repository and stand Hangar up against their own providers using only the README, with no undocumented steps.
- **SC-007**: When the access mode is unset, Hangar refuses to start; and a request carrying a forged identity header sent directly to Hangar (not via the proxy) is denied access.
- **SC-008**: 100% of content-changing corrections are delivered as pull requests (zero direct or forced pushes), 100% of API corrections are recorded in the audit log, and re-running any correction makes no additional change (idempotent).
- **SC-009**: During a simulated provider API/webhook outage, the dashboard and scorecard continue to render the last good snapshot, and each connection's staleness is visible via its last-sync timestamp.
- **SC-010**: Under normal use, opening the dashboard does not trigger bursts of live provider API calls, and an instance does not exhaust any connection's provider rate limit.

## Assumptions

- **Single operator, self-hosted.** Exactly one trusted operator per instance; no multi-tenant isolation, no public sign-up, no hosted SaaS. Access is delegated to the homelab edge (forward-auth or network trust); Hangar is never a provider's identity gate.
- **MVP provider is GitHub.** Gitea is a Phase-1 fast-follow; the provider abstraction is designed in from the start, but only GitHub is exercised end-to-end at MVP.
- **Connection scope.** A connection's scope is assumed to be an organization (or user) and/or an explicit allowlist of repositories; org-scope is the primary MVP path.
- **Fleet scale (MVP target).** The MVP is sized for up to ~500 repositories total across a handful of connections, which the SQLite-default datastore on a modest homelab host must serve within the SC-001 and SC-010 targets. Larger fleets are a documented scaling path (e.g., Postgres), not an MVP requirement.
- **MVP check catalog and corrections are curated.** The check list in FR-009 reflects the PRD's MVP catalog; the curated set of safe API corrections at MVP is: enable Dependabot/security alerts (settings), and PR-based additions/updates of `dependabot.yml` (with cooldown), LICENSE, SECURITY.md, CODEOWNERS, and release automation config. Other catalog checks ship as report and/or deep-link at MVP.
- **Detection heuristics are finalized at design/ADR stage.** Exactly how each soft check is detected ("conventional commits enforced," "cooldown configured," "release automation configured," etc.) is defined per check during planning; the spec fixes the behavior (pass/fail/unknown + evidence), not the heuristic.
- **The GitHub connection mechanism, exact per-remediation scope sets, datastore, and other build choices are deferred to ADRs** (the project constitution already pins the broader technology direction); they must satisfy the human-triggered/PR-first and secure/fail-closed requirements above.
- **Reference deployment context.** Hangar is expected to sit behind a reverse proxy with a forward-auth SSO layer on a private homelab network (Traefik + an SSO provider such as Authentik are the illustrative reference, and Tailscale identity is an illustrative network-trust path); the requirements above are written to not privilege any specific proxy or SSO product.
- **Notifications, multi-policy assignment, compliance history/trends, OSSF Scorecard integration, and a Claude Code remediation channel are out of MVP scope** (Phase 1/2 per the roadmap).
- **Default thresholds use sensible defaults** (e.g., "stale issue," "release pending / unreleased-commit age," and "cooldown target") with operator-configurable values; the specific default numbers are set during planning.
