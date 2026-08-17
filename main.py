"""
main.py - CLI entrypoint for the AI Code Review Bot.

Usage:
    python main.py --repo owner/repo --pr 42
    python main.py --repo owner/repo --pr 42 --dry-run
    python main.py --repo owner/repo --pr 42 --token ghp_xxx --min-severity minor
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Optional

from dotenv import load_dotenv

import config
from github_client import (
    get_pr_files,
    get_pr_head_sha,
    post_inline_comments,
    post_review_comment,
)
from models import Finding
from reviewer import review_diff

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI Code Review Bot — reviews a GitHub PR using Claude."
    )
    parser.add_argument(
        "--repo",
        required=True,
        metavar="OWNER/NAME",
        help="GitHub repository in owner/name format (e.g. acme/backend).",
    )
    parser.add_argument(
        "--pr",
        required=True,
        type=int,
        metavar="NUMBER",
        help="Pull request number to review.",
    )
    parser.add_argument(
        "--token",
        default=None,
        metavar="GHTOKEN",
        help="GitHub personal access token (defaults to GITHUB_TOKEN env var).",
    )
    parser.add_argument(
        "--anthropic-key",
        default=None,
        metavar="API_KEY",
        help="Anthropic API key (defaults to ANTHROPIC_API_KEY env var).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print findings to stdout instead of posting them to GitHub.",
    )
    parser.add_argument(
        "--min-severity",
        choices=["critical", "warning", "minor"],
        default=config.MIN_SEVERITY_TO_POST,
        help=(
            f"Minimum severity level to post as inline comment "
            f"(default: {config.MIN_SEVERITY_TO_POST})."
        ),
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-5",
        metavar="MODEL",
        help="Claude model to use (default: claude-sonnet-4-5).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Enable debug-level logging.",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def dedupe_findings(findings: list[Finding]) -> list[Finding]:
    """Remove duplicate findings with the same (file, line, category) key.

    When duplicates exist the one with the highest severity is kept.
    """
    seen: dict[tuple[str, int, str], Finding] = {}
    for f in findings:
        key = (f.file, f.line, f.category)
        if key not in seen:
            seen[key] = f
        else:
            existing = seen[key]
            if config.SEVERITY_ORDER.get(f.severity, 0) > config.SEVERITY_ORDER.get(existing.severity, 0):
                seen[key] = f
    return list(seen.values())


# ---------------------------------------------------------------------------
# Summary comment builder
# ---------------------------------------------------------------------------


def build_summary(findings: list[Finding], pr_number: int, repo: str, dry_run: bool) -> str:
    """Construct the markdown summary comment body."""
    lines: list[str] = [config.REVIEW_HEADER]

    if not findings:
        lines.append("✅ No significant issues found. LGTM!\n")
        lines.append(config.REVIEW_FOOTER)
        return "".join(lines)

    # Group by severity for the summary table
    by_severity: dict[str, list[Finding]] = {"critical": [], "warning": [], "minor": []}
    for f in findings:
        by_severity.setdefault(f.severity, []).append(f)

    total = len(findings)
    counts = {k: len(v) for k, v in by_severity.items() if v}
    count_str = ", ".join(f"**{v}** {k}" for k, v in counts.items())
    lines.append(f"Found **{total}** issue(s): {count_str}.\n\n")

    # Ordered table
    lines.append("| Severity | Category | File | Line | Issue |\n")
    lines.append("|----------|----------|------|------|-------|\n")

    severity_order = ["critical", "warning", "minor"]
    emoji_map = {"critical": "🔴", "warning": "🟡", "minor": "🔵"}
    for sev in severity_order:
        for f in by_severity.get(sev, []):
            emoji = emoji_map.get(sev, "⚪")
            short_comment = f.comment[:120] + "…" if len(f.comment) > 120 else f.comment
            lines.append(
                f"| {emoji} {sev.capitalize()} | `{f.category}` | `{f.file}` | {f.line} | {short_comment} |\n"
            )

    if dry_run:
        lines.append("\n> ⚠️ **Dry-run mode** — inline comments were NOT posted.\n")

    lines.append(config.REVIEW_FOOTER)
    return "".join(lines)


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


def run(args: argparse.Namespace) -> int:
    """Orchestrate the full review flow. Returns an exit code."""

    # ---- Resolve secrets ---------------------------------------------------
    github_token = args.token or os.environ.get("GITHUB_TOKEN")
    if not github_token:
        logger.error(
            "No GitHub token provided.  Set --token or the GITHUB_TOKEN env var."
        )
        return 1

    anthropic_key = args.anthropic_key or os.environ.get("ANTHROPIC_API_KEY")
    if not anthropic_key:
        logger.error(
            "No Anthropic API key provided.  Set --anthropic-key or the ANTHROPIC_API_KEY env var."
        )
        return 1

    logger.info("Starting review: %s PR #%d", args.repo, args.pr)

    # ---- Fetch PR files ----------------------------------------------------
    try:
        pr_files = get_pr_files(args.repo, args.pr, github_token)
    except Exception as exc:
        logger.error("Failed to fetch PR files: %s", exc)
        return 1

    if not pr_files:
        logger.info("No files changed in PR #%d — nothing to review.", args.pr)
        return 0

    # ---- Filter and cap files ----------------------------------------------
    reviewable = [f for f in pr_files if f.get("patch")]
    skipped_no_patch = len(pr_files) - len(reviewable)
    if skipped_no_patch:
        logger.info("Skipped %d binary/renamed file(s) with no patch.", skipped_no_patch)

    if len(reviewable) > config.MAX_FILES_PER_RUN:
        logger.warning(
            "PR has %d reviewable files; capping at %d (MAX_FILES_PER_RUN).",
            len(reviewable),
            config.MAX_FILES_PER_RUN,
        )
        reviewable = reviewable[: config.MAX_FILES_PER_RUN]

    # ---- Review each file --------------------------------------------------
    all_findings: list[Finding] = []

    for file_info in reviewable:
        filename: str = file_info["filename"]
        patch: str = file_info["patch"]

        logger.info("Reviewing %s …", filename)
        try:
            findings = review_diff(
                filename=filename,
                patch=patch,
                anthropic_api_key=anthropic_key,
                model=args.model,
            )
            all_findings.extend(findings)
        except Exception as exc:
            # Per-file error tolerance — log and continue
            logger.error("Error reviewing %s: %s", filename, exc)

    logger.info("Total findings before dedup: %d", len(all_findings))

    # ---- Dedup -------------------------------------------------------------
    unique_findings = dedupe_findings(all_findings)
    logger.info("Unique findings after dedup: %d", len(unique_findings))

    # ---- Sort by severity (critical first) ---------------------------------
    unique_findings.sort(
        key=lambda f: -config.SEVERITY_ORDER.get(f.severity, 0)
    )

    # ---- Build summary -----------------------------------------------------
    summary_body = build_summary(unique_findings, args.pr, args.repo, args.dry_run)

    # ---- Output / post -----------------------------------------------------
    if args.dry_run:
        print("\n" + "=" * 72)
        print("DRY RUN — Summary comment that would be posted:")
        print("=" * 72)
        print(summary_body)
        print("=" * 72)
        print(f"\n{len(unique_findings)} unique finding(s) total.\n")
        for f in unique_findings:
            print(f.to_markdown())
        print()
        return 0

    # Post summary comment
    try:
        post_review_comment(args.repo, args.pr, github_token, summary_body)
    except Exception as exc:
        logger.error("Failed to post summary comment: %s", exc)
        return 1

    # Post inline comments
    if unique_findings:
        try:
            commit_sha = get_pr_head_sha(args.repo, args.pr, github_token)
            post_inline_comments(
                repo_name=args.repo,
                pr_number=args.pr,
                token=github_token,
                commit_sha=commit_sha,
                findings=unique_findings,
                min_severity=args.min_severity,
            )
        except Exception as exc:
            logger.error("Failed to post inline comments: %s", exc)
            # Non-fatal: summary was already posted

    logger.info("Review complete for %s PR #%d.", args.repo, args.pr)
    return 0


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    load_dotenv()
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    sys.exit(run(args))


if __name__ == "__main__":
    main()
