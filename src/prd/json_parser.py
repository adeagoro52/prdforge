"""JSON format PRD parser."""

import json
from datetime import datetime

from .base import BasePRDParser, PRDParseError
from .models import PRD, PRDMeta, PRDTask, Phase, TaskCategory, TestCoverage


class JSONPRDParser(BasePRDParser):
    """Parser for JSON format PRD files.

    Supports the standard PRDForge JSON format with:
    - meta: PRD metadata object
    - phases: Array of phase definitions
    - tasks: Array of task objects
    """

    def get_format_name(self) -> str:
        return "json"

    def can_parse(self, content: str) -> bool:
        """Check if content looks like valid JSON with PRD structure."""
        content = content.strip()
        if not content.startswith("{"):
            return False

        try:
            data = json.loads(content)
            # Check for PRD-specific keys
            return isinstance(data, dict) and (
                "tasks" in data or "phases" in data or "meta" in data
            )
        except json.JSONDecodeError:
            return False

    def parse(self, content: str, source_path: str | None = None) -> PRD:
        """Parse JSON PRD content.

        Args:
            content: JSON string content.
            source_path: Optional source file path.

        Returns:
            Parsed PRD object.

        Raises:
            PRDParseError: If JSON is invalid or missing required fields.
        """
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise PRDParseError(
                f"Invalid JSON: {e.msg}",
                source=source_path,
                line=e.lineno
            ) from e

        if not isinstance(data, dict):
            raise PRDParseError(
                "PRD JSON must be an object at root level",
                source=source_path
            )

        # Parse metadata
        meta = self._parse_meta(data.get("meta", {}), source_path)

        # Parse phases
        phases = self._parse_phases(data.get("phases", []), source_path)

        # Parse tasks
        tasks = self._parse_tasks(data.get("tasks", []), source_path)

        return PRD(
            meta=meta,
            phases=phases,
            tasks=tasks,
            source_format="json",
            source_path=source_path,
        )

    def _parse_meta(self, data: dict, source_path: str | None) -> PRDMeta:
        """Parse PRD metadata section."""
        if not isinstance(data, dict):
            raise PRDParseError("meta must be an object", source=source_path)

        # Parse created_at date if present
        created_at = None
        if "created_at" in data:
            try:
                created_at = datetime.fromisoformat(data["created_at"])
            except (ValueError, TypeError):
                # Try just date format
                try:
                    created_at = datetime.strptime(data["created_at"], "%Y-%m-%d")
                except (ValueError, TypeError):
                    pass  # Skip invalid dates

        # Collect additional metadata
        known_keys = {
            "feature_name", "feature_slug", "description", "created_at",
            "project_name", "priority", "wave", "tech_stack_decision",
            "deployment", "storage"
        }
        extra_metadata = {k: v for k, v in data.items() if k not in known_keys}

        return PRDMeta(
            feature_name=data.get("feature_name", "Unnamed PRD"),
            feature_slug=data.get("feature_slug", ""),
            description=data.get("description", ""),
            created_at=created_at,
            project_name=data.get("project_name", ""),
            priority=data.get("priority", "medium"),
            wave=data.get("wave", ""),
            tech_stack=data.get("tech_stack_decision", ""),
            deployment=data.get("deployment", ""),
            storage=data.get("storage", ""),
            metadata=extra_metadata,
        )

    def _parse_phases(self, data: list, source_path: str | None) -> list[Phase]:
        """Parse phases array."""
        if not isinstance(data, list):
            raise PRDParseError("phases must be an array", source=source_path)

        phases = []
        for i, phase_data in enumerate(data):
            if not isinstance(phase_data, dict):
                raise PRDParseError(
                    f"Phase {i} must be an object",
                    source=source_path
                )

            phases.append(Phase(
                phase=phase_data.get("phase", i + 1),
                name=phase_data.get("name", f"Phase {i + 1}"),
                description=phase_data.get("description", ""),
                estimated_tasks=phase_data.get("estimated_tasks", 0),
            ))

        return phases

    def _parse_tasks(self, data: list, source_path: str | None) -> list[PRDTask]:
        """Parse tasks array."""
        if not isinstance(data, list):
            raise PRDParseError("tasks must be an array", source=source_path)

        tasks = []
        for i, task_data in enumerate(data):
            if not isinstance(task_data, dict):
                raise PRDParseError(
                    f"Task {i} must be an object",
                    source=source_path
                )

            task_id = task_data.get("id")
            if not task_id:
                raise PRDParseError(
                    f"Task {i} missing required 'id' field",
                    source=source_path
                )

            # Parse category
            category_str = task_data.get("category", "other")
            category = TaskCategory.from_string(category_str)

            # Parse test coverage
            coverage_str = task_data.get("test_coverage", "none")
            test_coverage = TestCoverage.from_string(coverage_str)

            # Parse steps (can be string or list)
            steps = task_data.get("steps", [])
            if isinstance(steps, str):
                steps = [s.strip() for s in steps.split("\n") if s.strip()]

            # Parse blocked_by (can be string or list)
            blocked_by = task_data.get("blocked_by", [])
            if isinstance(blocked_by, str):
                blocked_by = [b.strip() for b in blocked_by.split(",") if b.strip()]

            # Collect additional metadata
            known_keys = {
                "id", "phase", "category", "description", "steps",
                "passes", "test_coverage", "blocked_by", "acceptance_criteria"
            }
            extra_metadata = {k: v for k, v in task_data.items() if k not in known_keys}

            tasks.append(PRDTask(
                id=task_id,
                phase=task_data.get("phase", 1),
                category=category,
                description=task_data.get("description", ""),
                steps=steps if isinstance(steps, list) else [],
                passes=bool(task_data.get("passes", False)),
                test_coverage=test_coverage,
                blocked_by=blocked_by if isinstance(blocked_by, list) else [],
                acceptance_criteria=task_data.get("acceptance_criteria", []),
                metadata=extra_metadata,
            ))

        return tasks
