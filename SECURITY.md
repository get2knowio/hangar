# Security Policy

Hangar is a self-hosted, single-operator fleet control plane that handles provider
credentials and enforces security gates on the repositories it manages. We take
security issues seriously and appreciate responsible disclosure.

## Supported versions

Hangar is released from `main` as `0.x` versions. Security fixes are applied to the
latest released version only; please upgrade to the most recent release before
reporting an issue you cannot reproduce there.

| Version | Supported |
| ------- | --------- |
| Latest `0.x` release | ✅ |
| Older releases | ❌ |

## Reporting a vulnerability

**Please do not open a public issue for security vulnerabilities.**

Report privately through GitHub's built-in advisory workflow:

1. Go to the [Security tab](https://github.com/get2knowio/hangar/security/advisories)
   of this repository.
2. Click **Report a vulnerability** to open a private security advisory.

If you are unable to use GitHub Security Advisories, you may email the maintainer
at **pofallon@users.noreply.github.com** with the details.

Please include, where possible:

- A description of the vulnerability and its impact.
- Steps to reproduce (proof-of-concept, affected endpoints/config, or a minimal repro).
- The Hangar version (or commit) and relevant deployment details (forward-auth mode,
  provider connection type).

## Disclosure process

- We aim to acknowledge a report within **5 business days**.
- We will work with you to confirm the issue, determine impact, and prepare a fix.
- Once a fix is released, we will publish a security advisory crediting the reporter
  (unless you prefer to remain anonymous).

## Scope

Security-relevant areas include, but are not limited to:

- The forward-auth middleware and startup fail-closed gate.
- Webhook HMAC verification.
- Credential encryption at rest (Fernet) and handling of decrypted credentials.
- The provider seam and any path that performs writes (PR-first remediation).

Thank you for helping keep Hangar and its operators safe.
