# Release setup for Action-Semver-Control

This guide walks through adopting Action-Semver-Control in a repository you do not maintain personally. No tribal knowledge required.

## What you need

| Item | Purpose |
|------|---------|
| **GitHub App** (yours) | Verified commits and PRs that satisfy branch protection |
| **`GH_APP_CLIENT_ID`** variable | App **Client ID** from the app settings page (not the numeric App ID) |
| **`GH_APP_PRIVATE_KEY`** secret | PEM contents from **Generate a private key** |
| **`auto_semver_config.yml`** | Branch suffixes, version files, changelog groups |
| **Caller workflows** | Thin wrappers that invoke reusable workflows at the floating `v1` tag |

Action-Semver-Control is listed on the [GitHub Marketplace](https://github.com/marketplace/actions/auto-semver-bumper) for discovery. Marketplace does not install secrets or workflows — follow this guide after adding the action.

## Quick setup (CLI)

From your consumer repository:

```bash
uvx --from git+https://github.com/GuyErreich/Action-Semver-Control auto-semver setup
```

The wizard will:

1. Print a **prefilled GitHub App registration URL**
2. Prompt for App **Client ID** and private key path
3. Write `GH_APP_CLIENT_ID` via `gh variable set` and `GH_APP_PRIVATE_KEY` via `gh secret set`
4. Scaffold `auto_semver_config.yml` and caller workflows (if missing)

Flags: `--dry-run`, `--skip-secrets`, `--skip-scaffold`, `--open-browser`.

## Manual setup

### 1. Register the GitHub App

Open the prefilled registration URL (permissions: **Contents** and **Pull requests** read/write, webhooks off):

```
https://github.com/settings/apps/new?name=Auto+Semver+Bot&description=Signed+commits+and+PRs+for+Action-Semver-Control&url=https%3A%2F%2Fgithub.com%2FGuyErreich%2FAction-Semver-Control&public=true&webhook_active=false&contents=write&pull_requests=write
```

Or regenerate links for your repo:

```bash
python scripts/generate_onboarding_links.py --owner YOUR_ORG --repo YOUR_REPO --branch master
```

Note the **Client ID** (preferred for Actions; distinct from the numeric App ID and the installation ID). Generate and download a **private key** (`.pem`).

### 2. Install the app on your repository

App settings → **Install App** → select your account/org → grant access to the target repository.

### 3. Set repository credentials

```bash
gh variable set GH_APP_CLIENT_ID --repo YOUR_ORG/YOUR_REPO --body 'Iv1.xxxxxxxx'
gh secret set GH_APP_PRIVATE_KEY --repo YOUR_ORG/YOUR_REPO
```

Paste the Client ID (public identifier) as a variable and the full PEM file contents as a secret (including `BEGIN` / `END` lines).

> **Migration note:** Older setups used `secrets.GH_APP_ID` with `create-github-app-token`'s deprecated `app-id` input. Switch callers to `vars.GH_APP_CLIENT_ID` and the `client-id` input.

### 4. Add caller workflows

**Option A — GitHub UI (prefilled PR):**

Use the deep links from `scripts/generate_onboarding_links.py` or the CLI setup output. They open the web editor with workflow YAML already filled in.

**Option B — copy minimal callers:**

`.github/workflows/auto-semver.yml`:

```yaml
name: Auto Semver Bump
on:
  pull_request:
    types: [closed]
    branches: [dev, staging, master]
permissions:
  contents: write
  pull-requests: write
# Required when multiple PRs merge close together — see "Concurrent merges" below.
concurrency:
  group: auto-semver-bump-${{ github.repository }}-${{ github.event.pull_request.base.ref }}
  cancel-in-progress: false
jobs:
  bump:
    if: github.event.pull_request.merged == true
    uses: GuyErreich/Action-Semver-Control/.github/workflows/semver-bump.reusable.yml@v1
    with:
      client-id: ${{ vars.GH_APP_CLIENT_ID }}
    secrets:
      app-private-key: ${{ secrets.GH_APP_PRIVATE_KEY }}
```

Validate locally:

```bash
auto-semver setup --check
```

`.github/workflows/promote.yml` (optional manual promotion):

```yaml
name: Manual Semver Promotion
on:
  workflow_dispatch:
    inputs:
      from_tag:
        required: true
        type: string
      to_branch:
        required: true
        default: staging
        type: choice
        options: [staging, master]
      dry_run:
        required: false
        default: false
        type: boolean
permissions:
  contents: write
jobs:
  promote:
    uses: GuyErreich/Action-Semver-Control/.github/workflows/semver-promote.reusable.yml@v1
    with:
      from_tag: ${{ inputs.from_tag }}
      to_branch: ${{ inputs.to_branch }}
      dry_run: ${{ inputs.dry_run }}
      client-id: ${{ vars.GH_APP_CLIENT_ID }}
    secrets:
      app-private-key: ${{ secrets.GH_APP_PRIVATE_KEY }}
```

### 5. Configure `auto_semver_config.yml`

Start from [`src/auto_semver/setup/scaffolds/auto_semver_config.yml`](../src/auto_semver/setup/scaffolds/auto_semver_config.yml). Adjust:

- `suffixes` — map your branch names (`dev`, `staging`, `master`, etc.)
- `version_files` — files Action-Semver-Control may update directly (`version.txt`, `pyproject.toml`, JSON manifests such as `package.json` / Cursor `plugin.json`). Lines like `"version": "1.2.3",` (trailing comma) are supported. **`uv.lock` is not included** — after a version bump, run `uv lock` (or Dependabot) so the editable package version in the lockfile matches `pyproject.toml`.
- `promotions` — which channels auto-promote
- `commit_groups` — changelog grouping; use `summary_mode: header_only` to avoid noisy squash bodies (see README)
- `release.strategy` — `single` (default) or `multi` for multiple open release PRs
- `release.branch_prefix` — default `auto-semver/release/` (owned branches only)
- `bump.mode` — `classic` (default) or `cumulative` (opt-in; see [TROUBLESHOOTING.md](TROUBLESHOOTING.md))

## Concurrent merges & bump queue

When several PRs merge in quick succession (batch merge, merge queue, or rapid merges), bump workflows must **queue** — not run in parallel.

Add this block to your **caller** workflow (already included in scaffolded `auto-semver.yml`):

```yaml
concurrency:
  group: auto-semver-bump-${{ github.repository }}-${{ github.event.pull_request.base.ref }}
  cancel-in-progress: false
```

- Same target branch (`dev`, `staging`, `master`) shares one queue.
- `cancel-in-progress: false` is critical: cancelled runs lose their bump.

Run `auto-semver setup --check` to fail fast if the block is missing.

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for version regression and two-phase release flow.

### 6. Create channel branches

```bash
git checkout -b dev && git push -u origin dev
git checkout -b staging && git push -u origin staging
```

Keep `master` (or `main`) as production. Merge feature work into `dev`.

## Pinning policy

| Pin | When to use |
|-----|-------------|
| `v1` (as `...@v1`) | **Recommended** — floating major tag, updated on each production release |
| `@1.3.14` | Exact semver for reproducibility |
| `@<sha>` | Maximum control; pin in reusable workflow `action-ref` input |

Production releases of Action-Semver-Control force-update the `v1` tag to the latest stable release.

## Troubleshooting

See **[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)** for version regressions, noisy release PRs, stale branches, and bump modes.

### Workflow fails immediately: "Missing GitHub App credentials"

Set `GH_APP_CLIENT_ID` (repository variable) and `GH_APP_PRIVATE_KEY` (secret). Re-run setup:

```bash
uvx --from git+https://github.com/GuyErreich/Action-Semver-Control auto-semver setup
```

### `create-github-app-token` fails

- Confirm the app is **installed** on this repository (not just created).
- Confirm `GH_APP_CLIENT_ID` is the App **Client ID** (not the installation ID or the deprecated numeric App ID secret).
- Confirm the PEM secret includes header/footer lines.

### Reusable workflow not found at tag `v1`

The `v1` tag is created on the first **production** release of Action-Semver-Control. Until then, pin `action-ref` to a commit SHA or release tag in your caller workflow, or wait for `v1` to exist.

### Commits blocked by branch protection

Reusable bump/promote workflows default **`signed-commits: true`**, which creates GitHub-verified App commits:

- **Default:** GraphQL `createCommitOnBranch` for ordinary `100644` files (lock, changelog, version files).
- **Fallback ([#286](https://github.com/GuyErreich/Action-Semver-Control/issues/286)):** Git Database REST (`blob` → `tree` with explicit `100644` / `100755` / `120000` → `commit` → `ref`) when the change includes executables, symlinks, or a destination↔source **mode** change GraphQL cannot apply. Author/committer/signature are omitted so GitHub App-signs the commit; ASC refuses to move the branch unless `verification.verified` is true.

- Use a **GitHub App** installation token (not `GITHUB_TOKEN` alone).
- The Docker action input `signed-commits` still defaults to `false` for backward compatibility when you call `uses: GuyErreich/Action-Semver-Control@v1` directly — pass `signed-commits: true` (or use the reusable workflows).
- Opt out in a reusable caller with `signed-commits: false` only if you do not need verified signatures.

If merges still fail with **Cannot update this protected ref** / **Commits must have verified signatures**, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md#merging-is-blocked--commits-must-have-verified-signatures).

### Auto-promote is not a PR that waits on checks

With `promotions[].auto_promote: true`, finalize does **not** open a promotion PR. After tagging the source (e.g. `X.Y.Z-dev`), ASC uses the App installation token (ruleset **bypass**) to update the target branch and create the destination tag (e.g. `X.Y.Z-rc`) in one shot — GraphQL or verified REST as above.

Required status checks on the destination branch therefore **cannot** block the promote. Consumer publish workflows that gate on `*.*.*-rc` can refuse to create a GitHub Release, but the branch and tag already exist. Source CI on `-dev` also does not prove the `-rc` tree (promote rewrites version metadata and may change file modes).

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md#auto-promotion-failed-or-staging-did-not-deploy).

### License check before Auto Semver

`license-check` (workflow **License Header Check**) must be a **required status check** on `dev` and `master`.

Auto Semver Bump runs only after a PR is merged. Requiring `license-check` on those branches means:

1. PRs (including annual copyright-year updates) cannot merge until SPDX headers pass.
2. Auto Semver then runs on the merged tree that already includes any license/header file updates.

Configure under **Settings → Rules → Rulesets** (or classic branch protection): require status check **`license-check`**.

The **Copyright Year Update** workflow (`copyright-year.yml`) opens a PR to `dev` each New Year; merge it only after `license-check` is green.

## Architecture

```mermaid
flowchart LR
  merge[PR merged to dev] --> caller[auto-semver.yml caller]
  caller --> reusable[semver-bump.reusable.yml@v1]
  reusable --> preflight[Preflight secrets]
  preflight --> appAuth[app-authentication]
  appAuth --> action[Action-Semver-Control@v1]
  action --> releasePR[Release PR + tag]
```
