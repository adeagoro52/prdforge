"""PRD parsing and handling module.

This module provides parsers for JSON and Markdown PRD formats,
format auto-detection, and conversion between formats.

Example usage:
    from prd import parse_prd, PRD, PRDTask

    # Parse from file (auto-detects format)
    prd = parse_prd("path/to/prd.json")

    # Get pending tasks
    for task in prd.get_pending_tasks():
        print(f"{task.id}: {task.description}")

    # Convert to markdown
    from prd import PRDConverter
    converter = PRDConverter()
    markdown = converter.to_markdown(prd)
"""

from .base import BasePRDParser, PRDParseError
from .converter import PRDConverter
from .detector import PRDFormatDetector
from .generator import (
    InterviewPhase,
    InterviewSession,
    Question,
    QuestionType,
    get_template,
    list_templates,
    review_prd,
)
from .json_parser import JSONPRDParser
from .markdown_parser import MarkdownPRDParser
from .models import PRD, PRDMeta, PRDTask, Phase, TaskCategory, TestCoverage

# Convenience function for parsing
parse_prd = PRDFormatDetector.parse_file
parse_prd_string = PRDFormatDetector.parse_string

__all__ = [
    # Models
    "PRD",
    "PRDMeta",
    "PRDTask",
    "Phase",
    "TaskCategory",
    "TestCoverage",
    # Parsers
    "BasePRDParser",
    "JSONPRDParser",
    "MarkdownPRDParser",
    "PRDParseError",
    # Utilities
    "PRDConverter",
    "PRDFormatDetector",
    # Generator
    "InterviewPhase",
    "InterviewSession",
    "Question",
    "QuestionType",
    "get_template",
    "list_templates",
    "review_prd",
    # Convenience functions
    "parse_prd",
    "parse_prd_string",
]
