"""PRD generation with interview mode.

This module provides:
- InterviewSession for guiding users through PRD creation
- Question generation based on context
- PRD template system for common patterns
- Review mode for existing PRDs
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional
import json
import re

from .models import PRD, PRDMeta, PRDTask, TestCoverage


class InterviewPhase(Enum):
    """Phases of the PRD interview process."""

    FEATURE_OVERVIEW = "feature_overview"  # Name, description, priority
    CONTEXT_GATHERING = "context_gathering"  # Tech stack, constraints
    TASK_DEFINITION = "task_definition"  # Individual tasks
    ACCEPTANCE_CRITERIA = "acceptance_criteria"  # Test criteria
    REVIEW = "review"  # Final review
    COMPLETE = "complete"  # Interview finished


class QuestionType(Enum):
    """Types of interview questions."""

    TEXT = "text"  # Free text input
    CHOICE = "choice"  # Single choice from options
    MULTI_CHOICE = "multi_choice"  # Multiple selections
    NUMBER = "number"  # Numeric input
    CONFIRM = "confirm"  # Yes/no confirmation


@dataclass
class Question:
    """A question in the interview flow.

    Attributes:
        id: Unique question identifier.
        text: The question text.
        question_type: Type of expected answer.
        options: Available options for choice questions.
        required: Whether answer is required.
        default: Default value if not answered.
        help_text: Additional help for the question.
        field_path: Path to field in PRD structure.
    """

    id: str
    text: str
    question_type: QuestionType = QuestionType.TEXT
    options: list[str] = field(default_factory=list)
    required: bool = True
    default: Optional[str] = None
    help_text: Optional[str] = None
    field_path: Optional[str] = None


@dataclass
class InterviewResponse:
    """Response to an interview question.

    Attributes:
        question_id: ID of the question answered.
        value: The response value.
        timestamp: When the response was given.
    """

    question_id: str
    value: Any
    timestamp: datetime = field(default_factory=datetime.utcnow)


# Pre-defined question sets for each phase
FEATURE_QUESTIONS = [
    Question(
        id="feature_name",
        text="What is the name of this feature?",
        help_text="A short, descriptive name (e.g., 'User Authentication', 'Dark Mode Support')",
        field_path="meta.feature_name",
    ),
    Question(
        id="feature_description",
        text="Describe the feature in 1-2 sentences:",
        help_text="What does this feature do and why is it needed?",
        field_path="meta.description",
    ),
    Question(
        id="priority",
        text="What is the priority of this feature?",
        question_type=QuestionType.CHOICE,
        options=["critical", "high", "medium", "low"],
        default="medium",
        field_path="meta.priority",
    ),
]

CONTEXT_QUESTIONS = [
    Question(
        id="tech_stack",
        text="What technologies/frameworks will be used?",
        question_type=QuestionType.TEXT,
        help_text="e.g., Python, FastAPI, React, PostgreSQL",
        required=False,
        field_path="meta.tech_stack",
    ),
    Question(
        id="dependencies",
        text="Are there any dependencies or prerequisites?",
        question_type=QuestionType.TEXT,
        help_text="Other features or systems this depends on",
        required=False,
    ),
    Question(
        id="constraints",
        text="Are there any constraints or limitations to consider?",
        question_type=QuestionType.TEXT,
        help_text="Performance requirements, backwards compatibility, etc.",
        required=False,
    ),
]

TASK_QUESTIONS = [
    Question(
        id="task_description",
        text="Describe this task:",
        help_text="What needs to be done in this task?",
    ),
    Question(
        id="task_category",
        text="What category is this task?",
        question_type=QuestionType.CHOICE,
        options=["backend", "frontend", "database", "api", "config", "docs", "test"],
        default="backend",
    ),
    Question(
        id="task_steps",
        text="What are the implementation steps?",
        question_type=QuestionType.TEXT,
        help_text="List the steps, one per line",
    ),
    Question(
        id="task_test_coverage",
        text="What test coverage is required?",
        question_type=QuestionType.CHOICE,
        options=["none", "unit", "integration", "e2e", "manual"],
        default="unit",
    ),
]


# PRD Templates for common patterns
PRD_TEMPLATES = {
    "api_endpoint": {
        "name": "API Endpoint",
        "description": "Template for adding a new API endpoint",
        "tasks": [
            {
                "category": "backend",
                "description": "Define endpoint schema and request/response models",
                "steps": [
                    "Create Pydantic models for request body",
                    "Create Pydantic models for response",
                    "Define error response models",
                ],
                "test_coverage": "unit",
            },
            {
                "category": "backend",
                "description": "Implement endpoint handler",
                "steps": [
                    "Create route handler function",
                    "Implement business logic",
                    "Add error handling",
                    "Add logging",
                ],
                "test_coverage": "integration",
            },
            {
                "category": "test",
                "description": "Write tests for the endpoint",
                "steps": [
                    "Write happy path tests",
                    "Write error case tests",
                    "Write validation tests",
                ],
                "test_coverage": "integration",
            },
            {
                "category": "docs",
                "description": "Document the endpoint",
                "steps": [
                    "Add OpenAPI documentation",
                    "Update API documentation",
                ],
                "test_coverage": "none",
            },
        ],
    },
    "ui_feature": {
        "name": "UI Feature",
        "description": "Template for adding a new UI feature",
        "tasks": [
            {
                "category": "frontend",
                "description": "Design component structure",
                "steps": [
                    "Create component hierarchy",
                    "Define props and state",
                    "Plan styling approach",
                ],
                "test_coverage": "none",
            },
            {
                "category": "frontend",
                "description": "Implement UI components",
                "steps": [
                    "Create main component",
                    "Create child components",
                    "Add styling",
                    "Handle user interactions",
                ],
                "test_coverage": "unit",
            },
            {
                "category": "frontend",
                "description": "Integrate with API",
                "steps": [
                    "Add API calls",
                    "Handle loading states",
                    "Handle error states",
                ],
                "test_coverage": "integration",
            },
            {
                "category": "test",
                "description": "Write tests",
                "steps": [
                    "Write component unit tests",
                    "Write integration tests",
                ],
                "test_coverage": "unit",
            },
        ],
    },
    "refactoring": {
        "name": "Refactoring",
        "description": "Template for refactoring existing code",
        "tasks": [
            {
                "category": "backend",
                "description": "Analyze existing code",
                "steps": [
                    "Review current implementation",
                    "Identify pain points",
                    "Document dependencies",
                ],
                "test_coverage": "none",
            },
            {
                "category": "test",
                "description": "Ensure test coverage before refactoring",
                "steps": [
                    "Write tests for current behavior",
                    "Verify test coverage",
                ],
                "test_coverage": "unit",
            },
            {
                "category": "backend",
                "description": "Implement refactoring",
                "steps": [
                    "Make incremental changes",
                    "Run tests after each change",
                    "Update documentation",
                ],
                "test_coverage": "unit",
            },
            {
                "category": "test",
                "description": "Verify refactoring",
                "steps": [
                    "Run all tests",
                    "Perform manual testing",
                    "Get code review",
                ],
                "test_coverage": "integration",
            },
        ],
    },
    "database_migration": {
        "name": "Database Migration",
        "description": "Template for database schema changes",
        "tasks": [
            {
                "category": "database",
                "description": "Design schema changes",
                "steps": [
                    "Document current schema",
                    "Design new schema",
                    "Plan migration path",
                ],
                "test_coverage": "none",
            },
            {
                "category": "database",
                "description": "Create migration scripts",
                "steps": [
                    "Write forward migration",
                    "Write rollback migration",
                    "Test on local database",
                ],
                "test_coverage": "integration",
            },
            {
                "category": "backend",
                "description": "Update application code",
                "steps": [
                    "Update models",
                    "Update queries",
                    "Update tests",
                ],
                "test_coverage": "unit",
            },
        ],
    },
}


class InterviewSession:
    """Manages the PRD interview process.

    This class guides users through creating a PRD by asking
    structured questions and collecting responses.

    Example usage::

        session = InterviewSession()
        while not session.is_complete:
            question = session.get_current_question()
            print(question.text)
            answer = input("> ")
            session.answer(answer)

        prd = session.generate_prd()
    """

    def __init__(
        self,
        template: Optional[str] = None,
        existing_prd: Optional[PRD] = None,
    ):
        """Initialize interview session.

        Args:
            template: Optional template name to start from.
            existing_prd: Optional existing PRD for review mode.
        """
        self.responses: list[InterviewResponse] = []
        self.phase = InterviewPhase.FEATURE_OVERVIEW
        self.tasks: list[dict[str, Any]] = []
        self.current_task_index = 0
        self._question_index = 0
        self._template = template
        self._existing_prd = existing_prd

        # If template provided, pre-populate tasks
        if template and template in PRD_TEMPLATES:
            self.tasks = [dict(t) for t in PRD_TEMPLATES[template]["tasks"]]

        # If reviewing existing PRD, populate responses
        if existing_prd:
            self._populate_from_prd(existing_prd)
            self.phase = InterviewPhase.REVIEW

    def _populate_from_prd(self, prd: PRD) -> None:
        """Populate responses from existing PRD."""
        self.responses.extend([
            InterviewResponse("feature_name", prd.meta.feature_name),
            InterviewResponse("feature_description", prd.meta.description or ""),
            InterviewResponse("priority", prd.meta.priority or "medium"),
        ])

        for task in prd.tasks:
            self.tasks.append({
                "id": task.id,
                "description": task.description,
                "category": task.category,
                "steps": task.steps,
                "test_coverage": task.test_coverage.value if task.test_coverage else "unit",
                "blocked_by": task.blocked_by,
                "passes": task.passes,
            })

    @property
    def is_complete(self) -> bool:
        """Check if interview is complete."""
        return self.phase == InterviewPhase.COMPLETE

    def get_current_question(self) -> Optional[Question]:
        """Get the current question to ask.

        Returns:
            Current Question or None if interview is complete.
        """
        if self.is_complete:
            return None

        questions = self._get_phase_questions()
        if self._question_index < len(questions):
            return questions[self._question_index]

        # No more questions in current phase
        return None

    def _get_phase_questions(self) -> list[Question]:
        """Get questions for the current phase."""
        if self.phase == InterviewPhase.FEATURE_OVERVIEW:
            return FEATURE_QUESTIONS
        elif self.phase == InterviewPhase.CONTEXT_GATHERING:
            return CONTEXT_QUESTIONS
        elif self.phase == InterviewPhase.TASK_DEFINITION:
            return TASK_QUESTIONS
        elif self.phase == InterviewPhase.ACCEPTANCE_CRITERIA:
            return [
                Question(
                    id="add_another_task",
                    text="Do you want to add another task?",
                    question_type=QuestionType.CONFIRM,
                    default="no",
                )
            ]
        elif self.phase == InterviewPhase.REVIEW:
            return [
                Question(
                    id="confirm_prd",
                    text="Does this PRD look correct?",
                    question_type=QuestionType.CONFIRM,
                    default="yes",
                )
            ]
        return []

    def answer(self, value: Any) -> None:
        """Record an answer to the current question.

        Args:
            value: The answer value.
        """
        question = self.get_current_question()
        if not question:
            return

        # Store response
        self.responses.append(InterviewResponse(question.id, value))

        # Handle task-specific logic
        if self.phase == InterviewPhase.TASK_DEFINITION:
            self._handle_task_response(question.id, value)
        elif self.phase == InterviewPhase.ACCEPTANCE_CRITERIA:
            self._handle_acceptance_response(question.id, value)
        elif self.phase == InterviewPhase.REVIEW:
            self._handle_review_response(question.id, value)

        # Move to next question or phase
        self._question_index += 1
        if self._question_index >= len(self._get_phase_questions()):
            self._advance_phase()

    def _handle_task_response(self, question_id: str, value: Any) -> None:
        """Handle responses during task definition phase."""
        if question_id == "task_description":
            # Start new task
            if self.current_task_index >= len(self.tasks):
                self.tasks.append({})
            self.tasks[self.current_task_index]["description"] = value

        elif question_id == "task_category":
            self.tasks[self.current_task_index]["category"] = value

        elif question_id == "task_steps":
            # Parse steps (one per line)
            steps = [s.strip() for s in value.split("\n") if s.strip()]
            self.tasks[self.current_task_index]["steps"] = steps

        elif question_id == "task_test_coverage":
            self.tasks[self.current_task_index]["test_coverage"] = value

    def _handle_acceptance_response(self, question_id: str, value: Any) -> None:
        """Handle responses during acceptance criteria phase."""
        if question_id == "add_another_task":
            if str(value).lower() in ("yes", "y", "true"):
                # Go back to task definition
                self.current_task_index += 1
                self.phase = InterviewPhase.TASK_DEFINITION
                self._question_index = 0

    def _handle_review_response(self, question_id: str, value: Any) -> None:
        """Handle responses during review phase."""
        if question_id == "confirm_prd":
            if str(value).lower() not in ("yes", "y", "true"):
                # Go back to feature overview for corrections
                self.phase = InterviewPhase.FEATURE_OVERVIEW
                self._question_index = 0

    def _advance_phase(self) -> None:
        """Advance to the next interview phase."""
        self._question_index = 0

        if self.phase == InterviewPhase.FEATURE_OVERVIEW:
            self.phase = InterviewPhase.CONTEXT_GATHERING
        elif self.phase == InterviewPhase.CONTEXT_GATHERING:
            self.phase = InterviewPhase.TASK_DEFINITION
        elif self.phase == InterviewPhase.TASK_DEFINITION:
            self.phase = InterviewPhase.ACCEPTANCE_CRITERIA
        elif self.phase == InterviewPhase.ACCEPTANCE_CRITERIA:
            self.phase = InterviewPhase.REVIEW
        elif self.phase == InterviewPhase.REVIEW:
            self.phase = InterviewPhase.COMPLETE

    def get_response(self, question_id: str) -> Optional[Any]:
        """Get a response by question ID.

        Args:
            question_id: The question ID to look up.

        Returns:
            The response value or None if not found.
        """
        for response in reversed(self.responses):
            if response.question_id == question_id:
                return response.value
        return None

    def generate_prd(self) -> PRD:
        """Generate a PRD from interview responses.

        Returns:
            Generated PRD object.
        """
        # Build meta
        feature_name = self.get_response("feature_name") or "Untitled Feature"
        description = self.get_response("feature_description") or ""
        priority = self.get_response("priority") or "medium"

        # Generate slug from feature name
        slug = re.sub(r"[^a-z0-9]+", "_", feature_name.lower()).strip("_")

        meta = PRDMeta(
            feature_name=feature_name,
            feature_slug=slug,
            description=description,
            priority=priority,
            created_at=datetime.utcnow().strftime("%Y-%m-%d"),
        )

        # Build tasks
        prd_tasks = []
        for i, task_data in enumerate(self.tasks):
            task_id = task_data.get("id") or f"task-{i+1:03d}"
            test_cov_str = task_data.get("test_coverage", "unit")
            try:
                test_coverage = TestCoverage(test_cov_str)
            except ValueError:
                test_coverage = TestCoverage.UNIT

            task = PRDTask(
                id=task_id,
                phase=1,  # Default to phase 1
                category=task_data.get("category", "backend"),
                description=task_data.get("description", ""),
                steps=task_data.get("steps", []),
                passes=task_data.get("passes", False),
                test_coverage=test_coverage,
                blocked_by=task_data.get("blocked_by", []),
            )
            prd_tasks.append(task)

        return PRD(meta=meta, tasks=prd_tasks)

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of current interview state.

        Returns:
            Dict with interview summary.
        """
        return {
            "phase": self.phase.value,
            "is_complete": self.is_complete,
            "response_count": len(self.responses),
            "task_count": len(self.tasks),
            "feature_name": self.get_response("feature_name"),
            "template": self._template,
        }


def list_templates() -> list[dict[str, str]]:
    """List available PRD templates.

    Returns:
        List of template info dicts with 'id', 'name', 'description'.
    """
    return [
        {
            "id": template_id,
            "name": template_data["name"],
            "description": template_data["description"],
        }
        for template_id, template_data in PRD_TEMPLATES.items()
    ]


def get_template(template_id: str) -> Optional[dict[str, Any]]:
    """Get a template by ID.

    Args:
        template_id: Template identifier.

    Returns:
        Template dict or None if not found.
    """
    return PRD_TEMPLATES.get(template_id)


def review_prd(prd: PRD) -> list[str]:
    """Review a PRD and suggest improvements.

    Args:
        prd: PRD to review.

    Returns:
        List of suggestions.
    """
    suggestions = []

    # Check for description
    if not prd.meta.description:
        suggestions.append("Add a description to explain the feature's purpose.")

    # Check for empty tasks
    if not prd.tasks:
        suggestions.append("Add tasks to define the implementation steps.")

    # Check for tasks without steps
    for task in prd.tasks:
        if not task.steps:
            suggestions.append(f"Task '{task.id}' has no implementation steps.")

    # Check for test coverage
    no_test_tasks = [t for t in prd.tasks if t.test_coverage == TestCoverage.NONE]
    if len(no_test_tasks) > len(prd.tasks) * 0.5:
        suggestions.append(
            "Consider adding test coverage for more tasks. "
            f"{len(no_test_tasks)} of {len(prd.tasks)} tasks have no tests."
        )

    # Check for blocked_by consistency
    task_ids = {t.id for t in prd.tasks}
    for task in prd.tasks:
        for dep in task.blocked_by:
            if dep not in task_ids:
                suggestions.append(
                    f"Task '{task.id}' depends on '{dep}' which doesn't exist."
                )

    # Check for circular dependencies
    def has_circular_dep(task_id: str, visited: set[str]) -> bool:
        if task_id in visited:
            return True
        visited = visited | {task_id}
        task = next((t for t in prd.tasks if t.id == task_id), None)
        if task:
            for dep in task.blocked_by:
                if has_circular_dep(dep, visited):
                    return True
        return False

    for task in prd.tasks:
        if has_circular_dep(task.id, set()):
            suggestions.append(f"Task '{task.id}' has a circular dependency.")
            break

    return suggestions
