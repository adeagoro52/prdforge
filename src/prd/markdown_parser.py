"""Markdown format PRD parser.

Supports Ralph-style markdown PRDs and a general markdown format.

Ralph-style format:
```markdown
# Feature Name

Description text...

## Phase 1: Phase Name

### Task 1.1: Task Description
- [ ] Step 1
- [ ] Step 2
- [x] Completed step

**Blocked by:** task-1-0
**Category:** backend
**Test coverage:** unit
```
"""

import re
from datetime import datetime

from .base import BasePRDParser, PRDParseError
from .models import PRD, PRDMeta, PRDTask, Phase, TaskCategory, TestCoverage


class MarkdownPRDParser(BasePRDParser):
    """Parser for Markdown format PRD files.

    Supports:
    - Ralph-style markdown with task checkboxes
    - Generic markdown with headers and metadata blocks
    """

    # Patterns for parsing
    PHASE_PATTERN = re.compile(
        r"^##\s+(?:Phase\s+)?(\d+)(?:\s*[:\-]\s*|\s+)(.+)$",
        re.IGNORECASE
    )
    TASK_PATTERN = re.compile(
        r"^###\s+(?:Task\s+)?(\d+(?:\.\d+)?|\w+(?:-\w+)*)(?:\s*[:\-]\s*|\s+)(.+)$",
        re.IGNORECASE
    )
    CHECKBOX_PATTERN = re.compile(r"^[-*]\s+\[([ xX])\]\s+(.+)$")
    METADATA_PATTERN = re.compile(r"^\*\*(.+?)\*\*\s*[:\s]\s*(.+)$")
    YAML_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.+?)\n---\s*\n", re.DOTALL)

    def get_format_name(self) -> str:
        return "markdown"

    def can_parse(self, content: str) -> bool:
        """Check if content looks like a markdown PRD."""
        content = content.strip()

        # Check for markdown indicators
        has_headers = bool(re.search(r"^#+ .+", content, re.MULTILINE))
        has_checkboxes = bool(re.search(r"^\s*[-*]\s+\[[ xX]\]", content, re.MULTILINE))
        has_phase = bool(self.PHASE_PATTERN.search(content))

        # Consider it markdown if it has headers and either checkboxes or phase markers
        return has_headers and (has_checkboxes or has_phase)

    def parse(self, content: str, source_path: str | None = None) -> PRD:
        """Parse Markdown PRD content.

        Args:
            content: Markdown string content.
            source_path: Optional source file path.

        Returns:
            Parsed PRD object.

        Raises:
            PRDParseError: If content cannot be parsed.
        """
        # Extract YAML frontmatter if present
        frontmatter = {}
        content_body = content
        fm_match = self.YAML_FRONTMATTER_PATTERN.match(content)
        if fm_match:
            frontmatter = self._parse_simple_yaml(fm_match.group(1))
            content_body = content[fm_match.end():]

        lines = content_body.split("\n")

        # Parse the document
        meta = self._parse_meta(lines, frontmatter, source_path)
        phases, tasks = self._parse_content(lines, source_path)

        return PRD(
            meta=meta,
            phases=phases,
            tasks=tasks,
            source_format="markdown",
            source_path=source_path,
        )

    def _parse_simple_yaml(self, yaml_str: str) -> dict:
        """Parse simple YAML frontmatter (key: value pairs only)."""
        result = {}
        for line in yaml_str.split("\n"):
            line = line.strip()
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if value:
                    result[key] = value
        return result

    def _parse_meta(
        self,
        lines: list[str],
        frontmatter: dict,
        source_path: str | None
    ) -> PRDMeta:
        """Extract PRD metadata from document."""
        # Get title from first H1
        feature_name = frontmatter.get("title", "")
        description_lines = []
        in_description = False

        for line in lines:
            stripped = line.strip()

            # Get feature name from H1 if not in frontmatter
            if stripped.startswith("# ") and not feature_name:
                feature_name = stripped[2:].strip()
                in_description = True
                continue

            # Collect description until we hit a section header
            if in_description:
                if stripped.startswith("##"):
                    break
                if stripped:
                    description_lines.append(stripped)

        # Generate slug from name
        feature_slug = frontmatter.get(
            "slug",
            re.sub(r"[^a-z0-9]+", "_", feature_name.lower()).strip("_")
        )

        # Parse date
        created_at = None
        date_str = frontmatter.get("date") or frontmatter.get("created_at")
        if date_str:
            try:
                created_at = datetime.fromisoformat(date_str)
            except ValueError:
                try:
                    created_at = datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    pass

        return PRDMeta(
            feature_name=feature_name or "Unnamed PRD",
            feature_slug=feature_slug,
            description=frontmatter.get("description", " ".join(description_lines)),
            created_at=created_at,
            project_name=frontmatter.get("project", ""),
            priority=frontmatter.get("priority", "medium"),
            wave=frontmatter.get("wave", ""),
            tech_stack=frontmatter.get("tech_stack", ""),
            deployment=frontmatter.get("deployment", ""),
            storage=frontmatter.get("storage", ""),
            metadata={k: v for k, v in frontmatter.items()
                      if k not in {"title", "slug", "description", "date",
                                   "created_at", "project", "priority", "wave",
                                   "tech_stack", "deployment", "storage"}},
        )

    def _parse_content(
        self,
        lines: list[str],
        source_path: str | None
    ) -> tuple[list[Phase], list[PRDTask]]:
        """Parse phases and tasks from document content."""
        phases: list[Phase] = []
        tasks: list[PRDTask] = []

        current_phase: int = 0
        current_task: dict | None = None
        task_counter: int = 0

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()

            # Check for phase header
            phase_match = self.PHASE_PATTERN.match(stripped)
            if phase_match:
                # Save current task if any
                if current_task:
                    tasks.append(self._build_task(current_task, source_path))
                    current_task = None

                phase_num = int(phase_match.group(1))
                phase_name = phase_match.group(2).strip()
                current_phase = phase_num

                phases.append(Phase(
                    phase=phase_num,
                    name=phase_name,
                    description="",
                    estimated_tasks=0,
                ))
                continue

            # Check for task header
            task_match = self.TASK_PATTERN.match(stripped)
            if task_match:
                # Save previous task if any
                if current_task:
                    tasks.append(self._build_task(current_task, source_path))

                task_counter += 1
                task_id_raw = task_match.group(1)
                task_desc = task_match.group(2).strip()

                # Generate task ID
                if re.match(r"^\d+(\.\d+)?$", task_id_raw):
                    # Numeric ID like "1.1" -> "phase1-001"
                    parts = task_id_raw.split(".")
                    phase_num = int(parts[0]) if len(parts) > 1 else current_phase
                    task_num = int(parts[-1]) if len(parts) > 1 else task_counter
                    task_id = f"phase{phase_num}-{task_num:03d}"
                else:
                    # Already a slug-style ID
                    task_id = task_id_raw

                current_task = {
                    "id": task_id,
                    "phase": current_phase or 1,
                    "description": task_desc,
                    "steps": [],
                    "passes": False,
                    "all_steps_done": True,  # Track if all checkboxes are checked
                    "category": "other",
                    "test_coverage": "none",
                    "blocked_by": [],
                    "acceptance_criteria": [],
                    "line": line_num,
                }
                continue

            # Inside a task - parse content
            if current_task:
                # Check for metadata line FIRST (before bullet check, since ** starts with *)
                meta_match = self.METADATA_PATTERN.match(stripped)
                if meta_match:
                    # Clean up key: lowercase, spaces to underscores, strip trailing colon
                    key = meta_match.group(1).lower().replace(" ", "_").rstrip(":")
                    value = meta_match.group(2).strip()

                    if key == "blocked_by":
                        # Parse comma-separated list
                        current_task["blocked_by"] = [
                            b.strip() for b in value.split(",") if b.strip()
                        ]
                    elif key == "category":
                        current_task["category"] = value.lower()
                    elif key == "test_coverage":
                        current_task["test_coverage"] = value.lower()
                    elif key == "acceptance_criteria":
                        current_task["acceptance_criteria"].append(value)
                    continue

                # Check for checkbox step
                checkbox_match = self.CHECKBOX_PATTERN.match(stripped)
                if checkbox_match:
                    is_checked = checkbox_match.group(1).lower() == "x"
                    step_text = checkbox_match.group(2).strip()
                    current_task["steps"].append(step_text)
                    if not is_checked:
                        current_task["all_steps_done"] = False
                    continue

                # Regular bullet point (not checkbox) as step
                if stripped.startswith(("-", "*")) and "[" not in stripped[:4]:
                    step_text = stripped.lstrip("-* ").strip()
                    if step_text:
                        current_task["steps"].append(step_text)

        # Don't forget the last task
        if current_task:
            tasks.append(self._build_task(current_task, source_path))

        # Update phase estimated_tasks counts
        for phase in phases:
            phase.estimated_tasks = len([t for t in tasks if t.phase == phase.phase])

        return phases, tasks

    def _build_task(self, task_data: dict, source_path: str | None) -> PRDTask:
        """Build a PRDTask from parsed data."""
        # If all checkbox steps are done, mark task as passing
        passes = task_data.get("passes", False)
        if task_data.get("all_steps_done", False) and task_data.get("steps"):
            passes = True

        return PRDTask(
            id=task_data["id"],
            phase=task_data.get("phase", 1),
            category=TaskCategory.from_string(task_data.get("category", "other")),
            description=task_data.get("description", ""),
            steps=task_data.get("steps", []),
            passes=passes,
            test_coverage=TestCoverage.from_string(task_data.get("test_coverage", "none")),
            blocked_by=task_data.get("blocked_by", []),
            acceptance_criteria=task_data.get("acceptance_criteria", []),
            metadata={"source_line": task_data.get("line")},
        )
