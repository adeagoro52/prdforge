"""PRD format converter - convert between JSON and Markdown formats."""

import json
from datetime import datetime

from .models import PRD, PRDTask, Phase


class PRDConverter:
    """Converter between PRD formats.

    Supports conversion:
    - PRD object -> JSON string
    - PRD object -> Markdown string
    """

    def to_json(self, prd: PRD, indent: int = 2) -> str:
        """Convert PRD to JSON format string.

        Args:
            prd: PRD object to convert.
            indent: JSON indentation level.

        Returns:
            JSON string representation.
        """
        data = {
            "meta": self._meta_to_dict(prd.meta),
            "phases": [self._phase_to_dict(p) for p in prd.phases],
            "tasks": [self._task_to_dict(t) for t in prd.tasks],
        }
        return json.dumps(data, indent=indent, default=str)

    def to_markdown(self, prd: PRD) -> str:
        """Convert PRD to Markdown format string.

        Args:
            prd: PRD object to convert.

        Returns:
            Markdown string representation.
        """
        lines = []

        # YAML frontmatter
        lines.append("---")
        lines.append(f"title: {prd.meta.feature_name}")
        if prd.meta.feature_slug:
            lines.append(f"slug: {prd.meta.feature_slug}")
        if prd.meta.project_name:
            lines.append(f"project: {prd.meta.project_name}")
        if prd.meta.priority:
            lines.append(f"priority: {prd.meta.priority}")
        if prd.meta.created_at:
            lines.append(f"date: {prd.meta.created_at.strftime('%Y-%m-%d')}")
        lines.append("---")
        lines.append("")

        # Title and description
        lines.append(f"# {prd.meta.feature_name}")
        lines.append("")
        if prd.meta.description:
            lines.append(prd.meta.description)
            lines.append("")

        # Group tasks by phase
        tasks_by_phase: dict[int, list[PRDTask]] = {}
        for task in prd.tasks:
            if task.phase not in tasks_by_phase:
                tasks_by_phase[task.phase] = []
            tasks_by_phase[task.phase].append(task)

        # Output each phase
        for phase in sorted(prd.phases, key=lambda p: p.phase):
            lines.append(f"## Phase {phase.phase}: {phase.name}")
            lines.append("")
            if phase.description:
                lines.append(phase.description)
                lines.append("")

            # Output tasks in this phase
            phase_tasks = tasks_by_phase.get(phase.phase, [])
            for task in phase_tasks:
                lines.extend(self._task_to_markdown(task))

        # Handle tasks without a defined phase
        orphan_phases = set(tasks_by_phase.keys()) - {p.phase for p in prd.phases}
        for phase_num in sorted(orphan_phases):
            lines.append(f"## Phase {phase_num}")
            lines.append("")
            for task in tasks_by_phase[phase_num]:
                lines.extend(self._task_to_markdown(task))

        return "\n".join(lines)

    def _task_to_markdown(self, task: PRDTask) -> list[str]:
        """Convert a single task to markdown lines."""
        lines = []

        # Task header
        lines.append(f"### Task {task.id}: {task.description}")
        lines.append("")

        # Steps as checkboxes
        for step in task.steps:
            checkbox = "[x]" if task.passes else "[ ]"
            lines.append(f"- {checkbox} {step}")

        if task.steps:
            lines.append("")

        # Metadata
        if task.category.value != "other":
            lines.append(f"**Category:** {task.category.value}")
        if task.test_coverage.value != "none":
            lines.append(f"**Test coverage:** {task.test_coverage.value}")
        if task.blocked_by:
            lines.append(f"**Blocked by:** {', '.join(task.blocked_by)}")
        if task.acceptance_criteria:
            lines.append("**Acceptance criteria:**")
            for criteria in task.acceptance_criteria:
                lines.append(f"- {criteria}")

        lines.append("")
        return lines

    def _meta_to_dict(self, meta) -> dict:
        """Convert PRDMeta to dictionary."""
        result = {
            "feature_name": meta.feature_name,
            "feature_slug": meta.feature_slug,
            "description": meta.description,
            "project_name": meta.project_name,
            "priority": meta.priority,
        }

        if meta.created_at:
            result["created_at"] = meta.created_at.strftime("%Y-%m-%d")
        if meta.wave:
            result["wave"] = meta.wave
        if meta.tech_stack:
            result["tech_stack_decision"] = meta.tech_stack
        if meta.deployment:
            result["deployment"] = meta.deployment
        if meta.storage:
            result["storage"] = meta.storage

        # Include additional metadata
        result.update(meta.metadata)

        return result

    def _phase_to_dict(self, phase: Phase) -> dict:
        """Convert Phase to dictionary."""
        return {
            "phase": phase.phase,
            "name": phase.name,
            "description": phase.description,
            "estimated_tasks": phase.estimated_tasks,
        }

    def _task_to_dict(self, task: PRDTask) -> dict:
        """Convert PRDTask to dictionary."""
        result = {
            "id": task.id,
            "phase": task.phase,
            "category": task.category.value,
            "description": task.description,
            "steps": task.steps,
            "passes": task.passes,
            "test_coverage": task.test_coverage.value,
            "blocked_by": task.blocked_by,
        }

        if task.acceptance_criteria:
            result["acceptance_criteria"] = task.acceptance_criteria

        # Include additional metadata
        result.update(task.metadata)

        return result
