# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Entry point for the semantic version automation tool.

This script performs version bumping, changelog updating, git operations, and GitHub PR creation
based on CI/CD context and branch strategy (e.g., single-branch release workflows).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from auto_semver.adapters.git import GitOps
from auto_semver.adapters.github import GitHubEvent
from auto_semver.cli import bump, finalize, promote, setup
from auto_semver.cli.utils import is_finalized
from auto_semver.config import Config
from auto_semver.setup.check import run_check
from runview import Config as RunviewConfig
from runview import close, get_summary, install, log_group, set_command, status

logger = logging.getLogger(__name__)


def _resolve_command_name(args: argparse.Namespace) -> str:
    """Map parsed args to a short Live-view command label.

    Args:
        args: Parsed CLI namespace.

    Returns:
        Command label for the outer panel title.
    """
    if args.command == "promote":
        return "promote"
    if args.command == "setup":
        return "setup"
    return "bump"


def _build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI argument parser.

    Returns:
        Configured ArgumentParser.
    """
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("--github-token", type=str, help="GitHub token")
    parent_parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parent_parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Plain-text forensic log path (default: auto-semver.log)",
    )
    parent_parser.add_argument(
        "--log-style",
        choices=("auto", "rich", "plain", "github"),
        default="auto",
        help="Run presentation style (default: auto)",
    )
    parent_parser.add_argument(
        "--signed-commits",
        action="store_true",
        help="Create verified commits via the GitHub API (requires App installation token)",
    )

    parser = argparse.ArgumentParser(parents=[parent_parser])
    subparsers = parser.add_subparsers(dest="command")

    promote_parser = subparsers.add_parser(
        "promote",
        help="Promote version between branches",
        parents=[parent_parser],
    )
    promote_parser.add_argument(
        "--dry-run", action="store_true", help="Validate promotion without creating PR"
    )
    promote_parser.add_argument("--from-tag", required=True, help="Specific tag to promote")
    promote_parser.add_argument("--to-branch", required=True, help="Target branch")

    setup_parser = subparsers.add_parser(
        "setup",
        help="Configure GitHub App secrets and scaffold consumer workflows",
        parents=[parent_parser],
    )
    setup_parser.add_argument("--owner", type=str, help="Repository owner")
    setup_parser.add_argument("--repo", type=str, help="Repository name")
    setup_parser.add_argument("--default-branch", type=str, help="Default/base branch")
    setup_parser.add_argument("--client-id", type=str, help="GitHub App Client ID (preferred)")
    setup_parser.add_argument("--app-id", type=str, help="Deprecated alias for --client-id")
    setup_parser.add_argument("--private-key", type=Path, help="Path to App private key PEM")
    setup_parser.add_argument("--dry-run", action="store_true", help="Print plan only")
    setup_parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open prefilled GitHub App registration URL",
    )
    setup_parser.add_argument(
        "--skip-secrets",
        action="store_true",
        help="Skip writing GH_APP_CLIENT_ID and GH_APP_PRIVATE_KEY",
    )
    setup_parser.add_argument(
        "--skip-scaffold",
        action="store_true",
        help="Skip writing auto_semver_config.yml and workflow files",
    )
    setup_parser.add_argument(
        "--check",
        action="store_true",
        help="Validate caller workflow concurrency and config presence",
    )
    return parser


def _init_logging(args: argparse.Namespace, command: str) -> None:
    """Configure runview logging and presentation.

    Args:
        args: Parsed CLI namespace.
        command: Short command label for the outer title.
    """
    log_file = getattr(args, "log_file", None)
    install(
        RunviewConfig(
            app_name="auto-semver",
            log_file_env="AUTO_SEMVER_LOG_FILE",
            default_log_file="auto-semver.log",
            quiet_loggers=("urllib3", "git", "git.cmd", "github", "httpcore", "httpx"),
            style=getattr(args, "log_style", "auto"),
            debug=getattr(args, "debug", False),
            command=command,
            log_file=str(log_file) if log_file is not None else None,
        )
    )


def _run_setup(args: argparse.Namespace) -> None:
    """Run the setup subcommand (check or onboard).

    Args:
        args: Parsed CLI namespace.
    """
    if getattr(args, "check", False):
        get_summary().set("outcome", "check")
        sys.exit(0 if run_check() else 1)
    setup.run(
        owner=args.owner,
        repo=args.repo,
        default_branch=args.default_branch,
        app_id=args.app_id,
        client_id=getattr(args, "client_id", None),
        private_key_path=args.private_key,
        dry_run=args.dry_run,
        open_browser=args.open_browser,
        skip_secrets=args.skip_secrets,
        skip_scaffold=args.skip_scaffold,
    )
    get_summary().set("outcome", "success")


def _run_semver(args: argparse.Namespace) -> None:
    """Run bump, finalize, or promote workflows.

    Args:
        args: Parsed CLI namespace.
    """
    command = _resolve_command_name(args)
    get_summary().set("command", command)

    with log_group("Startup"):
        with status("Loading config and git context..."):
            config = Config()
            gitops = GitOps(
                ensure_safe=True,
                signed_commits=args.signed_commits,
                github_token=args.github_token,
            )

        if args.command == "promote":
            event: GitHubEvent | None = None
            finalized = False
        else:
            with status("Loading GitHub event and detecting workflow..."):
                event = GitHubEvent()
                finalized = is_finalized(config=config, event=event)

    if args.command == "promote":
        promote.run(
            gitops=gitops,
            config=config,
            to_branch=args.to_branch,
            from_tag=args.from_tag,
            dry_run=args.dry_run,
        )
        get_summary().set("outcome", "success")
        return

    assert event is not None
    if finalized:
        set_command("finalize")
        get_summary().set("command", "finalize")
        finalize.run(gitops=gitops, event=event, config=config, github_token=args.github_token)
    else:
        bump.run(gitops=gitops, event=event, config=config, github_token=args.github_token)
    get_summary().set("outcome", "success")


# TODO: Research about click package for CLI
def main() -> None:
    """
    Automating semantic versioning and release processes.

    This script performs the following tasks:
        1. Parse CLI args
        2. Setup logging/config
        3. Determine branch + SHA from GitHub if missing
        4. Bump version + set suffix
        5. Update version files
        6. Create release branch + commit changes
        7. Update changelog
        8. Push branch + open PR

    Command-line Arguments:
    - `--github-token`: GitHub token for authentication (required).
    - `--debug`: Enables debug logging if specified.
    - `--log-file`: Plain-text forensic log path.
    - `promote`: Subcommand for manual promotion.
        - `--from-branch`: Source branch (required).
        - `--to-branch`: Target branch (required).
        - `--dry-run`: Validate without creating PR.

    Raises:
    - SystemExit: With code 1 on failure or cancellation.
    """
    args = argparse.Namespace(debug=False)
    view_started = False
    try:
        # Filter out empty arguments that might come from GitHub Actions expressions
        sys.argv = [arg for arg in sys.argv if arg]

        parser = _build_parser()
        args = parser.parse_args()
        command = _resolve_command_name(args)

        if args.command == "setup":
            _init_logging(args, "setup")
            view_started = True
            _run_setup(args)
            return

        if args.command != "promote" and not args.github_token:
            parser.error("the following arguments are required: --github-token")

        _init_logging(args, command)
        view_started = True
        _run_semver(args)
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        get_summary().set("outcome", "cancelled")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        get_summary().set("outcome", "failed")
        if getattr(args, "debug", False):
            logger.exception("Full traceback:")
        sys.exit(1)
    finally:
        if view_started:
            close()
