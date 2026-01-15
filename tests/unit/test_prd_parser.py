"""Unit tests for PRD parsing module."""

import json
import tempfile
from pathlib import Path

import pytest

from src.prd import (
    JSONPRDParser,
    MarkdownPRDParser,
    PRD,
    PRDConverter,
    PRDFormatDetector,
    PRDParseError,
    PRDTask,
    Phase,
    TaskCategory,
    TestCoverage,
    parse_prd,
    parse_prd_string,
)


class TestTaskCategory:
    """Tests for TaskCategory enum."""

    def test_from_string_valid(self):
        assert TaskCategory.from_string("backend") == TaskCategory.BACKEND
        assert TaskCategory.from_string("FRONTEND") == TaskCategory.FRONTEND
        assert TaskCategory.from_string("Config") == TaskCategory.CONFIG

    def test_from_string_invalid(self):
        assert TaskCategory.from_string("unknown") == TaskCategory.OTHER
        assert TaskCategory.from_string("") == TaskCategory.OTHER


class TestTestCoverage:
    """Tests for TestCoverage enum."""

    def test_from_string_valid(self):
        assert TestCoverage.from_string("unit") == TestCoverage.UNIT
        assert TestCoverage.from_string("INTEGRATION") == TestCoverage.INTEGRATION

    def test_from_string_invalid(self):
        assert TestCoverage.from_string("unknown") == TestCoverage.NONE


class TestPRDTask:
    """Tests for PRDTask model."""

    def test_is_blocked_no_deps(self):
        task = PRDTask(
            id="task-1",
            phase=1,
            category=TaskCategory.BACKEND,
            description="Test task",
        )
        assert not task.is_blocked(set())
        assert not task.is_blocked({"other-task"})

    def test_is_blocked_with_deps(self):
        task = PRDTask(
            id="task-2",
            phase=1,
            category=TaskCategory.BACKEND,
            description="Test task",
            blocked_by=["task-1"],
        )
        assert task.is_blocked(set())
        assert task.is_blocked({"other-task"})
        assert not task.is_blocked({"task-1"})


class TestPRD:
    """Tests for PRD model."""

    @pytest.fixture
    def sample_prd(self):
        from src.prd.models import PRDMeta

        return PRD(
            meta=PRDMeta(feature_name="Test Feature"),
            phases=[
                Phase(phase=1, name="Phase 1"),
                Phase(phase=2, name="Phase 2"),
            ],
            tasks=[
                PRDTask(id="p1-001", phase=1, category=TaskCategory.BACKEND,
                        description="Task 1", passes=True),
                PRDTask(id="p1-002", phase=1, category=TaskCategory.BACKEND,
                        description="Task 2", passes=False, blocked_by=["p1-001"]),
                PRDTask(id="p2-001", phase=2, category=TaskCategory.FRONTEND,
                        description="Task 3", passes=False),
            ],
        )

    def test_get_tasks_by_phase(self, sample_prd):
        phase1_tasks = sample_prd.get_tasks_by_phase(1)
        assert len(phase1_tasks) == 2
        assert all(t.phase == 1 for t in phase1_tasks)

    def test_get_pending_tasks(self, sample_prd):
        pending = sample_prd.get_pending_tasks()
        assert len(pending) == 2
        assert all(not t.passes for t in pending)

    def test_get_completed_tasks(self, sample_prd):
        completed = sample_prd.get_completed_tasks()
        assert len(completed) == 1
        assert completed[0].id == "p1-001"

    def test_get_task_by_id(self, sample_prd):
        task = sample_prd.get_task_by_id("p1-002")
        assert task is not None
        assert task.description == "Task 2"

        assert sample_prd.get_task_by_id("nonexistent") is None

    def test_get_executable_tasks(self, sample_prd):
        executable = sample_prd.get_executable_tasks()
        # p1-002 is blocked by p1-001 (completed), so it should be executable
        # p2-001 has no blockers, so it should be executable
        assert len(executable) == 2
        assert {t.id for t in executable} == {"p1-002", "p2-001"}

    def test_progress_percent(self, sample_prd):
        assert sample_prd.total_tasks == 3
        assert sample_prd.completed_count == 1
        assert sample_prd.progress_percent == pytest.approx(33.33, rel=0.1)


class TestJSONPRDParser:
    """Tests for JSON PRD parser."""

    @pytest.fixture
    def parser(self):
        return JSONPRDParser()

    def test_can_parse_valid_json(self, parser):
        assert parser.can_parse('{"tasks": []}')
        assert parser.can_parse('{"meta": {}, "phases": []}')

    def test_can_parse_invalid(self, parser):
        assert not parser.can_parse("# Markdown header")
        assert not parser.can_parse("not json at all")
        assert not parser.can_parse('{"random": "object"}')

    def test_parse_minimal(self, parser):
        content = '{"meta": {"feature_name": "Test"}, "tasks": []}'
        prd = parser.parse(content)
        assert prd.meta.feature_name == "Test"
        assert len(prd.tasks) == 0

    def test_parse_full_prd(self, parser):
        content = json.dumps({
            "meta": {
                "feature_name": "Test Feature",
                "feature_slug": "test_feature",
                "description": "A test PRD",
                "created_at": "2025-01-15",
                "project_name": "TestProject",
                "priority": "high",
            },
            "phases": [
                {"phase": 1, "name": "Setup", "description": "Initial setup"},
            ],
            "tasks": [
                {
                    "id": "phase1-001",
                    "phase": 1,
                    "category": "backend",
                    "description": "Create structure",
                    "steps": ["Step 1", "Step 2"],
                    "passes": False,
                    "test_coverage": "unit",
                    "blocked_by": [],
                },
            ],
        })

        prd = parser.parse(content)
        assert prd.meta.feature_name == "Test Feature"
        assert prd.meta.priority == "high"
        assert len(prd.phases) == 1
        assert prd.phases[0].name == "Setup"
        assert len(prd.tasks) == 1
        assert prd.tasks[0].id == "phase1-001"
        assert prd.tasks[0].category == TaskCategory.BACKEND
        assert prd.tasks[0].test_coverage == TestCoverage.UNIT

    def test_parse_invalid_json(self, parser):
        with pytest.raises(PRDParseError) as exc_info:
            parser.parse("not valid json")
        assert "Invalid JSON" in str(exc_info.value)

    def test_parse_missing_task_id(self, parser):
        content = '{"tasks": [{"description": "No ID"}]}'
        with pytest.raises(PRDParseError) as exc_info:
            parser.parse(content)
        assert "missing required 'id' field" in str(exc_info.value)


class TestMarkdownPRDParser:
    """Tests for Markdown PRD parser."""

    @pytest.fixture
    def parser(self):
        return MarkdownPRDParser()

    def test_can_parse_valid_markdown(self, parser):
        md = "# Feature\n\n## Phase 1: Setup\n\n### Task 1.1: Create\n- [ ] Step"
        assert parser.can_parse(md)

    def test_can_parse_invalid(self, parser):
        assert not parser.can_parse('{"json": "object"}')
        assert not parser.can_parse("plain text without headers")

    def test_parse_simple_prd(self, parser):
        md = """# My Feature

This is a test feature.

## Phase 1: Setup

### Task 1.1: Create structure
- [ ] Create directories
- [x] Add files

**Category:** backend
**Test coverage:** unit
"""
        prd = parser.parse(md)
        assert prd.meta.feature_name == "My Feature"
        assert len(prd.phases) == 1
        assert prd.phases[0].name == "Setup"
        assert len(prd.tasks) == 1
        assert prd.tasks[0].category == TaskCategory.BACKEND
        assert len(prd.tasks[0].steps) == 2

    def test_parse_with_frontmatter(self, parser):
        md = """---
title: Custom Title
project: MyProject
priority: high
date: 2025-01-15
---

# Feature Name

Description here.
"""
        prd = parser.parse(md)
        assert prd.meta.feature_name == "Custom Title"
        assert prd.meta.project_name == "MyProject"
        assert prd.meta.priority == "high"

    def test_parse_blocked_by(self, parser):
        md = """# Feature

## Phase 1: Setup

### Task 1.1: First
- [ ] Do something

### Task 1.2: Second
- [ ] Depends on first

**Blocked by:** phase1-001
"""
        prd = parser.parse(md)
        assert len(prd.tasks) == 2
        assert prd.tasks[1].blocked_by == ["phase1-001"]

    def test_all_steps_done_marks_passes(self, parser):
        md = """# Feature

## Phase 1: Setup

### Task 1.1: Complete task
- [x] Step 1
- [x] Step 2
"""
        prd = parser.parse(md)
        assert prd.tasks[0].passes is True


class TestPRDConverter:
    """Tests for PRD format converter."""

    @pytest.fixture
    def sample_prd(self):
        from src.prd.models import PRDMeta
        from datetime import datetime

        return PRD(
            meta=PRDMeta(
                feature_name="Test Feature",
                feature_slug="test_feature",
                description="A test PRD",
                created_at=datetime(2025, 1, 15),
                project_name="TestProject",
            ),
            phases=[Phase(phase=1, name="Setup", description="Initial setup")],
            tasks=[
                PRDTask(
                    id="phase1-001",
                    phase=1,
                    category=TaskCategory.BACKEND,
                    description="Create structure",
                    steps=["Step 1", "Step 2"],
                    passes=False,
                    test_coverage=TestCoverage.UNIT,
                    blocked_by=[],
                ),
            ],
        )

    def test_to_json(self, sample_prd):
        converter = PRDConverter()
        json_str = converter.to_json(sample_prd)
        data = json.loads(json_str)

        assert data["meta"]["feature_name"] == "Test Feature"
        assert len(data["phases"]) == 1
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["id"] == "phase1-001"

    def test_to_markdown(self, sample_prd):
        converter = PRDConverter()
        md = converter.to_markdown(sample_prd)

        assert "# Test Feature" in md
        assert "## Phase 1: Setup" in md
        assert "### Task phase1-001: Create structure" in md
        assert "- [ ] Step 1" in md
        assert "**Category:** backend" in md

    def test_roundtrip_json(self, sample_prd):
        """Test JSON -> parse -> JSON produces equivalent result."""
        converter = PRDConverter()
        json_parser = JSONPRDParser()

        json_str = converter.to_json(sample_prd)
        reparsed = json_parser.parse(json_str)

        assert reparsed.meta.feature_name == sample_prd.meta.feature_name
        assert len(reparsed.tasks) == len(sample_prd.tasks)
        assert reparsed.tasks[0].id == sample_prd.tasks[0].id


class TestPRDFormatDetector:
    """Tests for format auto-detection."""

    def test_detect_json_by_extension(self):
        assert PRDFormatDetector.detect_format(path="test.json") == "json"

    def test_detect_markdown_by_extension(self):
        assert PRDFormatDetector.detect_format(path="test.md") == "markdown"
        assert PRDFormatDetector.detect_format(path="test.markdown") == "markdown"

    def test_detect_json_by_content(self):
        content = '{"meta": {}, "tasks": []}'
        assert PRDFormatDetector.detect_format(content=content) == "json"

    def test_detect_markdown_by_content(self):
        content = "# Feature\n\n## Phase 1: Setup\n\n### Task 1.1: Test\n- [ ] Step"
        assert PRDFormatDetector.detect_format(content=content) == "markdown"

    def test_detect_unknown_format_raises(self):
        with pytest.raises(PRDParseError):
            PRDFormatDetector.detect_format(content="random text")

    def test_parse_file_json(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump({
                "meta": {"feature_name": "Test"},
                "tasks": [],
            }, f)
            f.flush()

            prd = parse_prd(f.name)
            assert prd.meta.feature_name == "Test"
            assert prd.source_format == "json"

    def test_parse_file_markdown(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        ) as f:
            f.write("# Test Feature\n\n## Phase 1: Setup\n")
            f.flush()

            prd = parse_prd(f.name)
            assert prd.meta.feature_name == "Test Feature"
            assert prd.source_format == "markdown"

    def test_parse_string_with_hint(self):
        content = '{"meta": {"feature_name": "Test"}, "tasks": []}'
        prd = parse_prd_string(content, format_hint="json")
        assert prd.meta.feature_name == "Test"

    def test_list_formats(self):
        formats = PRDFormatDetector.list_formats()
        assert "json" in formats
        assert "markdown" in formats

    def test_list_extensions(self):
        extensions = PRDFormatDetector.list_extensions()
        assert ".json" in extensions
        assert ".md" in extensions


class TestPRDParseError:
    """Tests for PRDParseError exception."""

    def test_error_with_source(self):
        err = PRDParseError("Test error", source="test.json", line=10)
        assert err.source == "test.json"
        assert err.line == 10
        assert "Test error" in str(err)
