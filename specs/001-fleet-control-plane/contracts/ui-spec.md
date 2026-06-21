# UI Contract (normative): Fleet Control Plane

**Binding reference**: `docs/prototype/Hangar.dc.html` (chosen direction **02 · Clean Developer SAAS**) and `docs/prototype/screenshots/`. This document pins what the shipped React + TypeScript + shadcn/ui SPA MUST reproduce. Where this doc and the prototype disagree, **the prototype wins** — it is the source of truth for layout, tokens, copy, and interaction. Per the user's instruction, the UI is to be implemented fully and faithfully, not approximated.

## Design tokens (lift verbatim from the prototype `:root`)

Mirror these into the Tailwind theme as CSS variables; theme toggle swaps the whole set (light default / dark).

| Token | Light | Dark |
|-------|-------|------|
| `--bg` | `#f5f4f0` | `#0d100e` |
| `--surface` | `#ffffff` | `#161a18` |
| `--surface-2` | `#faf9f6` | `#121514` |
| `--border` | `#eceae5` | `#262b28` |
| `--border-2` | `#f3f1ec` | `#1d211f` |
| `--fg` | `#1d1c1a` | `#e9ebe6` |
| `--fg-2` | `#54514a` | `#a7aca5` |
| `--muted` | `#8a877e` | `#6e736d` |
| `--hover` | `#f7f6f2` | `#1c211e` |
| `--pass` | `#2f8f57` | `#5cc98a` |
| `--warn` | `#b9791a` | `#e0a23c` |
| `--fail` | `#c2443f` | `#f0635c` |
| `--unknown` | `#9a968c` | `#6e736d` |
| `--pass-bg` / `--warn-bg` / `--fail-bg` | `#e9f3ec` / `#f7efe0` / `#f6e7e6` | `#13241a` / `#2a2113` / `#2a1715` |

**Typography**: `Public Sans` for UI text; `JetBrains Mono` for numerals, IDs, badges, repo names, audit rows. **Color is status-only** — chrome stays monochrome; `--pass/--warn/--fail/--unknown` carry all semantic color. Dense / power-user spacing as in the prototype.

**Status → glyph/label map** (prototype `viz`): pass `●` green · fail `✕` red · unknown `○` grey · working `◐` amber "Working…" · pending `◐` amber "PR open". Hygiene color thresholds (`hygColor`): ≥85 `--pass`, ≥65 `--warn`, else `--fail`.

## App shell (every screen)

- **Topbar** (52px): Hangar logo + mark, `/` breadcrumb to current screen title; right side — **connection switcher** (dot + `gh:get2knowio ▾`, dropdown lists "All connections" + each connection with tick/dot/scope), `synced {n} ago`, **theme toggle** (`☾ Dark` / `☀ Light`).
- **Sidebar** (212px): "FLEET" label; nav items **Overview / Scorecard / Catalog & policy / Providers** with icon, active highlight, and urgency badges (Overview badge = CI-fail + critical-alert count in `--fail`; Scorecard badge = repos < 65% in `--warn`). Footer: **Access: forward-auth** dot + `Remote-User · fail-closed / behind Traefik`.
- **Toast** (bottom-center): appears on remediation actions, auto-dismisses (~2.6s).

## Screens (all five are MVP)

### 1. Fleet overview (`/`)
Title + `{n} repos · {pct}% compliant`; subtitle "What needs attention right now, across {scope}." **Six stat tiles** (Open PRs, Bot PRs, CI failing, Sec alerts, Release pending, Compliance) in a 6-col grid. Two columns: **repo table** (Repository / PRs / CI / Alerts / Release / Hygiene-bar) with connection badges and bot-PR `🤖` flag; **attention feed** (left-border-color by tone, tag + repo + title) sorted critical → CI → release → high-alert → bot PRs. Rows and feed items drill into the repo. (FR-001–FR-004)

### 2. Hygiene scorecard (`/scorecard`)
Title + `{pct}% fleet compliance · {clear}/{n} clear`. **Top-drift chips** + **Failing-only toggle**. **Matrix**: sticky repo column (hygiene % + name + connection badge), grouped check columns (Supply chain / Release / Governance / Security / Project meta), per-cell glyph from `viz`; failing-only dims passing cells to 0.12 opacity. Legend row. Click a repo → drill-in. (FR-005–FR-007)

### 3. Check catalog & policy (`/catalog`)
Title + `{enabled} of {total} checks active`. Subtitle stresses "catalog is data, not UI." Checks grouped; each row: **toggle** (in/out of policy), label + **tier badge** (`API` / `API · PR` / `Deep-link` / `Report`), check `id` in mono, optional **target input** (e.g. cooldown days), and a per-check **pass-rate bar** `{pass}/{total}`. Toggling/targets recompute the scorecard live. (FR-008, FR-009, FR-019, FR-020)

### 4. Providers & access (`/providers`)
Title + subtitle on the homelab/provider decoupling. **Access banner**: forward-auth state, `HANGAR_FORWARD_AUTH=enabled · header Remote-User · allowed=paul · fail-closed when unset`, "Behind Traefik" pill. **Connection cards** (`+ Add connection`): label, type badge, **Read+write / Read-only** pill, synced; grid of Scope / Auth / Repos / Remediation. **Audit log** table — every correction (time, repo, check, result). (FR-021–FR-032)

### 5. Repo drill-down (`/repos/:id`)
Back link; repo name (mono) + connection badge + optional **read-only · deep-link only** pill; big right-aligned **hygiene %** + `{pass}/{total} checks`. **Activity strip**: Open pull requests list (dependabot `⚙` vs human `↗`, status, age), CI default-branch card, Security-alerts card (severity pills). **Policy checks & remediation**, grouped; each check row: status glyph, label + tier badge, evidence, and the **remediation control**:
  - `pass` → "Pass" / "Fixed via Hangar ✓"
  - `fail`/`unknown` + `report` → "Report only"
  - `link` (or read-only) → **Open in {provider} ↗** (deep-link)
  - `patch` writable → **Enable** (settings)
  - `pr` writable → **Open fix PR** → `working…` → **PR #{n} open ↗** with **Mark merged** → fixed
(Story 3; FR-011–FR-018)

## Interactions / state (reproduce prototype logic)

- **Connection filter**: `all` or one connection re-scopes every screen (overview, scorecard, repo set, stats, feed) — prototype `visibleRepos`.
- **Remediation state machine**: `none → working → (pr_open ⇒ pending | fixed) ` with toast + audit append; read-only connections always degrade write tiers to deep-link (prototype `fire`/`deep`/`markMerged`). Idempotent: existing open Hangar PR is surfaced, not duplicated.
- **Theme**: light/dark token swap, persisted.
- **Empty/outage states**: empty fleet guides "add a connection"; provider outage keeps the last cached snapshot with a stale `last_sync` indicator (Edge Cases, FR-035/FR-036).

## Fidelity acceptance criteria

- [ ] All five screens present and reachable via the sidebar, matching the prototype layout and copy.
- [ ] Design tokens, fonts, and status-only color match the prototype in **both** light and dark.
- [ ] Connection switcher, theme toggle, urgency badges, attention-feed ordering, scorecard matrix (incl. failing-only dimming and legend), catalog toggles/targets/pass-bars, providers access banner + audit log, and the repo remediation state machine all behave as in `Hangar.dc.html`.
- [ ] Numerals/IDs/badges render in JetBrains Mono; chrome is monochrome.
- [ ] Playwright e2e walks the prototype's primary flows (overview → drill-in → open fix PR → mark merged → audit entry; scorecard failing-only; catalog toggle recomputes; connection filter).
