"""Base parser interface for PRD file formats."""

from abc import ABC, abstractmethod
from pathlib import Path

from .models import PRD


class PRDParseError(Exception):
    """Raised when PRD parsing fails."""

    def __init__(self, message: str, source: str | None = None, line: int | None = None):
        self.source = source
        self.line = line
        super().__init__(message)


class BasePRDParser(ABC):
    """Abstract base class for PRD parsers.

    All PRD format parsers must implement this interface,
    producing the unified PRD model regardless of input format.
    """

    @abstractmethod
    def parse(self, content: str, source_path: str | None = None) -> PRD:
        """Parse PRD content string into a PRD object.

        Args:
            content: Raw PRD content as string.
            source_path: Optional path to the source file.

        Returns:
            Parsed PRD object.

        Raises:
            PRDParseError: If parsing fails.
        """

    def parse_file(self, path: Path | str) -> PRD:
        """Parse PRD from a file path.

        Args:
            path: Path to the PRD file.

        Returns:
            Parsed PRD object.

        Raises:
            PRDParseError: If file cannot be read or parsed.
        """
        path = Path(path)
        if not path.exists():
            raise PRDParseError(f"PRD file not found: {path}", source=str(path))

        try:
            content = path.read_text(encoding="utf-8")
        except OSError as e:
            raise PRDParseError(f"Failed to read PRD file: {e}", source=str(path)) from e

        return self.parse(content, source_path=str(path))

    @abstractmethod
    def get_format_name(self) -> str:
        """Return the format name this parser handles."""

    @abstractmethod
    def can_parse(self, content: str) -> bool:
        """Check if this parser can handle the given content.

        Used for format auto-detection when file extension is ambiguous.

        Args:
            content: Raw content to check.

        Returns:
            True if this parser can likely handle the content.
        """
