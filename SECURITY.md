# Security Policy

## Supported versions

Security fixes are applied to the latest production release on `master` and reflected on the floating major tag `v1`.

| Version | Supported |
|---------|-----------|
| Latest `1.x` / tag `v1` | Yes |
| Older patch releases | Best-effort only |

## Reporting a vulnerability

Please **do not** open a public issue for security reports.

Use GitHub’s **private vulnerability reporting**:

1. Open [Security → Advisories](https://github.com/GuyErreich/Action-Semver-Control/security/advisories) for this repository, or  
2. Use **Report a vulnerability** on the Security tab.

Include:

- Affected version / tag (or commit SHA)
- Impact and reproduction steps
- Whether you know of public exploitation

You should receive an acknowledgment within a few days. After a fix is available, we prefer coordinated disclosure.

## Scope

In scope: the GitHub Action, reusable workflows, and Python package in this repository.

Out of scope: consumer repositories that *call* this action, third-party Actions we pin by SHA, and GitHub platform issues.

## Actions supply chain

This repository keeps **SHA pinning required** for GitHub Actions (`sha_pinning_required: true`). Top-level and nested `uses:` must resolve to full-length commit SHAs.

Third-party composites that still pin nested actions by tag (today: `apache/skywalking-eyes` → `actions/setup-go@…`) cannot be invoked via `uses:` under that policy. License header checks therefore run the checker in a **digest-pinned container** (`apache/skywalking-eyes:…@sha256:…`) rather than as a nested Action. See [docs/SETUP.md](docs/SETUP.md#why-license-check-uses-docker-sha-pinning) and [#263](https://github.com/GuyErreich/Action-Semver-Control/issues/263).
