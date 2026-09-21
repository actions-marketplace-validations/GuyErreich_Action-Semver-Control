# Workspace Agent Notes

This file defines global working rules for the repository.

## Core Rules

- Reuse before creating: check existing modules, helpers, and patterns before adding new ones.
- Prefer absolute imports under `auto_semver.*` (no forced relative imports inside the package).
- Keep product logic in `core/`, VCS I/O in `adapters/git/`, and YAML schema in `config/`.

## Config entry point

- **Only public import path:** `from auto_semver.config import Config, …`
- `Config` is the runtime entry point (load / access configuration).
- Schema types (`CommitGroupConfig`, `ConfigData`, `PromotionRule`, …) are re-exported from `config/__init__.py` for **typing** annotations (prefer `TYPE_CHECKING`) and for the rare cases that must construct those values while applying config.
- **Never** import `auto_semver.config._models` (or any submodule of it) outside the `config/` package. `_models` is private packaging for schema definitions; consumers must not reach into it.
- Inside `config/` only: `config.py` and `_models/*` may import `_models` modules directly.

## Folder map (src/)

- `auto_semver/config/` — `Config` loader + private `_models` schema (public via `__init__.py`)
- `auto_semver/core/` — commits, semver, changelog, PR content
- `auto_semver/adapters/git/` — git operations (`GitOpsBase` + focused ops modules)
- `auto_semver/cli/` — CLI entrypoints
- `auto_semver/templates/` — Jinja engine + shared template utils
- `auto_semver/setup/` — scaffolds / init helpers
- `runview/` — structured run presentation (Reporter + renderers); must never import `auto_semver`

## Validate

- Base branch for branch/PR diffs: `dev`.
- Lint: `task lint` — 0 errors required.
- Type-check: `task type-check` — must succeed.
- Tests: `task test` — must succeed.
- Audit: `task audit` — must succeed when dependencies/lockfile change.

CI and milestone skills read these commands and the base branch from this block.

- Run lint, type-check, and tests at review / commit / PR milestones.
- Record pass/fail from raw shell exit codes.

## Review scope

When reviewing, materialize the full surface: the tier diff (for PR/push prefer `merge-base...HEAD` against `dev`), plus the nearest `AGENT.md` for every changed path (leaf → root), plus the skills routed by the changed file types.
