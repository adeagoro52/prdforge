"""Unit tests for PRD generation with interview mode."""

import pytest

from src.prd import (
    InterviewPhase,
    InterviewSession,
    PRD,
    PRDMeta,
    PRDTask,
    Question,
    QuestionType,
    TestCoverage,
    get_template,
    list_templates,
    review_prd,
)


class TestQuestion:
    """Tests for Question dataclass."""

    def test_default_question(self):
        """Test question with default values."""
        q = Question(id="test", text="What is this?")
        assert q.id == "test"
        assert q.text == "What is this?"
        assert q.question_type == QuestionType.TEXT
        assert q.required is True
        assert q.options == []

    def test_choice_question(self):
        """Test choice question with options."""
        q = Question(
            id="priority",
            text="What priority?",
            question_type=QuestionType.CHOICE,
            options=["low", "medium", "high"],
        )
        assert q.question_type == QuestionType.CHOICE
        assert q.options == ["low", "medium", "high"]


class TestInterviewSession:
    """Tests for InterviewSession class."""

    def test_initial_state(self):
        """Test initial session state."""
        session = InterviewSession()
        assert session.phase == InterviewPhase.FEATURE_OVERVIEW
        assert not session.is_complete
        assert len(session.responses) == 0
        assert len(session.tasks) == 0

    def test_initial_question(self):
        """Test getting the first question."""
        session = InterviewSession()
        question = session.get_current_question()
        assert question is not None
        assert question.id == "feature_name"

    def test_answer_advances_question(self):
        """Test that answering advances to next question."""
        session = InterviewSession()
        q1 = session.get_current_question()
        session.answer("My Feature")
        q2 = session.get_current_question()
        assert q1.id != q2.id

    def test_answer_stores_response(self):
        """Test that answers are stored."""
        session = InterviewSession()
        session.answer("My Feature")
        assert session.get_response("feature_name") == "My Feature"

    def test_phase_advances_after_questions(self):
        """Test phase advancement after all questions answered."""
        session = InterviewSession()

        # Answer all feature questions
        for _ in range(len(session._get_phase_questions())):
            session.answer("test")

        assert session.phase == InterviewPhase.CONTEXT_GATHERING

    def test_with_template(self):
        """Test session initialized with template."""
        session = InterviewSession(template="api_endpoint")
        assert len(session.tasks) > 0
        assert session.tasks[0]["category"] == "backend"

    def test_with_invalid_template(self):
        """Test session with invalid template name."""
        session = InterviewSession(template="nonexistent")
        assert len(session.tasks) == 0

    def test_get_summary(self):
        """Test getting session summary."""
        session = InterviewSession()
        session.answer("My Feature")

        summary = session.get_summary()
        assert summary["phase"] == InterviewPhase.FEATURE_OVERVIEW.value
        assert summary["is_complete"] is False
        assert summary["response_count"] == 1
        assert summary["feature_name"] == "My Feature"


class TestInterviewSessionComplete:
    """Tests for completing the interview process."""

    @pytest.fixture
    def complete_session(self):
        """Create a session with responses for all phases."""
        session = InterviewSession()

        # Feature overview
        session.answer("Test Feature")  # feature_name
        session.answer("A test feature")  # feature_description
        session.answer("medium")  # priority

        # Context gathering
        session.answer("Python, FastAPI")  # tech_stack
        session.answer("")  # dependencies
        session.answer("")  # constraints

        # Task definition (first task)
        session.answer("Implement the feature")  # task_description
        session.answer("backend")  # task_category
        session.answer("Step 1\nStep 2")  # task_steps
        session.answer("unit")  # task_test_coverage

        # Don't add another task
        session.answer("no")  # add_another_task

        # Review
        session.answer("yes")  # confirm_prd

        return session

    def test_complete_session_is_complete(self, complete_session):
        """Test that complete session is marked complete."""
        assert complete_session.is_complete

    def test_generate_prd(self, complete_session):
        """Test generating PRD from complete session."""
        prd = complete_session.generate_prd()

        assert prd.meta.feature_name == "Test Feature"
        assert prd.meta.description == "A test feature"
        assert prd.meta.priority == "medium"
        assert len(prd.tasks) == 1
        assert prd.tasks[0].description == "Implement the feature"
        assert prd.tasks[0].category == "backend"
        assert prd.tasks[0].steps == ["Step 1", "Step 2"]

    def test_prd_slug_generation(self, complete_session):
        """Test that PRD slug is generated from feature name."""
        prd = complete_session.generate_prd()
        assert prd.meta.feature_slug == "test_feature"


class TestInterviewReviewMode:
    """Tests for review mode with existing PRD."""

    @pytest.fixture
    def existing_prd(self):
        """Create an existing PRD."""
        return PRD(
            meta=PRDMeta(
                feature_name="Existing Feature",
                feature_slug="existing_feature",
                description="An existing feature",
                priority="high",
            ),
            tasks=[
                PRDTask(
                    id="task-001",
                    phase=1,
                    category="backend",
                    description="Existing task",
                    steps=["Step 1"],
                    passes=True,
                    test_coverage=TestCoverage.UNIT,
                )
            ],
        )

    def test_review_mode_initial_phase(self, existing_prd):
        """Test review mode starts at review phase."""
        session = InterviewSession(existing_prd=existing_prd)
        assert session.phase == InterviewPhase.REVIEW

    def test_review_mode_populates_responses(self, existing_prd):
        """Test review mode populates responses from PRD."""
        session = InterviewSession(existing_prd=existing_prd)
        assert session.get_response("feature_name") == "Existing Feature"
        assert session.get_response("priority") == "high"

    def test_review_mode_populates_tasks(self, existing_prd):
        """Test review mode populates tasks from PRD."""
        session = InterviewSession(existing_prd=existing_prd)
        assert len(session.tasks) == 1
        assert session.tasks[0]["id"] == "task-001"


class TestTemplates:
    """Tests for PRD template functionality."""

    def test_list_templates(self):
        """Test listing available templates."""
        templates = list_templates()
        assert len(templates) > 0
        assert all("id" in t and "name" in t and "description" in t for t in templates)

    def test_get_template(self):
        """Test getting a template by ID."""
        template = get_template("api_endpoint")
        assert template is not None
        assert "name" in template
        assert "tasks" in template

    def test_get_nonexistent_template(self):
        """Test getting a nonexistent template."""
        template = get_template("nonexistent")
        assert template is None

    def test_api_endpoint_template(self):
        """Test API endpoint template structure."""
        template = get_template("api_endpoint")
        assert template["name"] == "API Endpoint"
        assert len(template["tasks"]) >= 3


class TestReviewPrd:
    """Tests for PRD review functionality."""

    def test_review_empty_prd(self):
        """Test reviewing PRD with no tasks."""
        prd = PRD(
            meta=PRDMeta(feature_name="Test", feature_slug="test"),
            tasks=[],
        )
        suggestions = review_prd(prd)
        assert any("tasks" in s.lower() for s in suggestions)

    def test_review_prd_missing_description(self):
        """Test reviewing PRD with no description."""
        prd = PRD(
            meta=PRDMeta(feature_name="Test", feature_slug="test", description=""),
            tasks=[PRDTask(id="t1", phase=1, category="backend", description="Task")],
        )
        suggestions = review_prd(prd)
        assert any("description" in s.lower() for s in suggestions)

    def test_review_prd_task_without_steps(self):
        """Test reviewing PRD with task missing steps."""
        prd = PRD(
            meta=PRDMeta(feature_name="Test", feature_slug="test", description="Test desc"),
            tasks=[PRDTask(id="t1", phase=1, category="backend", description="Task", steps=[])],
        )
        suggestions = review_prd(prd)
        assert any("t1" in s and "steps" in s.lower() for s in suggestions)

    def test_review_prd_invalid_dependency(self):
        """Test reviewing PRD with invalid blocked_by reference."""
        prd = PRD(
            meta=PRDMeta(feature_name="Test", feature_slug="test", description="Test desc"),
            tasks=[
                PRDTask(
                    id="t1",
                    phase=1,
                    category="backend",
                    description="Task",
                    steps=["Step 1"],
                    blocked_by=["nonexistent"],
                )
            ],
        )
        suggestions = review_prd(prd)
        assert any("nonexistent" in s for s in suggestions)

    def test_review_valid_prd(self):
        """Test reviewing a valid PRD returns few/no suggestions."""
        prd = PRD(
            meta=PRDMeta(
                feature_name="Test Feature",
                feature_slug="test_feature",
                description="A well-defined feature",
            ),
            tasks=[
                PRDTask(
                    id="t1",
                    phase=1,
                    category="backend",
                    description="Task 1",
                    steps=["Step 1", "Step 2"],
                    test_coverage=TestCoverage.UNIT,
                ),
                PRDTask(
                    id="t2",
                    phase=1,
                    category="test",
                    description="Task 2",
                    steps=["Write tests"],
                    test_coverage=TestCoverage.INTEGRATION,
                    blocked_by=["t1"],
                ),
            ],
        )
        suggestions = review_prd(prd)
        # A well-formed PRD should have minimal suggestions
        assert len(suggestions) <= 1
