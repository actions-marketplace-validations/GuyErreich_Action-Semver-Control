# Auto Semver Action

A custom GitHub Action written in Python to automatically bump semantic versioning, update changelogs, and create Pull Requests — fully configurable.

[![GitHub Marketplace](https://img.shields.io/badge/Marketplace-Auto%20Semver%20Bumper-blue?logo=github)](https://github.com/marketplace/actions/auto-semver-bumper)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Pin major v1 tag](https://img.shields.io/badge/pin-v1-green)](docs/SETUP.md#pinning-policy)
[![CI](https://github.com/GuyErreich/Action-Semver-Control/actions/workflows/ci.yml/badge.svg)](https://github.com/GuyErreich/Action-Semver-Control/actions/workflows/ci.yml)

## Usage

Marketplace install snippets often pin an exact release (for example `@1.6.3`). Prefer the floating major tag for compatible updates:

```yaml
- name: Auto Semver Bumper
  uses: GuyErreich/Action-Semver-Control@v1
```

See [Pinning policy](docs/SETUP.md#pinning-policy) for the floating `v1` tag vs exact semver vs SHA pins.

## Quickstart

**New to this action?** Follow [docs/SETUP.md](docs/SETUP.md) end-to-end (GitHub App, secrets, workflows).

**Required:** Caller workflows must include a [concurrency queue](docs/SETUP.md#concurrent-merges--bump-queue) when merging multiple PRs to the same branch.

### One-command setup (recommended)

From your consumer repository:

```bash
uvx --from git+https://github.com/GuyErreich/Action-Semver-Control auto-semver setup
```

### Add workflows without the CLI

1. **[Register a GitHub App](https://github.com/settings/apps/new?name=Auto+Semver+Bot&description=Signed+commits+and+PRs+for+Action-Semver-Control&url=https%3A%2F%2Fgithub.com%2FGuyErreich%2FAction-Semver-Control&public=true&webhook_active=false&contents=write&pull_requests=write)** — install it on your repo, set variable `GH_APP_CLIENT_ID` and secret `GH_APP_PRIVATE_KEY`.
2. **Add a caller workflow** — copy [src/auto_semver/setup/scaffolds/auto-semver.caller.yml](src/auto_semver/setup/scaffolds/auto-semver.caller.yml) to `.github/workflows/auto-semver.yml`.
3. **Add config** — copy [src/auto_semver/setup/scaffolds/auto_semver_config.yml](src/auto_semver/setup/scaffolds/auto_semver_config.yml) to `auto_semver_config.yml` and edit branch suffixes.

Regenerate prefilled “add workflow” links for your repo:

```bash
python scripts/generate_onboarding_links.py --owner YOUR_ORG --repo YOUR_REPO --branch master
```

Pin reusable workflows at the floating major tag `v1` (for example `.../semver-bump.reusable.yml@v1`). See [Pinning policy](docs/SETUP.md#pinning-policy).

## Features
- Auto bump `major`, `minor`, or `patch` depending on branch type
- Add suffixes (`-dev`, `-rc`) depending on the target branch
- Auto-create release branches
- Auto-close old release PRs (single branch mode)
- Label bump PRs automatically (`semver-bump`)
- 100% typed Python (>=3.12)
- No subprocess — uses GitPython and Requests libraries only
- Fully Dockerized for clean CI/CD usage
- Comprehensive test coverage with pytest and pyfakefs
- Modern Python tooling (ruff, mypy, pre-commit, gitleaks secret scan)

## CLI Usage

The action is primarily designed to run in CI/CD, but the CLI can be used for manual operations.

### Manual Promotion
To manually promote a version from one branch to another (e.g., `dev` -> `staging`):

```bash
auto-semver --github-token <TOKEN> promote --from-branch dev --to-branch staging
```

Options:
- `--dry-run`: Validate the promotion without creating a PR.

## Configuration (`auto_semver_config.yml`)

```yaml
start_version: "0.1.0"

suffixes:
  dev: "-dev"
  staging: "-rc"
  main: ""

files_to_update:
  - "version.txt"
  - "README.md"
```

### Commit Parsing & Grouping

The action supports three intelligent parsing strategies to organize your changelogs and release notes effectively. Grouping is configured via the `commit_groups` section in your config file.

#### 1. Sectioned Changes (Type 3 - Highest Priority)
Best for large commits covering multiple areas. Use Markdown headers in your commit body.

**Commit Message:**
```text
feat: major overhaul of auth system

### ✨ Features
- Added OIDC provider support
- Implemented refresh token rotation

### 🐛 Bug Fixes
- Fixed race condition in login flow
- Resolved session timeout issue
```

**Result:**
- The bullet points under `### ✨ Features` will appear in the "Features" group.
- The bullet points under `### 🐛 Bug Fixes` will appear in the "Bug Fixes" group.

#### 2. Bullet Points (Type 2)
Great for listing multiple related changes without specific sections.

**Commit Message:**
```text
fix: update dependency handling

- Upgrade pydantic to v2
- Remove deprecated validation logic
- Fix circular import in config module
```

**Result:**
- Each bullet point is treated as an individual change.
- Each point is matched against your `auto_semver_config.yml` patterns independently.

#### 3. Header Only (Type 1 - Default)
Standard conventional commit format.

**Commit Message:**
```text
fix(api): handle missing auth header gracefully
```

**Result:**
- The entire header is matched against config patterns.
- Grouped based on the prefix (e.g., `fix:` goes to "Bug Fixes").

### Configuration Example

Define how regex patterns map to groups in `auto_semver_config.yml`:

```yaml
commit_groups:
  - title: "✨ Features"
    patterns:
      - "^feat:"
      - "^add:"
    priority: 1

  - title: "🐛 Bug Fixes"
    patterns:
      - "^fix:"
      - "^resolve:"
    priority: 2
```

## License

MIT — see [LICENSE](LICENSE).
