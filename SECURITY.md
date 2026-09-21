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
