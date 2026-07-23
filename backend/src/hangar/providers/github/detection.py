"""GitHub detection heuristics (research.md §11) — real, read-only interrogation.

Each catalog check maps to a live GitHub read (repo metadata, contents API, rulesets,
org policy, alerts). The primary repo resource is fetched conditionally (If-None-Match);
a ``304`` means the **repo body** is unchanged, so the checks derived from that body are
reused from the previous snapshot — but every other signal (alerts, CI, PRs, releases,
settings, rulesets) is still re-fetched, because those change without altering the repo
resource's ETag. A check whose required capability/scope is absent — or whose resource
returns ``403`` — yields ``unknown`` rather than a false pass/fail.
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Any

from hangar.domain.models import (
    AlertCounts,
    Capability,
    CIStatus,
    ProviderConnection,
    PullRequestSummary,
    Repo,
)
from hangar.domain.repo_config import HangarRepoConfig

if TYPE_CHECKING:
    from datetime import datetime

    from githubkit import GitHub

    from hangar.providers.github.adapter import GitHubAdapter

# A workflow step's ``uses:`` reference. Anchored to the step-key position (start of line,
# optionally after a ``- `` list marker) so a ``run:`` line that merely echoes the word
# "uses:" inside a string is not mistaken for an action reference. Comments are already
# stripped by the caller.
_USES_RE = re.compile(r"""^\s*-?\s*uses:\s*['"]?([^'"\s]+)""")
# A 40-hex git commit SHA (a "pinned" action ref).
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
# Actions/config that indicate conventional-commit / PR-title enforcement.
_CONVENTIONAL_ACTIONS = ("commitlint", "action-semantic-pull-request", "semantic-pull-request")
_CONVENTIONAL_CONFIGS = (
    "commitlint.config.js", "commitlint.config.cjs", "commitlint.config.mjs",
    ".commitlintrc", ".commitlintrc.json", ".commitlintrc.yml", ".commitlintrc.yaml",
)
# Unreleased-commit age (HEAD − last release, in days) at/above which release_health fails.
_RELEASE_STALE_DAYS = 14

# Checks whose outcome is derived purely from the primary repo resource body. On a 304
# (repo body unchanged) these are carried over from the previous snapshot; everything
# else is always re-evaluated.
_METADATA_CHECKS = frozenset({"license", "description", "default_branch", "secret_scanning"})

# Update-bot config locations. "Version updates configured" (check id ``dependabot_updates``,
# kept stable) passes when EITHER a Dependabot or a Renovate config is present — Hangar tracks
# both, so a Renovate-only repo is not falsely failed for "no version updates".
_DEPENDABOT_CONFIG_FILES = [".github/dependabot.yml", ".github/dependabot.yaml"]
_RENOVATE_CONFIG_FILES = [
    "renovate.json", "renovate.json5", ".github/renovate.json", ".github/renovate.json5",
    ".renovaterc", ".renovaterc.json", ".renovaterc.json5",
]

# Candidate paths whose presence satisfies a file-based check. (license is determined
# from repo metadata below — GitHub's own license detection — not a filename match.)
_FILE_CHECKS = {
    "readme": ["README.md", "README.rst", "README"],
    "security_md": ["SECURITY.md", ".github/SECURITY.md"],
    "contributing": ["CONTRIBUTING.md", ".github/CONTRIBUTING.md", "docs/CONTRIBUTING.md"],
    "codeowners": ["CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"],
    "changelog": ["CHANGELOG.md", "CHANGELOG"],
    "lockfile": ["poetry.lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
                 "bun.lock", "bun.lockb", "uv.lock", "Cargo.lock"],
    "release_please": ["release-please-config.json", ".release-please-manifest.json"],
    "templates": [".github/ISSUE_TEMPLATE/config.yml", ".github/ISSUE_TEMPLATE",
                  ".github/PULL_REQUEST_TEMPLATE.md"],
    "dependabot_updates": _DEPENDABOT_CONFIG_FILES + _RENOVATE_CONFIG_FILES,
}

# --------------------------------------------------------------------------------------
# Provider-neutral content heuristics (shared with the Gitea adapter, which imports them).
# Each is a pure function over already-fetched text/refs so both adapters detect the same
# way; the platform reads that feed them live in the adapter-specific groups below.
# --------------------------------------------------------------------------------------

# Attacker-controllable GitHub Actions contexts whose raw interpolation into a step is a
# script-injection vector (Scorecard "Dangerous-Workflow").
_INJECTABLE_RE = re.compile(
    r"\$\{\{\s*github\.(?:"
    r"event\.(?:issue|pull_request|comment|review|discussion|commits|head_commit|"
    r"workflow_run)[\w.\[\]]*\.(?:title|body|message|name|email|label|ref)"
    r"|event\.pages[\w.\[\]]*\.page_name"
    r"|head_ref)\b"
)
# A checkout that pulls the untrusted PR head (dangerous under pull_request_target/workflow_run).
_UNTRUSTED_CHECKOUT_RE = re.compile(
    r"ref:\s*\$\{\{\s*github\.(?:event\.pull_request\.head\.(?:sha|ref)|head_ref)"
)
# A pull_request trigger (excluding pull_request_target, which does NOT gate normal PRs the
# same way and is itself a dangerous-workflow signal).
_PR_TRIGGER_RE = re.compile(r"\bpull_request\b(?!_target)")

_SBOM_ACTION_MARKERS = ("sbom", "cyclonedx", "cdxgen", "syft")
_SBOM_FILE_CANDIDATES = [
    "sbom.json", "sbom.spdx.json", "sbom.cdx.json", "sbom.xml",
    "bom.json", "bom.xml", ".sbom/bom.json",
]
_SIGNING_ACTION_MARKERS = ("cosign", "sigstore", "slsa-github-generator", "slsa-framework")
_SIGNATURE_ASSET_SUFFIXES = (".sig", ".asc", ".intoto.jsonl", ".sigstore", ".pem.sig")

# Committed executable/compiled outputs that can't be audited from source (Scorecard
# "Binary-Artifacts"). Fonts/images are intentionally excluded — they are not build outputs.
_BINARY_EXTENSIONS = (
    ".exe", ".dll", ".so", ".dylib", ".a", ".o", ".class", ".jar", ".war", ".ear",
    ".pyc", ".pyo", ".wasm", ".node", ".msi", ".deb", ".rpm", ".apk", ".dmg", ".pkg",
)

_FROM_RE = re.compile(r"^\s*FROM\s+(\S+)(?:\s+AS\s+(\S+))?", re.IGNORECASE)


def _extract_refs(text: str) -> list[str]:
    """All ``uses:`` action references in one workflow file's text (comments stripped)."""
    refs: list[str] = []
    for line in text.splitlines():
        m = _USES_RE.match(line.split("#", 1)[0])
        if m:
            refs.append(m.group(1))
    return refs


def _on_block(text: str) -> str:
    """The body of a workflow's top-level ``on:`` block (inline and nested forms).

    Returns just the trigger section so a ``pull_request`` mention inside a job step
    (e.g. ``github.event.pull_request.number``) isn't mistaken for a trigger.
    """
    out: list[str] = []
    capturing = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line:
            continue
        m = re.match(r"^on\s*:(.*)$", line)  # top-level key (no indentation)
        if m:
            capturing = True
            out.append(m.group(1))
            continue
        if capturing:
            if re.match(r"^\S", line):  # next top-level key ends the on: block
                break
            out.append(line)
    return "\n".join(out)


def workflow_is_dangerous(texts: list[str]) -> bool:
    """True if any workflow shows a Scorecard 'dangerous workflow' pattern.

    (1) an attacker-controlled context interpolated into a step (script injection), or
    (2) a ``pull_request_target`` / ``workflow_run`` trigger that checks out the PR head
    ref — running untrusted code with the base repo's write token/secrets ("pwn request").
    """
    for text in texts:
        if _INJECTABLE_RE.search(text):
            return True
        on = _on_block(text)
        if ("pull_request_target" in on or "workflow_run" in on) and _UNTRUSTED_CHECKOUT_RE.search(text):
            return True
    return False


def workflow_triggers_on_pr(texts: list[str]) -> bool:
    """True if any workflow is triggered by ``pull_request`` (CI gates PRs — Scorecard CI-Tests)."""
    return any(_PR_TRIGGER_RE.search(_on_block(t)) for t in texts)


def refs_generate_sbom(refs: list[str]) -> bool:
    """True if a workflow references an SBOM-generating action/tool."""
    return any(any(m in r.lower() for m in _SBOM_ACTION_MARKERS) for r in refs)


def refs_sign_releases(refs: list[str]) -> bool:
    """True if a workflow references release-signing / provenance tooling."""
    return any(any(m in r.lower() for m in _SIGNING_ACTION_MARKERS) for r in refs)


def release_assets_signed(assets: list) -> bool:
    """True if a release carries signature/provenance assets (``.sig``/``.asc``/in-toto)."""
    for a in assets:
        name = (a.get("name") or "").lower() if isinstance(a, dict) else ""
        if name.endswith(_SIGNATURE_ASSET_SUFFIXES) or "provenance" in name or "intoto" in name:
            return True
    return False


def dockerfile_has_unpinned_base(text: str) -> bool:
    """True if any Dockerfile ``FROM`` pulls a registry image without a ``@sha256:`` digest.

    Multi-stage aliases (``FROM builder``), ``scratch``, and build-arg images (``FROM $BASE``)
    are not registry pulls and are skipped.
    """
    stages: set[str] = set()
    unpinned = False
    for raw in text.splitlines():
        m = _FROM_RE.match(raw.split("#", 1)[0])
        if not m:
            continue
        image, alias = m.group(1), m.group(2)
        if alias:
            stages.add(alias.lower())
        low = image.lower()
        if low == "scratch" or low in stages or image.startswith("$"):
            continue
        if "@sha256:" not in image:
            unpinned = True
    return unpinned


def tree_has_binaries(tree_items: list) -> bool:
    """True if any blob in a recursive git tree is a committed executable/compiled binary."""
    for it in tree_items:
        if isinstance(it, dict) and it.get("type") == "blob":
            if (it.get("path") or "").lower().endswith(_BINARY_EXTENSIONS):
                return True
    return False


async def interrogate_repo(
    adapter: GitHubAdapter,
    gh: GitHub,
    connection: ProviderConnection,
    repo_ref: str,
    previous: Repo | None = None,
) -> Repo | None:
    """Interrogate one repo into a normalized snapshot.

    Returns ``None`` only when the repo is unreadable (404/403) or when it is unchanged
    *and* there is no prior snapshot to carry forward. A primary-resource ``304`` reuses
    the repo-body-derived checks from ``previous`` and re-fetches all volatile signals.
    """
    from hangar.providers.github.adapter import _FORBIDDEN, _NOT_FOUND, _NOT_MODIFIED

    owner = connection.owner
    granted = connection.granted_capabilities
    cget = adapter._conditional_get

    repo_data = await cget(gh, connection.id, f"/repos/{owner}/{repo_ref}", conditional=True)
    if repo_data is _NOT_FOUND or repo_data is _FORBIDDEN:
        return None  # repo unreadable on this connection — keep any cached snapshot
    if repo_data is _NOT_MODIFIED:
        if previous is None:
            # A 304 with no cached snapshot to carry forward — e.g. a stale in-memory ETag
            # that outlived the row after the repo was pruned from an allowlist and
            # re-added. The 304 can't be acted on, so refetch the repo in full to rebuild
            # rather than reporting it permanently absent until its body next changes.
            repo_data = await cget(
                gh, connection.id, f"/repos/{owner}/{repo_ref}", conditional=False
            )
            if not isinstance(repo_data, dict):
                return None
            meta_fails, meta_unknowns, description, default_branch, license_spdx = _metadata_checks(repo_data)
        else:
            meta_fails, meta_unknowns, description, default_branch, license_spdx = _metadata_from_previous(previous)
    else:
        meta_fails, meta_unknowns, description, default_branch, license_spdx = _metadata_checks(repo_data)

    (dyn_fails, dyn_unknowns, open_prs, bot_prs, ci, alerts, release_pending, pulls) = (
        await _dynamic_checks(adapter, gh, connection, owner, repo_ref, default_branch, granted)
    )

    # The repo's committed .hangar.json opt-outs. Gated on file reads; unreadable → {}.
    suppressions: dict[str, str] = {}
    if Capability.read_files in granted:
        suppressions = await _read_suppressions(cget, gh, connection.id, owner, repo_ref)

    fails = meta_fails + dyn_fails
    unknowns = meta_unknowns + dyn_unknowns
    return Repo(
        id=repo_ref,
        connection_id=connection.id,
        description=description,
        default_branch=default_branch,
        open_prs=open_prs,
        bot_prs=bot_prs,
        ci_status=ci,
        alerts=alerts,
        release_pending_days=release_pending,
        fails=sorted(set(fails)),
        unknowns=sorted(set(unknowns) - set(fails)),
        suppressions=suppressions,
        license_spdx=license_spdx,
        pull_requests=[PullRequestSummary(**d) for d in pulls],
    )


def _license_spdx(repo_data: Any) -> str | None:
    """The SPDX id of a detected license, or None when absent/unidentifiable.

    GitHub reports ``NOASSERTION`` when a LICENSE file exists but maps to no known SPDX id
    (custom/unrecognized) — the license check still passes, but there's no id to show.
    """
    lic = repo_data.get("license") or {}
    spdx = lic.get("spdx_id")
    return spdx if spdx and spdx != "NOASSERTION" else None


def _metadata_checks(repo_data: Any) -> tuple[list[str], list[str], str, str, str | None]:
    """Checks derived from the primary repo resource body (license/description/branch/secret)."""
    fails: list[str] = []
    unknowns: list[str] = []

    if not repo_data.get("license"):
        fails.append("license")
    # The catalog check is "Description & topics set" — both are required; the evidence
    # string (project_meta) reports which is missing without claiming both are empty.
    if not (repo_data.get("description") and repo_data.get("topics")):
        fails.append("description")
    default_branch = repo_data.get("default_branch") or "main"
    if default_branch != "main":
        fails.append("default_branch")

    saa = repo_data.get("security_and_analysis")
    if saa is not None:
        ss = (saa.get("secret_scanning") or {}).get("status")
        pp = (saa.get("secret_scanning_push_protection") or {}).get("status")
        if ss != "enabled" or pp != "enabled":
            fails.append("secret_scanning")
    else:
        # `security_and_analysis` is omitted entirely when the token is not repo-admin
        # (and for some plans/visibilities), so an absent field means the state is
        # unreadable — honestly `unknown`, never a fabricated `fail` (Constitution VIII).
        unknowns.append("secret_scanning")

    return fails, unknowns, repo_data.get("description") or "", default_branch, _license_spdx(repo_data)


def _metadata_from_previous(previous: Repo) -> tuple[list[str], list[str], str, str, str | None]:
    """Carry the repo-body-derived checks from a prior snapshot on a 304."""
    fails = [c for c in previous.fails if c in _METADATA_CHECKS]
    unknowns = [c for c in previous.unknowns if c in _METADATA_CHECKS]
    return fails, unknowns, previous.description, previous.default_branch, previous.license_spdx


async def _dynamic_checks(
    adapter: GitHubAdapter,
    gh: GitHub,
    connection: ProviderConnection,
    owner: str,
    repo_ref: str,
    default_branch: str,
    granted: set[Capability],
) -> tuple[list[str], list[str], int, int, CIStatus, AlertCounts, int | None, list[dict]]:
    """All checks that can change without the primary repo resource's ETag changing.

    Always re-evaluated each poll (even on a 304) so security/activity drift surfaces.
    A ``403`` on any resource yields ``unknown`` for the affected check(s) rather than
    propagating an exception that would abort the whole snapshot.
    """
    from hangar.providers.github.adapter import _FORBIDDEN, _NO_CONTENT, _NOT_FOUND

    cget = adapter._conditional_get
    fails: list[str] = []
    unknowns: list[str] = []

    can_files = Capability.read_files in granted
    can_settings = Capability.read_settings in granted
    can_alerts = Capability.read_alerts in granted
    can_org = Capability.read_org_policy in granted

    # Scalars produced by the activity groups below (filled via nonlocal).
    open_prs = bot_prs = 0
    pull_details: list[dict] = []
    ci = CIStatus.none
    alerts = AlertCounts()
    release_pending: int | None = None
    # Signals for checks whose outcome combines a workflow read with a file/release read
    # (sbom, signed_releases). Set by the groups; combined once, race-free, after the gather.
    sbom_wf = signing_wf = sbom_file = release_signed = False

    async def _probe(path: str) -> object:
        return await cget(gh, connection.id, f"/repos/{owner}/{repo_ref}/contents/{path}")

    async def _present(path: str) -> bool:
        r = await _probe(path)
        return r is not _NOT_FOUND and r is not _FORBIDDEN

    # The groups below are independent provider reads with no cross-dependency, so they run
    # concurrently (asyncio.gather) instead of serially — the bulk of a repo's poll latency.
    # Each appends to the shared fails/unknowns (list.append is atomic between awaits and the
    # caller normalizes order) and writes its scalar via nonlocal. None of these reads is
    # conditional, so the per-connection ETag store is never written here: concurrency is safe.

    async def _files_group() -> None:
        # file-presence checks (contents API; 404 = absent, 403 = unknown) + cooldown
        nonlocal sbom_file
        if not can_files:
            unknowns.extend(_FILE_CHECKS)
            unknowns.extend(["cooldown", "pinned_deps"])
            return

        async def _one(check_id: str, candidates: list[str]) -> tuple[str, str]:
            for path in candidates:
                r = await _probe(path)
                if r is _FORBIDDEN:
                    return check_id, "unknown"
                if r is not _NOT_FOUND:
                    return check_id, "present"
            return check_id, "absent"

        statuses = dict(await asyncio.gather(*(_one(c, p) for c, p in _FILE_CHECKS.items())))
        for cid, st in statuses.items():
            if st == "unknown":
                unknowns.append(cid)
            elif st == "absent":
                fails.append(cid)

        # cooldown: the present update-bot config must declare a cooldown (requires reading
        # content). Dependabot uses a `cooldown:` block; Renovate uses `minimumReleaseAge`
        # (legacy `stabilityDays`). Keyed off dependabot_updates so a repo with no update bot
        # at all fails once (here) rather than twice.
        if statuses.get("dependabot_updates") == "unknown":
            unknowns.append("cooldown")
        elif statuses.get("dependabot_updates") == "absent":
            fails.append("cooldown")  # no update bot configured at all
        elif not await _has_cooldown(cget, gh, connection.id, owner, repo_ref):
            fails.append("cooldown")

        # pinned_deps: a committed Dockerfile must pin its base image(s) by @sha256 digest.
        # No Dockerfile → nothing of this kind to pin → passes (no entry).
        docker = await _read_text(cget, gh, connection.id, owner, repo_ref, "Dockerfile")
        if docker is not None and dockerfile_has_unpinned_base(docker):
            fails.append("pinned_deps")

        # sbom: a committed SBOM file satisfies half of the check (workflow marker is the other).
        for cand in _SBOM_FILE_CANDIDATES:
            if await _present(cand):
                sbom_file = True
                break

    async def _settings_group() -> None:
        # settings/ruleset checks (403 = unknown, 404 = not configured = fail)
        if not can_settings:
            unknowns.extend(["branch_protection", "workflow_permissions", "code_scanning",
                             "signed_commits"])
            return
        prot, wf_perms, cs, sigs = await asyncio.gather(
            cget(gh, connection.id, f"/repos/{owner}/{repo_ref}/branches/{default_branch}/protection"),
            cget(gh, connection.id, f"/repos/{owner}/{repo_ref}/actions/permissions/workflow"),
            cget(gh, connection.id, f"/repos/{owner}/{repo_ref}/code-scanning/analyses"),
            cget(gh, connection.id,
                 f"/repos/{owner}/{repo_ref}/branches/{default_branch}/protection/required_signatures"),
        )
        # signed_commits: the required_signatures endpoint 404s when the branch is unprotected
        # (→ not enforced = fail); 403 → unknown; 200 carries {"enabled": bool}.
        if sigs is _FORBIDDEN:
            unknowns.append("signed_commits")
        elif isinstance(sigs, dict):
            if not sigs.get("enabled"):
                fails.append("signed_commits")
        else:
            fails.append("signed_commits")
        if prot is _FORBIDDEN:
            unknowns.append("branch_protection")
        elif prot is _NOT_FOUND:
            fails.append("branch_protection")
        if isinstance(wf_perms, dict):
            if wf_perms.get("default_workflow_permissions") != "read":
                fails.append("workflow_permissions")
        elif wf_perms is _FORBIDDEN:
            unknowns.append("workflow_permissions")
        elif wf_perms is _NOT_FOUND:
            fails.append("workflow_permissions")
        if cs is _FORBIDDEN:
            unknowns.append("code_scanning")
        elif cs is _NOT_FOUND:
            fails.append("code_scanning")

    async def _org_group() -> None:
        # org 2FA enforcement (org policy scope)
        if not can_org:
            unknowns.append("two_fa")
            return
        org = await cget(gh, connection.id, f"/orgs/{owner}")
        if isinstance(org, dict) and not org.get("two_factor_requirement_enabled"):
            fails.append("two_fa")
        elif org is _NOT_FOUND or org is _FORBIDDEN:
            unknowns.append("two_fa")

    async def _workflows_group() -> None:
        # Everything derived from parsing .github/workflows/*: dep_review / conventional /
        # actions_pinned_sha / dangerous_workflow / ci_tests_on_pr, plus the workflow-side
        # signals for sbom and signed_releases.
        nonlocal sbom_wf, signing_wf
        if not can_files:
            unknowns.extend(["dep_review", "conventional", "actions_pinned_sha",
                             "dangerous_workflow", "ci_tests_on_pr"])
            return
        texts = await _read_workflow_texts(cget, gh, connection.id, owner, repo_ref)
        refs = [r for t in texts for r in _extract_refs(t)]
        if not any("dependency-review-action" in r for r in refs):
            fails.append("dep_review")
        has_conv = any(any(a in r for a in _CONVENTIONAL_ACTIONS) for r in refs)
        if not has_conv:
            for p in _CONVENTIONAL_CONFIGS:
                if await _present(p):  # short-circuits on the first config that exists
                    has_conv = True
                    break
        if not has_conv:
            fails.append("conventional")
        if _has_unpinned_action(refs):
            fails.append("actions_pinned_sha")
        if workflow_is_dangerous(texts):
            fails.append("dangerous_workflow")
        if not workflow_triggers_on_pr(texts):
            fails.append("ci_tests_on_pr")
        sbom_wf = refs_generate_sbom(refs)
        signing_wf = refs_sign_releases(refs)

    async def _release_group() -> None:
        # release_health: age of unreleased commits = default-branch HEAD date − last release.
        # signed_releases (workflow-independent side): the latest release's signature assets.
        nonlocal release_pending, release_signed
        rel = await cget(gh, connection.id, f"/repos/{owner}/{repo_ref}/releases/latest")
        if isinstance(rel, dict):
            release_signed = release_assets_signed(rel.get("assets") or [])
        release_pending = await _release_pending_days(
            cget, gh, connection.id, owner, repo_ref, default_branch, rel
        )
        if release_pending is not None and release_pending >= _RELEASE_STALE_DAYS:
            fails.append("release_health")

    async def _tree_group() -> None:
        # binary_artifacts: recursive git-tree scan for committed executables/compiled output.
        if not can_files:
            unknowns.append("binary_artifacts")
            return
        tree = await cget(
            gh, connection.id, f"/repos/{owner}/{repo_ref}/git/trees/{default_branch}",
            {"recursive": "1"},
        )
        if isinstance(tree, dict):
            if tree_has_binaries(tree.get("tree") or []):
                fails.append("binary_artifacts")
            elif tree.get("truncated"):
                # GitHub caps a tree at ~100k entries; a truncated listing we didn't find a
                # binary in is not a clean pass — report it honestly as unknown.
                unknowns.append("binary_artifacts")
        else:  # 403/404/other → undeterminable, honestly unknown (never a fabricated pass)
            unknowns.append("binary_artifacts")

    async def _pulls_group() -> None:
        nonlocal open_prs, bot_prs, pull_details
        open_prs, bot_prs, pull_details = await _pull_data(cget, gh, connection.id, owner, repo_ref)

    async def _ci_group() -> None:
        nonlocal ci
        ci = await _ci_status(cget, gh, connection.id, owner, repo_ref, default_branch)
        if ci is CIStatus.fail:
            fails.append("ci_workflow_green")
        elif ci is CIStatus.none:
            unknowns.append("ci_workflow_green")

    async def _alerts_group() -> None:
        nonlocal alerts
        if can_alerts:
            alerts = await _alert_counts(gh, connection.id, owner, repo_ref)

    async def _dependabot_alerts_group() -> None:
        # vulnerability-alerts endpoint: 204 (enabled), 404 (disabled), 403 (unreadable).
        # Capability-gated on read_alerts so an undeterminable state is honestly `unknown`.
        if not can_alerts:
            unknowns.append("dependabot_alerts")
            return
        va = await cget(gh, connection.id, f"/repos/{owner}/{repo_ref}/vulnerability-alerts")
        if va is _NOT_FOUND:
            fails.append("dependabot_alerts")  # endpoint 404 → alerts disabled
        elif va is not _NO_CONTENT:  # 403 or any unexpected body → cannot determine
            unknowns.append("dependabot_alerts")
        # _NO_CONTENT (204) → alerts enabled → passing (no entry)

    await asyncio.gather(
        _files_group(),
        _settings_group(),
        _org_group(),
        _workflows_group(),
        _release_group(),
        _tree_group(),
        _pulls_group(),
        _ci_group(),
        _alerts_group(),
        _dependabot_alerts_group(),
    )

    # Combine the multi-read checks once, after the gather (race-free): sbom passes on a
    # committed SBOM file OR an SBOM-generating workflow; signed_releases passes on signing
    # tooling in a workflow OR signature assets on the latest release. Both depend on file
    # reads, so they are honestly `unknown` when the file capability is absent.
    if can_files:
        if not (sbom_file or sbom_wf):
            fails.append("sbom")
    else:
        unknowns.append("sbom")
    if signing_wf or release_signed:
        pass
    elif can_files:
        fails.append("signed_releases")
    else:
        unknowns.append("signed_releases")

    return fails, unknowns, open_prs, bot_prs, ci, alerts, release_pending, pull_details


async def _read_workflow_texts(
    cget: Any, gh: GitHub, cid: str, owner: str, repo: str
) -> list[str]:
    """The text of every ``.github/workflows/*.yml`` file (comments intact).

    Lists the workflows directory and reads each YAML file. Returns [] when there is no
    workflows directory (cget yields a NOT_FOUND/FORBIDDEN sentinel, not a list). Callers
    derive action refs (``_extract_refs``) and the content heuristics (dangerous-workflow,
    PR trigger, SBOM/signing action markers) from these texts.
    """
    listing = await cget(gh, cid, f"/repos/{owner}/{repo}/contents/.github/workflows")
    if not isinstance(listing, list):
        return []
    texts: list[str] = []
    for item in listing:
        name = item.get("name", "")
        if item.get("type") != "file" or not name.endswith((".yml", ".yaml")):
            continue
        text = await _read_text(cget, gh, cid, owner, repo, item["path"])
        if text:
            texts.append(text)
    return texts


def _has_unpinned_action(refs: list[str]) -> bool:
    """True if any *external* action ref is not pinned to a 40-hex commit SHA.

    Local (``./…``) and docker (``docker://…``) refs are exempt; reusable workflows and
    marketplace actions (``owner/repo@ref``) must be SHA-pinned (supply-chain hardening).
    """
    for ref in refs:
        if ref.startswith("./") or ref.startswith("docker://") or "/" not in ref:
            continue
        _, _, pinned = ref.partition("@")
        if not _SHA_RE.match(pinned):
            return True
    return False


def _parse_dt(value: object) -> datetime | None:
    from datetime import datetime

    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def _release_pending_days(
    cget: Any, gh: GitHub, cid: str, owner: str, repo: str, branch: str,
    rel: object = None,
) -> int | None:
    """Days of unreleased commits = default-branch HEAD commit date − latest release date.

    None when there is no release (nothing to be behind) or HEAD is not ahead of the
    release. ``rel`` may be the already-fetched ``releases/latest`` body (the release group
    reads it once for both this and the signed-releases signal); when omitted it is fetched.
    """
    if rel is None:
        rel = await cget(gh, cid, f"/repos/{owner}/{repo}/releases/latest")
    if not isinstance(rel, dict):
        return None  # 404 (no releases) → no baseline
    rel_dt = _parse_dt(rel.get("published_at"))
    if rel_dt is None:
        return None
    commit = await cget(gh, cid, f"/repos/{owner}/{repo}/commits/{branch}")
    if not isinstance(commit, dict):
        return None
    head_dt = _parse_dt(((commit.get("commit") or {}).get("committer") or {}).get("date"))
    if head_dt is None or head_dt <= rel_dt:
        return None  # no unreleased commits
    return (head_dt - rel_dt).days


async def _read_text(
    cget: Any, gh: GitHub, cid: str, owner: str, repo: str, path: str
) -> str | None:
    import base64

    from hangar.providers.github.adapter import _FORBIDDEN, _NOT_FOUND, _NOT_MODIFIED

    data = await cget(gh, cid, f"/repos/{owner}/{repo}/contents/{path}")
    if data in (_NOT_FOUND, _NOT_MODIFIED, _FORBIDDEN) or not isinstance(data, dict):
        return None
    if data.get("encoding") == "base64" and data.get("content"):
        try:
            return base64.b64decode(data["content"]).decode("utf-8", "replace")
        except ValueError:
            return None
    return None


async def _read_suppressions(
    cget: Any, gh: GitHub, cid: str, owner: str, repo: str
) -> dict[str, str]:
    """Read + parse the repo's ``.hangar.json`` into a {check_id: reason} suppression map.

    Fail-safe: an absent file, a 403, or malformed content all yield ``{}`` — never an
    exception. Parsing is contained in ``HangarRepoConfig.parse`` (drops unknown ids).
    """
    raw = await _read_text(cget, gh, cid, owner, repo, ".hangar.json")
    if raw is None:
        return {}
    config = HangarRepoConfig.parse(raw)
    return config.suppressions() if config else {}


async def _has_cooldown(cget: Any, gh: GitHub, cid: str, owner: str, repo: str) -> bool:
    """Whether the present update-bot config declares a cooldown.

    Dependabot uses a ``cooldown:`` block in dependabot.yml; Renovate uses
    ``minimumReleaseAge`` (legacy ``stabilityDays``) in its config. Reads the Dependabot
    config first, then the Renovate config — a substring check, matching the lightweight
    approach used for the rest of the file-content checks.
    """
    for path in _DEPENDABOT_CONFIG_FILES:
        content = await _read_text(cget, gh, cid, owner, repo, path)
        if content is not None:
            return "cooldown" in content
    for path in _RENOVATE_CONFIG_FILES:
        content = await _read_text(cget, gh, cid, owner, repo, path)
        if content is not None:
            return "minimumReleaseAge" in content or "stabilityDays" in content
    return False


_MAX_PAGES = 10  # bound a list resource at ~1000 items rather than silently capping at 100


async def _paged(cget: Any, gh: GitHub, cid: str, path: str, params: dict[str, Any]) -> list:
    """Accumulate a paginated list endpoint so a count isn't silently capped at one page."""
    per_page = int(params.get("per_page", 100))
    items: list = []
    for page in range(1, _MAX_PAGES + 1):
        data = await cget(gh, cid, path, {**params, "page": page})
        if not isinstance(data, list) or not data:
            break
        items.extend(data)
        if len(data) < per_page:
            break
    return items


_LINK_NEXT_RE = re.compile(r'<([^>]+)>;\s*rel="next"')


def _next_after_cursor(link_header: str | None) -> str | None:
    """Extract the ``after`` cursor from a ``Link: …; rel="next"`` header, if present."""
    m = _LINK_NEXT_RE.search(link_header or "")
    if not m:
        return None
    from urllib.parse import parse_qs, urlparse

    after = parse_qs(urlparse(m.group(1)).query).get("after")
    return after[0] if after else None


async def _paged_cursor(gh: GitHub, cid: str, path: str, params: dict[str, Any]) -> list:
    """Accumulate a **cursor**-paginated list endpoint (e.g. dependabot alerts).

    Some GitHub list endpoints reject ``?page=`` (400 "Pagination using the page
    parameter is not supported") and instead page via an ``after`` cursor surfaced in the
    ``Link: rel="next"`` header. This follows that cursor (bounded by ``_MAX_PAGES`` like
    ``_paged``) so the count isn't silently capped at one page. A 403/404 (resource
    unreadable/absent) degrades to the items gathered so far rather than aborting.
    """
    from githubkit.exception import RequestFailed

    items: list = []
    after: str | None = None
    for _ in range(_MAX_PAGES):
        page_params = {**params, **({"after": after} if after else {})}
        try:
            resp = await gh.arequest("GET", path, params=page_params)
        except RequestFailed as exc:
            if exc.response.status_code in (403, 404):
                break
            raise
        data = resp.json()
        if not isinstance(data, list) or not data:
            break
        items.extend(data)
        after = _next_after_cursor(resp.headers.get("link"))
        if not after:
            break
    return items


_PR_DETAIL_CAP = 20  # store the most-recent N open PRs for the activity strip

# Bot-login classification is provider-neutral (Renovate runs on Gitea too) and lives in
# ``hangar.providers.bots``; re-exported here so this module stays the GitHub detection
# façade its callers already import from.
from hangar.providers.bots import is_bot_login, pr_kind  # noqa: E402

__all__ = ["interrogate_repo", "is_bot_login", "pr_kind"]


async def _pull_data(
    cget: Any, gh: GitHub, cid: str, owner: str, repo: str
) -> tuple[int, int, list[dict]]:
    """Open-PR count, dependency-bot count (Dependabot + Renovate), and recent PR details."""
    data = await _paged(
        cget, gh, cid, f"/repos/{owner}/{repo}/pulls",
        {"state": "open", "sort": "created", "direction": "desc", "per_page": 100},
    )
    bot = sum(1 for pr in data if is_bot_login((pr.get("user") or {}).get("login")))
    details: list[dict] = []
    for pr in data[:_PR_DETAIL_CAP]:
        login = (pr.get("user") or {}).get("login")
        details.append({
            "title": pr.get("title") or "",
            "number": pr.get("number"),
            "url": pr.get("html_url"),
            "kind": pr_kind(login),
            "created_at": pr.get("created_at"),
            "draft": bool(pr.get("draft")),
        })
    return len(data), bot, details


async def _ci_status(
    cget: Any, gh: GitHub, cid: str, owner: str, repo: str, branch: str
) -> CIStatus:

    data = await cget(gh, cid, f"/repos/{owner}/{repo}/actions/runs",
                      {"branch": branch, "per_page": 1})
    if not isinstance(data, dict):
        return CIStatus.none
    runs = data.get("workflow_runs") or []
    if not runs:
        return CIStatus.none
    conclusion = runs[0].get("conclusion")
    if conclusion == "success":
        return CIStatus.passing
    if conclusion in ("failure", "timed_out", "cancelled"):
        return CIStatus.fail
    return CIStatus.none


async def _alert_counts(gh: GitHub, cid: str, owner: str, repo: str) -> AlertCounts:
    # The dependabot alerts endpoint is cursor-paginated (rejects ?page=), so it needs the
    # Link/after cursor pager rather than the page-number _paged helper.
    data = await _paged_cursor(
        gh, cid, f"/repos/{owner}/{repo}/dependabot/alerts", {"state": "open", "per_page": 100}
    )
    counts = {"critical": 0, "high": 0, "moderate": 0, "low": 0}
    for alert in data:
        sev = ((alert.get("security_advisory") or {}).get("severity")
               or (alert.get("security_vulnerability") or {}).get("severity"))
        if sev in counts:
            counts[sev] += 1
    return AlertCounts(**counts)
