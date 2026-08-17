"""
reviewer.py - AI-powered diff reviewer using the Anthropic Claude API.

Sends each file's patch to Claude via the tool_use API to obtain structured
Finding objects, then returns them for aggregation by main.py.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from config import IGNORED_PATHS, MAX_DIFF_LINES_PER_FILE
from models import Finding

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool schema for structured output
# ---------------------------------------------------------------------------

REVIEW_TOOL_NAME = "report_findings"

REVIEW_TOOL_SCHEMA: dict[str, Any] = {
    "name": REVIEW_TOOL_NAME,
    "description": (
        "Report all code review findings for the provided diff. "
        "Call this tool once with an array of every finding discovered."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "description": "Array of code review findings (may be empty if nothing notable found).",
                "items": {
                    "type": "object",
                    "required": ["file", "line", "severity", "category", "comment"],
                    "properties": {
                        "file": {
                            "type": "string",
                            "description": "File path exactly as it appears in the diff header.",
                        },
                        "line": {
                            "type": "integer",
                            "description": (
                                "The line number in the **new** version of the file "
                                "where the issue is located."
                            ),
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["critical", "warning", "minor"],
                            "description": (
                                "critical = must fix before merge; "
                                "warning = should fix; "
                                "minor = optional improvement."
                            ),
                        },
                        "category": {
                            "type": "string",
                            "enum": ["bug", "security", "style", "perf"],
                            "description": "Primary category of the issue.",
                        },
                        "comment": {
                            "type": "string",
                            "description": (
                                "Concise, actionable comment explaining the issue "
                                "and how to fix it. Max 3 sentences."
                            ),
                        },
                    },
                },
            }
        },
        "required": ["findings"],
    },
}

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a senior software engineer performing a thorough code review.

Your responsibilities:
- Flag **bugs** (logic errors, off-by-one, null-dereference, unchecked errors).
- Flag **security** issues (injection, hardcoded credentials, insecure defaults, SSRF, path traversal).
- Flag **style** violations only when they would cause real readability or maintainability problems (not personal preference).
- Flag **performance** issues (N+1 queries, unnecessary allocations, blocking I/O in hot paths).

Guidelines:
- Only report **high-confidence** issues.  When in doubt, omit the finding.
- Do NOT report trivial nitpicks about whitespace, variable naming conventions, or comment typos unless asked.
- Be **concise and actionable**: each comment should explain the problem and suggest a fix in ≤3 sentences.
- Respect the line numbers from the diff: `line` must correspond to the **new-file** line number.
- Use the `report_findings` tool to return your results as structured JSON.
"""

# ---------------------------------------------------------------------------
# Path filtering helpers
# ---------------------------------------------------------------------------


def _is_ignored(filename: str) -> bool:
    """Return True if the file should be skipped based on IGNORED_PATHS."""
    for pattern in IGNORED_PATHS:
        # Support both plain substrings and simple glob-like "*.ext" patterns.
        if pattern.startswith("*."):
            if filename.endswith(pattern[1:]):
                return True
        elif pattern in filename:
            return True
    return False


def _count_diff_lines(patch: str) -> int:
    """Count the number of added/changed lines in a unified diff patch."""
    return sum(1 for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++"))


# ---------------------------------------------------------------------------
# Core review function
# ---------------------------------------------------------------------------


def review_diff(
    filename: str,
    patch: str,
    anthropic_api_key: str | None = None,
    model: str = "claude-sonnet-4-5",
) -> list[Finding]:
    """Send a single file's diff to Claude and return structured findings.

    Args:
        filename:          Repo-relative file path (e.g. ``"src/app.py"``).
        patch:             Unified diff text from the GitHub API.
        anthropic_api_key: Overrides the ``ANTHROPIC_API_KEY`` env var when set.
        model:             Claude model to use.

    Returns:
        A (possibly empty) list of :class:`Finding` objects.

    Raises:
        anthropic.APIError: Propagated on unrecoverable API failures.
    """
    if _is_ignored(filename):
        logger.info("Skipping ignored file: %s", filename)
        return []

    if not patch or not patch.strip():
        logger.debug("Skipping %s — empty patch (binary or moved file).", filename)
        return []

    diff_lines = _count_diff_lines(patch)
    if diff_lines > MAX_DIFF_LINES_PER_FILE:
        logger.warning(
            "Skipping %s — diff is %d lines (limit %d).",
            filename,
            diff_lines,
            MAX_DIFF_LINES_PER_FILE,
        )
        return []

    client = anthropic.Anthropic(api_key=anthropic_api_key) if anthropic_api_key else anthropic.Anthropic()

    user_message = (
        f"Please review the following diff for `{filename}`.\n\n"
        f"```diff\n{patch}\n```\n\n"
        "Use the `report_findings` tool to return all issues you find."
    )

    logger.debug("Sending %s to Claude (%d diff lines).", filename, diff_lines)

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=[REVIEW_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": REVIEW_TOOL_NAME},
        messages=[{"role": "user", "content": user_message}],
    )

    # Extract tool use block
    findings: list[Finding] = []
    for block in response.content:
        if block.type == "tool_use" and block.name == REVIEW_TOOL_NAME:
            raw_findings: list[dict[str, Any]] = block.input.get("findings", [])
            for raw in raw_findings:
                try:
                    findings.append(
                        Finding(
                            file=raw["file"],
                            line=int(raw["line"]),
                            severity=raw["severity"],
                            category=raw["category"],
                            comment=raw["comment"],
                        )
                    )
                except (KeyError, ValueError, TypeError) as exc:
                    logger.warning("Skipping malformed finding from Claude: %s — %s", raw, exc)

    logger.info("Claude returned %d finding(s) for %s.", len(findings), filename)
    return findings
