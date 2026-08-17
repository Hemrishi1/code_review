"""
models.py - Data models for the AI Code Review Bot.
"""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Finding:
    """Represents a single code review finding on a PR diff."""

    file: str
    line: int
    severity: Literal["critical", "warning", "minor"]
    category: Literal["bug", "security", "style", "perf"]
    comment: str

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Finding):
            return NotImplemented
        return (
            self.file == other.file
            and self.line == other.line
            and self.category == other.category
        )

    def __hash__(self) -> int:
        return hash((self.file, self.line, self.category))

    def to_markdown(self) -> str:
        """Render the finding as a markdown block."""
        severity_emoji = {
            "critical": "🔴",
            "warning": "🟡",
            "minor": "🔵",
        }
        category_label = {
            "bug": "Bug",
            "security": "Security",
            "style": "Style",
            "perf": "Performance",
        }
        emoji = severity_emoji.get(self.severity, "⚪")
        label = category_label.get(self.category, self.category.title())
        return (
            f"{emoji} **[{self.severity.upper()}]** `{label}` — "
            f"`{self.file}:{self.line}`\n> {self.comment}"
        )
