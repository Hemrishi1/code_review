"""
reviewer.py - AI-powered diff reviewer using the Google Gemini API (google-genai SDK).

Sends each file's patch to Gemini with structured JSON output schema to obtain
Finding objects, then returns them for aggregation by main.py.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from config import IGNORED_PATHS, MAX_DIFF_LINES_PER_FILE
from models import Finding

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Structured Schema using Pydantic
# ---------------------------------------------------------------------------


class FindingSchema(BaseModel):
    file: str = Field(description="File path exactly as it appears in the diff header.")
    line: int = Field(description="The line number in the new version of the file where the issue is located.")
    severity: Literal["critical", "warning", "minor"] = Field(
        description="critical = must fix before merge; warning = should fix; minor = optional improvement."
    )
    category: Literal["bug", "security", "style", "perf"] = Field(
        description="Primary category of the issue: bug, security, style, or perf."
    )
    comment: str = Field(
        description="Concise, actionable comment explaining the issue and how to fix it in <=3 sentences."
    )


class ReviewResultSchema(BaseModel):
    findings: list[FindingSchema] = Field(
        default_factory=list,
        description="List of code review findings. Empty if no issues are detected.",
    )


# ---------------------------------------------------------------------------
# System instruction
# ---------------------------------------------------------------------------

SYSTEM_INSTRUCTION = """\
You are a senior software engineer performing a thorough code review.

Your responsibilities:
- Flag **bugs** (logic errors, off-by-one, null-dereference, unchecked errors).
- Flag **security** issues (injection, hardcoded credentials, insecure defaults, SSRF, path traversal).
- Flag **style** violations only when they would cause real readability or maintainability problems (not personal preference).
- Flag **performance** issues (N+1 queries, unnecessary allocations, blocking I/O in hot paths).

Guidelines:
- Only report **high-confidence** issues. When in doubt, omit the finding.
- Do NOT report trivial nitpicks about whitespace, variable naming conventions, or comment typos unless asked.
- Be **concise and actionable**: each comment should explain the problem and suggest a fix in ≤3 sentences.
- Respect the line numbers from the diff: `line` must correspond to the **new-file** line number.
- Always output valid JSON conforming to the requested schema.
"""

# ---------------------------------------------------------------------------
# Path filtering helpers
# ---------------------------------------------------------------------------


def _is_ignored(filename: str) -> bool:
    """Return True if the file should be skipped based on IGNORED_PATHS."""
    for pattern in IGNORED_PATHS:
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
    gemini_api_key: str | None = None,
    model: str = "gemini-2.5-flash",
) -> list[Finding]:
    """Send a single file's diff to Google Gemini and return structured findings.

    Args:
        filename:       Repo-relative file path (e.g. ``"src/app.py"``).
        patch:          Unified diff text from the GitHub API.
        gemini_api_key: Overrides the ``GEMINI_API_KEY`` or ``GOOGLE_API_KEY`` env var.
        model:          Gemini model to use (default: ``"gemini-2.5-flash"``).

    Returns:
        A (possibly empty) list of :class:`Finding` objects.
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

    client = genai.Client(api_key=gemini_api_key) if gemini_api_key else genai.Client()

    user_prompt = (
        f"Please review the following diff for `{filename}`:\n\n"
        f"```diff\n{patch}\n```\n\n"
        "Return all findings structured according to the response schema."
    )

    logger.debug("Sending %s to Gemini (%d diff lines, model: %s).", filename, diff_lines, model)

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_schema=ReviewResultSchema,
        temperature=0.2,
    )

    response = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config=config,
    )

    findings: list[Finding] = []
    
    if response.parsed and isinstance(response.parsed, ReviewResultSchema):
        for item in response.parsed.findings:
            findings.append(
                Finding(
                    file=item.file or filename,
                    line=item.line,
                    severity=item.severity,
                    category=item.category,
                    comment=item.comment,
                )
            )
    elif response.text:
        try:
            data = json.loads(response.text)
            raw_findings = data.get("findings", []) if isinstance(data, dict) else []
            for raw in raw_findings:
                findings.append(
                    Finding(
                        file=raw.get("file", filename),
                        line=int(raw["line"]),
                        severity=raw["severity"],
                        category=raw["category"],
                        comment=raw["comment"],
                    )
                )
        except Exception as exc:
            logger.warning("Failed to parse Gemini response JSON: %s (Raw: %s)", exc, response.text)

    logger.info("Gemini returned %d finding(s) for %s.", len(findings), filename)
    return findings
