# Security Policy

Hangar is a self-hosted, single-operator control plane. It holds provider
credentials (encrypted at rest with a Fernet key) and runs fail-closed behind a
reverse-proxy SSO layer, so security reports are taken seriously.

## Supported versions

Hangar ships from `main` as a rolling release; only the **latest** published
image on GHCR (`ghcr.io/get2knowio/hangar`) receives security fixes. Please
reproduce any report against the most recent release before filing.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately through GitHub's
[private vulnerability reporting](https://github.com/get2knowio/hangar/security/advisories/new)
("Report a vulnerability" on the Security tab). Include:

- affected version / image digest,
- a description of the issue and its impact,
- steps to reproduce or a proof of concept,
- any suggested remediation.

You can expect an initial acknowledgement within **7 days**. Once a fix is
released, we will credit reporters who wish to be named in the advisory.

## Scope

In scope: the Hangar backend and frontend, the published container image, and
the example deployment stack under `deploy/`. Out of scope: vulnerabilities in
upstream vendor SDKs or GitHub/Gitea themselves (please report those upstream),
and issues that require a misconfigured deployment that ignores the hardening
guidance in [CONTRIBUTING.md](CONTRIBUTING.md).
