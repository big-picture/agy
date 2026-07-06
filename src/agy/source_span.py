# agy/source_span.py
"""Source location information for FLOWSY elements."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SourceSpan:
    """Source location for a parsed FLOWSY element.

    Attributes:
        file_name: Path to the .flowsy file
        start_line: First line number (1-based)
        end_line: Last line number (1-based, equals start_line for single-line elements)
        content: Raw content (one or more lines)
    """

    file_name: str
    start_line: int
    end_line: int
    content: str

    def __str__(self) -> str:
        """Human-readable representation for error messages."""
        if self.start_line == self.end_line:
            return f"Line {self.start_line}: {self.content}"
        # For multiline, show abbreviated content
        first_line = (
            self.content.split("\n")[0] if "\n" in self.content else self.content
        )
        return f"Lines {self.start_line}-{self.end_line}: {first_line}..."

    def __repr__(self) -> str:
        """Repr.

        Returns:
            str: Operation result.
        """
        return f"SourceSpan(file={self.file_name!r}, lines={self.start_line}-{self.end_line})"

    @classmethod
    def from_parser_dict(cls, d: dict[str, Any]) -> SourceSpan:
        """Create SourceSpan from flowsy_parser TypedDict.

        The flowsy_parser returns SourceSpan as TypedDict to avoid
        dependencies on agy. This method converts it to the dataclass.
        """
        return cls(
            file_name=d["file_name"],
            start_line=d["start_line"],
            end_line=d["end_line"],
            content=d["content"],
        )
