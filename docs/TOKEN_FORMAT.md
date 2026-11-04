# GitHub App installation token format

GitHub is rolling out **stateless** installation tokens for GitHub Apps. New tokens use the `ghs_` prefix with a JWT payload (~520 characters, two dots after the prefix). Classic **stateful** tokens remain shorter opaque strings with no dots.

Action-Semver-Control treats installation tokens as **opaque strings** — no hardcoded length or format assumptions in application code. Workflows pass tokens to `gh`, git HTTPS remotes, PyGithub, and the action unchanged.

## Audit summary

| Component | Compatible? | Notes |
|-----------|-------------|-------|
| `GitOps` / CLI | Yes | Token passed to PyGithub and `--github-token` without parsing |
| Git HTTPS remote | Yes | `x-access-token:TOKEN@github.com/...`; `@` delimiter; JWT dots are safe |
| Token storage | N/A | Tokens are ephemeral in CI; nothing persisted |
| `create-github-app-token` | Yes | Passes through whatever GitHub returns |
| Gitleaks (consumers) | Update rules | Default `ghs_[0-9a-zA-Z]{36}` misses stateless JWT leaks |

Recommended regex for both formats: `ghs_[A-Za-z0-9\.\-_]{36,}`

## Validate before rollout

GitHub provides a **temporary** override header on token minting:

```http
POST /app/installations/:installation_id/access_tokens
X-GitHub-Stateless-S2S-Token: enabled   # force stateless JWT format
X-GitHub-Stateless-S2S-Token: disabled  # force classic opaque format
```

Do **not** add this header to production [`app-authentication`](../.github/actions/app-authentication/action.yml). Use it only for validation.

### Run the validation workflow

1. Configure `GH_APP_CLIENT_ID` (repository variable) and `GH_APP_PRIVATE_KEY` (secret) — see README / SETUP.md.
2. Open **Actions → Validate Stateless App Token → Run workflow**.
3. Run with `mode=enabled`, then `mode=disabled`. Both must pass.

Or locally (requires App credentials and `gh` CLI):

```bash
uv sync
export GH_APP_CLIENT_ID=Iv1.xxxxxxxx
export GH_APP_PRIVATE_KEY='-----BEGIN RSA PRIVATE KEY-----...'
uv run python scripts/validate_stateless_token.py \
  --mode enabled \
  --owner GuyErreich \
  --repo Action-Semver-Control
```

The script checks token shape and exercises `gh api`, REST, and `git ls-remote` — the same paths used by semver workflows.

## References

- [April 2026 notice](https://github.blog/changelog/2026-04-24-notice-about-upcoming-new-format-for-github-app-installation-tokens/)
- [Per-request override header](https://github.blog/changelog/2026-05-15-github-app-installation-tokens-per-request-override-header/)

The override header will be deprecated once rollout completes; remove any test-only usage after both formats are validated.
