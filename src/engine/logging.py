"""Structured logging for PRDForge execution engine."""

import json
import logging
import sys
from datetime import datetime
from typing import Any


class JSONFormatter(logging.Formatter):
    """Format log records as JSON for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as a JSON string."""
        log_data: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields if present
        if hasattr(record, "run_id"):
            log_data["run_id"] = record.run_id
        if hasattr(record, "task_id"):
            log_data["task_id"] = record.task_id
        if hasattr(record, "event"):
            log_data["event"] = record.event
        if hasattr(record, "data"):
            log_data["data"] = record.data

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


class PrettyFormatter(logging.Formatter):
    """Human-readable formatter with colors for terminal output."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with colors and context."""
        color = self.COLORS.get(record.levelname, "")
        reset = self.RESET

        # Build prefix with context
        prefix_parts = []
        if hasattr(record, "run_id"):
            prefix_parts.append(f"run:{record.run_id[:8]}")
        if hasattr(record, "task_id"):
            prefix_parts.append(f"task:{record.task_id}")

        prefix = f"[{' | '.join(prefix_parts)}] " if prefix_parts else ""

        # Format timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")

        return f"{timestamp} {color}{record.levelname:8}{reset} {prefix}{record.getMessage()}"


class EngineLogger:
    """Logger wrapper with context support for PRDForge engine."""

    def __init__(self, name: str = "prdforge") -> None:
        """Initialize the engine logger.

        Args:
            name: Logger name.
        """
        self._logger = logging.getLogger(name)
        self._run_id: str | None = None
        self._task_id: str | None = None

    def setup(
        self,
        level: int = logging.INFO,
        json_output: bool = False,
        log_file: str | None = None,
    ) -> None:
        """Configure the logger.

        Args:
            level: Logging level.
            json_output: If True, output JSON formatted logs.
            log_file: Optional file path to write logs to.
        """
        self._logger.setLevel(level)
        self._logger.handlers.clear()

        # Console handler
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(level)

        if json_output:
            console_handler.setFormatter(JSONFormatter())
        else:
            console_handler.setFormatter(PrettyFormatter())

        self._logger.addHandler(console_handler)

        # File handler (always JSON for machine parsing)
        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(level)
            file_handler.setFormatter(JSONFormatter())
            self._logger.addHandler(file_handler)

    def set_context(
        self, run_id: str | None = None, task_id: str | None = None
    ) -> None:
        """Set logging context for run and task tracking.

        Args:
            run_id: Current run identifier.
            task_id: Current task identifier.
        """
        self._run_id = run_id
        self._task_id = task_id

    def clear_context(self) -> None:
        """Clear the logging context."""
        self._run_id = None
        self._task_id = None

    def _log(
        self,
        level: int,
        message: str,
        event: str | None = None,
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Internal logging method with context injection.

        Args:
            level: Log level.
            message: Log message.
            event: Optional event type for structured logging.
            data: Optional additional data.
            **kwargs: Additional keyword arguments for the log record.
        """
        extra = {
            "run_id": self._run_id,
            "task_id": self._task_id,
            "event": event,
            "data": data,
            **kwargs,
        }
        self._logger.log(level, message, extra=extra)

    def debug(
        self, message: str, event: str | None = None, data: dict[str, Any] | None = None
    ) -> None:
        """Log a debug message."""
        self._log(logging.DEBUG, message, event, data)

    def info(
        self, message: str, event: str | None = None, data: dict[str, Any] | None = None
    ) -> None:
        """Log an info message."""
        self._log(logging.INFO, message, event, data)

    def warning(
        self, message: str, event: str | None = None, data: dict[str, Any] | None = None
    ) -> None:
        """Log a warning message."""
        self._log(logging.WARNING, message, event, data)

    def error(
        self, message: str, event: str | None = None, data: dict[str, Any] | None = None
    ) -> None:
        """Log an error message."""
        self._log(logging.ERROR, message, event, data)

    def critical(
        self, message: str, event: str | None = None, data: dict[str, Any] | None = None
    ) -> None:
        """Log a critical message."""
        self._log(logging.CRITICAL, message, event, data)

    # Convenience methods for common events
    def run_started(self, run_id: str, config_summary: dict[str, Any]) -> None:
        """Log run started event."""
        self.set_context(run_id=run_id)
        self.info(f"Run started: {run_id}", event="run_started", data=config_summary)

    def run_completed(self, run_id: str, summary: dict[str, Any]) -> None:
        """Log run completed event."""
        self.info(f"Run completed: {run_id}", event="run_completed", data=summary)
        self.clear_context()

    def run_failed(self, run_id: str, error: str) -> None:
        """Log run failed event."""
        self.error(f"Run failed: {run_id}", event="run_failed", data={"error": error})
        self.clear_context()

    def task_started(self, task_id: str, description: str) -> None:
        """Log task started event."""
        self.set_context(run_id=self._run_id, task_id=task_id)
        self.info(f"Task started: {description}", event="task_started")

    def task_completed(self, task_id: str, duration: float) -> None:
        """Log task completed event."""
        self.info(
            f"Task completed: {task_id}",
            event="task_completed",
            data={"duration_seconds": duration},
        )

    def task_failed(self, task_id: str, error: str) -> None:
        """Log task failed event."""
        self.error(
            f"Task failed: {task_id}", event="task_failed", data={"error": error}
        )


# Global logger instance
logger = EngineLogger()
