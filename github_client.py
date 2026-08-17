"""
github_client.py - GitHub API helpers for the AI Code Review Bot.

Provides:
  - get_pr_files()          fetch changed files + patch text
  - post_review_comment()   post a top-level PR comment (summary)
  - post_inline_comments()  post per-line review comments
"""

from __future__ import annotations

import logging
from typing import Any

from github import Github, GithubException
from github.PullRequest import PullRequest

from models import Finding

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_pr(repo_name: str, pr_number: int, token: str) -> PullRequest:
    """Authenticate and return the PullRequest object."""
    g = Github(token)
    repo = g.get_repo(repo_name)
    return repo.get_pull(pr_number)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_pr_files(
    repo_name: str,
    pr_number: int,
    token: str,
) -> list[dict[str, Any]]:
    """Return a list of changed files for the given PR.

    Each element is a dict with at least:
      - ``filename``  (str)  path relative to the repo root
      - ``patch``     (str | None)  unified-diff text; None for binary files
      - ``additions`` (int)
      - ``deletions`` (int)
      - ``changes``   (int)  additions + deletions
    """
    try:
        pr = _get_pr(repo_name, pr_number, token)
        files = pr.get_files()
        result: list[dict[str, Any]] = []
        for f in files:
            result.append(
                {
                    "filename": f.filename,
                    "patch": getattr(f, "patch", None),
                    "additions": f.additions,
                    "deletions": f.deletions,
                    "changes": f.changes,
                    "status": f.status,  # added | modified | removed | renamed
                }
            )
        logger.info("Fetched %d changed file(s) from PR #%d.", len(result), pr_number)
        return result
    except GithubException as exc:
        logger.error("GitHub API error fetching PR files: %s", exc)
        raise


def get_pr_head_sha(repo_name: str, pr_number: int, token: str) -> str:
    """Return the SHA of the PR's head commit (needed for inline comments)."""
    pr = _get_pr(repo_name, pr_number, token)
    return pr.head.sha


def post_review_comment(
    repo_name: str,
    pr_number: int,
    token: str,
    body: str,
) -> None:
    """Post ``body`` as a top-level PR issue comment (the summary block)."""
    try:
        pr = _get_pr(repo_name, pr_number, token)
        pr.create_issue_comment(body)
        logger.info("Posted summary comment on PR #%d.", pr_number)
    except GithubException as exc:
        logger.error("GitHub API error posting review comment: %s", exc)
        raise


def post_inline_comments(
    repo_name: str,
    pr_number: int,
    token: str,
    commit_sha: str,
    findings: list[Finding],
    min_severity: str = "warning",
) -> None:
    """Post each Finding as an inline PR review comment on the exact line.

    Only findings that meet the ``min_severity`` threshold are posted.
    If a comment cannot be attached (e.g. line not in the diff), it is
    silently skipped with a warning log.
    """
    from config import SEVERITY_ORDER

    threshold = SEVERITY_ORDER.get(min_severity, 1)

    try:
        pr = _get_pr(repo_name, pr_number, token)
        commit = pr.base.repo.get_commit(commit_sha)

        posted = 0
        for finding in findings:
            if SEVERITY_ORDER.get(finding.severity, 0) < threshold:
                logger.debug(
                    "Skipping %s finding on %s:%d (below min severity).",
                    finding.severity,
                    finding.file,
                    finding.line,
                )
                continue

            body = (
                f"**[{finding.severity.upper()}]** `{finding.category}` — "
                f"{finding.comment}"
            )
            try:
                pr.create_review_comment(
                    body=body,
                    commit=commit,
                    path=finding.file,
                    line=finding.line,
                )
                posted += 1
            except GithubException as exc:
                logger.warning(
                    "Could not post inline comment on %s:%d — %s",
                    finding.file,
                    finding.line,
                    exc,
                )

        logger.info("Posted %d inline comment(s) on PR #%d.", posted, pr_number)
    except GithubException as exc:
        logger.error("GitHub API error posting inline comments: %s", exc)
        raise
