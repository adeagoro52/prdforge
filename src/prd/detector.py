"""PRD format auto-detection and parser registry."""

from pathlib import Path
from typing import Type

from .base import BasePRDParser, PRDParseError
from .json_parser import JSONPRDParser
from .markdown_parser import MarkdownPRDParser
from .models import PRD


class PRDFormatDetector:
    """Detects PRD file format and provides appropriate parser.

    Detection strategy:
    1. File extension (primary hint)
    2. Content inspection (fallback for ambiguous cases)
    """

    # Map file extensions to parser classes
    EXTENSION_MAP: dict[str, Type[BasePRDParser]] = {
        ".json": JSONPRDParser,
        ".md": MarkdownPRDParser,
        ".markdown": MarkdownPRDParser,
    }

    # All available parsers for content-based detection
    PARSERS: list[Type[BasePRDParser]] = [
        JSONPRDParser,
        MarkdownPRDParser,
    ]

    @classmethod
    def detect_format(cls, path: Path | str | None = None, content: str | None = None) -> str:
        """Detect the PRD format from path and/or content.

        Args:
            path: Optional file path for extension-based detection.
            content: Optional content for content-based detection.

        Returns:
            Format name ('json' or 'markdown').

        Raises:
            PRDParseError: If format cannot be determined.
        """
        # Try extension first
        if path:
            path = Path(path)
            ext = path.suffix.lower()
            if ext in cls.EXTENSION_MAP:
                return cls.EXTENSION_MAP[ext]().get_format_name()

        # Fall back to content inspection
        if content:
            for parser_cls in cls.PARSERS:
                parser = parser_cls()
                if parser.can_parse(content):
                    return parser.get_format_name()

        raise PRDParseError(
            "Unable to detect PRD format. "
            "Use .json extension for JSON or .md for Markdown.",
            source=str(path) if path else None
        )

    @classmethod
    def get_parser(cls, path: Path | str | None = None, content: str | None = None) -> BasePRDParser:
        """Get appropriate parser for the given path/content.

        Args:
            path: Optional file path.
            content: Optional content.

        Returns:
            Parser instance for the detected format.

        Raises:
            PRDParseError: If format cannot be determined.
        """
        format_name = cls.detect_format(path, content)

        for parser_cls in cls.PARSERS:
            parser = parser_cls()
            if parser.get_format_name() == format_name:
                return parser

        raise PRDParseError(f"No parser available for format: {format_name}")

    @classmethod
    def parse_file(cls, path: Path | str) -> PRD:
        """Parse a PRD file with auto-detected format.

        Args:
            path: Path to the PRD file.

        Returns:
            Parsed PRD object.

        Raises:
            PRDParseError: If file cannot be parsed.
        """
        path = Path(path)

        # Read content for potential content-based detection
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as e:
            raise PRDParseError(f"Failed to read file: {e}", source=str(path)) from e

        parser = cls.get_parser(path=path, content=content)
        return parser.parse(content, source_path=str(path))

    @classmethod
    def parse_string(cls, content: str, format_hint: str | None = None) -> PRD:
        """Parse PRD content string with auto-detected format.

        Args:
            content: PRD content string.
            format_hint: Optional format hint ('json' or 'markdown').

        Returns:
            Parsed PRD object.

        Raises:
            PRDParseError: If content cannot be parsed.
        """
        if format_hint:
            for parser_cls in cls.PARSERS:
                parser = parser_cls()
                if parser.get_format_name() == format_hint:
                    return parser.parse(content)
            raise PRDParseError(f"Unknown format hint: {format_hint}")

        parser = cls.get_parser(content=content)
        return parser.parse(content)

    @classmethod
    def list_formats(cls) -> list[str]:
        """List all supported format names."""
        return [parser_cls().get_format_name() for parser_cls in cls.PARSERS]

    @classmethod
    def list_extensions(cls) -> list[str]:
        """List all supported file extensions."""
        return list(cls.EXTENSION_MAP.keys())
