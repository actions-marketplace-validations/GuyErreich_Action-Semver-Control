# Contributing

Thanks for helping improve Action-Semver-Control.

## Before you start

1. Read [docs/SETUP.md](docs/SETUP.md) for how the action is meant to be adopted.
2. Open an issue for larger design changes before a big PR.
3. Use a feature branch off `dev` (default branch). Do not push straight to `dev` / `staging` / `master`.

## Development

```bash
uv sync
uv run pre-commit install
uv audit --frozen
uv run pytest
uv run ruff check .
uv run mypy src
```

Or via Task: `task install && task audit && task test && task lint && task type-check`.

## Pull requests

- Prefer conventional titles: `feat:`, `fix:`, `docs:`, `chore:`, etc. Those titles drive changelog grouping (`summary_mode: header_only`).
- Do **not** put bare `@v1` in PR titles or changelog prose — GitHub autolinks it to an unrelated user. Write **v1 tag** or `` `v1` `` instead. YAML examples with `...@v1` are fine.
- Keep PRs focused; include tests for behavior changes.
- CI must be green (Python including `uv audit`, license-check, CodeQL, Gitleaks).

## Releases

Maintainers handle version bumps via Auto Semver. After a production GitHub Release, update the Marketplace listing with `?marketplace=true` (see [docs/MARKETPLACE.md](docs/MARKETPLACE.md)).

## Security

Report vulnerabilities privately — see [SECURITY.md](SECURITY.md).
