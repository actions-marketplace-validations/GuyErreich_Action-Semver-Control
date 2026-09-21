#!/usr/bin/env python3
# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Validate GitHub App installation tokens against the stateless format rollout.

Mints an installation access token with the temporary override header
``X-GitHub-Stateless-S2S-Token`` and exercises the same consumer paths used
by Action-Semver-Control workflows (GH CLI, git HTTPS remote, REST API).

See docs/TOKEN_FORMAT.md and:
https://github.blog/changelog/2026-05-15-github-app-installation-tokens-per-request-override-header/
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Literal

import jwt

API_VERSION = "2022-11-28"
GITHUB_API_URL = os.environ.get("GITHUB_API_URL", "https://api.github.com")
STATELESS_MIN_LENGTH = 400
STATELESS_JWT_DOT_COUNT = 2
StatelessMode = Literal["enabled", "disabled"]


def create_app_jwt(*, app_id: str, private_key: str) -> str:
    """Create a short-lived JWT for GitHub App authentication."""
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 600, "iss": app_id}
    encoded = jwt.encode(payload, private_key, algorithm="RS256")
    return encoded if isinstance(encoded, str) else encoded.decode("ascii")


def _github_request(
    *,
    method: str,
    path: str,
    app_jwt: str,
    extra_headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{GITHUB_API_URL.rstrip('/')}{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {app_jwt}",
        "X-GitHub-Api-Version": API_VERSION,
    }
    if extra_headers:
        headers.update(extra_headers)

    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return {} if not raw else json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {method} {path} failed ({exc.code}): {detail}") from exc


def get_installation_id(*, app_jwt: str, owner: str, repo: str) -> int:
    """Return the installation ID for a repository."""
    payload = _github_request(
        method="GET", path=f"/repos/{owner}/{repo}/installation", app_jwt=app_jwt
    )
    installation_id = payload.get("id")
    if not isinstance(installation_id, int):
        raise RuntimeError(f"Unexpected installation response: {payload!r}")
    return installation_id


def mint_installation_token(*, app_jwt: str, installation_id: int, mode: StatelessMode) -> str:
    """Mint an installation access token, forcing stateless or stateful format."""
    payload = _github_request(
        method="POST",
        path=f"/app/installations/{installation_id}/access_tokens",
        app_jwt=app_jwt,
        extra_headers={"X-GitHub-Stateless-S2S-Token": mode},
        body={},
    )
    token = payload.get("token")
    if not isinstance(token, str) or not token:
        raise RuntimeError(f"Unexpected access token response: {payload!r}")
    return token


def assert_token_shape(token: str, mode: StatelessMode) -> None:
    """Validate token prefix and shape for the requested rollout mode."""
    if not token.startswith("ghs_"):
        msg = f"Expected ghs_ prefix, got length {len(token)}"
        raise ValueError(msg)

    body = token[4:]
    dot_count = body.count(".")

    if mode == "enabled":
        if len(token) < STATELESS_MIN_LENGTH:
            msg = f"Stateless token too short ({len(token)} chars); expected ~520"
            raise ValueError(msg)
        if dot_count != STATELESS_JWT_DOT_COUNT:
            msg = f"Stateless token expected {STATELESS_JWT_DOT_COUNT} dots after prefix, found {dot_count}"
            raise ValueError(msg)
        return

    if dot_count != 0:
        msg = f"Stateful token must not contain dots, found {dot_count}"
        raise ValueError(msg)


def validate_consumers(*, token: str, owner: str, repo: str) -> None:
    """Exercise GH CLI, REST API, and git HTTPS auth with the minted token."""
    env = {**os.environ, "GH_TOKEN": token}

    subprocess.run(
        ["gh", "api", "user", "--jq", ".login"],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}", "--jq", ".full_name"],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    remote_url = f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"
    subprocess.run(
        ["git", "ls-remote", remote_url, "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("enabled", "disabled"),
        required=True,
        help="Force stateless (enabled) or stateful (disabled) token format",
    )
    parser.add_argument("--owner", required=True, help="Repository owner")
    parser.add_argument("--repo", required=True, help="Repository name")
    parser.add_argument(
        "--app-id",
        default=None,
        help="GitHub App ID or Client ID (defaults to GH_APP_CLIENT_ID or GH_APP_ID)",
    )
    parser.add_argument(
        "--private-key",
        default=os.environ.get("GH_APP_PRIVATE_KEY"),
        help="GitHub App private key PEM (or set GH_APP_PRIVATE_KEY)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Mint, validate shape, and exercise consumer paths for one token mode."""
    args = parse_args(argv)
    app_id = args.app_id or os.environ.get("GH_APP_CLIENT_ID") or os.environ.get("GH_APP_ID")
    if not app_id or not args.private_key:
        print(
            "GH_APP_CLIENT_ID (or GH_APP_ID) and GH_APP_PRIVATE_KEY are required",
            file=sys.stderr,
        )
        return 1

    mode: StatelessMode = args.mode
    print(f"Minting installation token with X-GitHub-Stateless-S2S-Token: {mode}")

    app_jwt = create_app_jwt(app_id=str(app_id), private_key=args.private_key)
    installation_id = get_installation_id(app_jwt=app_jwt, owner=args.owner, repo=args.repo)
    token = mint_installation_token(app_jwt=app_jwt, installation_id=installation_id, mode=mode)

    assert_token_shape(token, mode)
    print(f"Token shape OK ({mode}): length={len(token)}, dots={token[4:].count('.')}")

    validate_consumers(token=token, owner=args.owner, repo=args.repo)
    print("Consumer checks passed (gh api, REST, git ls-remote)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
