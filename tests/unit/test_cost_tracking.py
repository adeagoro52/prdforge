"""Unit tests for cost tracking functionality."""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.db import AlertType, CostAlert, CostBudget, CostRecord, CostRepository, Database
from src.engine.cost_tracker import (
    EXECUTOR_PRICING,
    BudgetStatus,
    CostEstimate,
    CostTracker,
    get_cost_tracker,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    db = Database(db_path)
    db.initialize()
    yield db

    # Cleanup
    db_path.unlink(missing_ok=True)


@pytest.fixture
def cost_repo(temp_db):
    """Create a cost repository for testing."""
    return CostRepository(temp_db)


@pytest.fixture
def cost_tracker(temp_db):
    """Create a cost tracker for testing."""
    return CostTracker(temp_db)


@pytest.fixture
def test_project_id(temp_db):
    """Create a test project and return its ID."""
    from src.db import ProjectRepository, Project

    repo = ProjectRepository(temp_db)
    # create() returns the project ID directly
    project_id = repo.create(Project(
        id=None,
        name="test-project",
        path="/tmp/test-project",
    ))
    return project_id


class TestExecutorPricing:
    """Test executor pricing configuration."""

    def test_claude_api_pricing_exists(self):
        """Test Claude API pricing is defined."""
        assert "claude-api" in EXECUTOR_PRICING
        assert "claude-sonnet-4-20250514" in EXECUTOR_PRICING["claude-api"]
        assert "_default" in EXECUTOR_PRICING["claude-api"]

    def test_openai_pricing_exists(self):
        """Test OpenAI pricing is defined."""
        assert "openai" in EXECUTOR_PRICING
        assert "gpt-4o" in EXECUTOR_PRICING["openai"]
        assert "gpt-4o-mini" in EXECUTOR_PRICING["openai"]

    def test_gemini_pricing_exists(self):
        """Test Gemini pricing is defined."""
        assert "gemini" in EXECUTOR_PRICING
        assert "gemini-1.5-pro" in EXECUTOR_PRICING["gemini"]
        assert "gemini-1.5-flash" in EXECUTOR_PRICING["gemini"]

    def test_dry_run_pricing_is_zero(self):
        """Test dry-run executor has zero cost."""
        assert "dry-run" in EXECUTOR_PRICING
        assert EXECUTOR_PRICING["dry-run"]["_default"]["input"] == 0.0
        assert EXECUTOR_PRICING["dry-run"]["_default"]["output"] == 0.0

    def test_pricing_has_input_and_output(self):
        """Test all pricing has input and output."""
        for executor, models in EXECUTOR_PRICING.items():
            for model, pricing in models.items():
                assert "input" in pricing, f"{executor}/{model} missing input pricing"
                assert "output" in pricing, f"{executor}/{model} missing output pricing"


class TestCostCalculation:
    """Test cost calculation logic."""

    def test_calculate_cost_openai_gpt4o(self, cost_tracker):
        """Test cost calculation for GPT-4o."""
        # GPT-4o: $5/1M input, $15/1M output
        cost = cost_tracker.calculate_cost(
            executor="openai",
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
        )
        # Expected: (1000/1M * 5) + (500/1M * 15) = 0.005 + 0.0075 = 0.0125
        assert cost == pytest.approx(0.0125, rel=0.001)

    def test_calculate_cost_openai_mini(self, cost_tracker):
        """Test cost calculation for GPT-4o-mini."""
        # GPT-4o-mini: $0.15/1M input, $0.60/1M output
        cost = cost_tracker.calculate_cost(
            executor="openai",
            model="gpt-4o-mini",
            prompt_tokens=10000,
            completion_tokens=5000,
        )
        # Expected: (10000/1M * 0.15) + (5000/1M * 0.60) = 0.0015 + 0.003 = 0.0045
        assert cost == pytest.approx(0.0045, rel=0.001)

    def test_calculate_cost_claude_sonnet(self, cost_tracker):
        """Test cost calculation for Claude Sonnet."""
        # Claude Sonnet: $3/1M input, $15/1M output
        cost = cost_tracker.calculate_cost(
            executor="claude-api",
            model="claude-sonnet-4-20250514",
            prompt_tokens=2000,
            completion_tokens=1000,
        )
        # Expected: (2000/1M * 3) + (1000/1M * 15) = 0.006 + 0.015 = 0.021
        assert cost == pytest.approx(0.021, rel=0.001)

    def test_calculate_cost_dry_run(self, cost_tracker):
        """Test cost calculation for dry-run (should be zero)."""
        cost = cost_tracker.calculate_cost(
            executor="dry-run",
            model="any-model",
            prompt_tokens=100000,
            completion_tokens=50000,
        )
        assert cost == 0.0

    def test_calculate_cost_unknown_model_uses_default(self, cost_tracker):
        """Test unknown model uses default pricing."""
        cost1 = cost_tracker.calculate_cost(
            executor="openai",
            model="unknown-model",
            prompt_tokens=1000,
            completion_tokens=500,
        )
        cost2 = cost_tracker.calculate_cost(
            executor="openai",
            model="gpt-4o",  # Default
            prompt_tokens=1000,
            completion_tokens=500,
        )
        assert cost1 == cost2

    def test_estimate_cost_with_completion_tokens(self, cost_tracker):
        """Test cost estimation with specified completion tokens."""
        estimate = cost_tracker.estimate_cost(
            executor="openai",
            model="gpt-4o",
            prompt_tokens=1000,
            estimated_completion_tokens=500,
        )
        assert isinstance(estimate, CostEstimate)
        assert estimate.executor == "openai"
        assert estimate.model == "gpt-4o"
        assert estimate.prompt_tokens == 1000
        assert estimate.completion_tokens == 500
        assert estimate.estimated_cost_usd > 0

    def test_estimate_cost_without_completion_tokens(self, cost_tracker):
        """Test cost estimation defaults to 2x prompt tokens."""
        estimate = cost_tracker.estimate_cost(
            executor="openai",
            model="gpt-4o",
            prompt_tokens=1000,
        )
        assert estimate.completion_tokens == 2000  # 2x prompt tokens


class TestCostRecord:
    """Test cost record model."""

    def test_cost_record_creation(self):
        """Test creating a cost record."""
        record = CostRecord(
            id=None,
            project_id=1,
            executor="openai",
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
            cost_usd=0.0125,
        )
        assert record.project_id == 1
        assert record.total_tokens == 1500

    def test_cost_record_metadata(self):
        """Test cost record metadata parsing."""
        record = CostRecord(
            id=None,
            project_id=1,
            executor="openai",
            model="gpt-4o",
            metadata_json='{"task_id": "phase1-001"}',
        )
        assert record.metadata == {"task_id": "phase1-001"}

    def test_cost_record_invalid_metadata(self):
        """Test cost record handles invalid JSON metadata."""
        record = CostRecord(
            id=None,
            project_id=1,
            executor="openai",
            model="gpt-4o",
            metadata_json="not valid json",
        )
        assert record.metadata == {}


class TestCostRepository:
    """Test cost repository operations."""

    def test_create_cost_record(self, cost_repo, test_project_id):
        """Test creating a cost record in database."""
        record = CostRecord(
            id=None,
            project_id=test_project_id,
            executor="openai",
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
            cost_usd=0.0125,
        )
        saved = cost_repo.create_cost_record(record)
        assert saved.id is not None

    def test_get_cost_records_for_project(self, cost_repo, test_project_id):
        """Test retrieving cost records for a project."""
        # Create some records
        for i in range(3):
            record = CostRecord(
                id=None,
                project_id=test_project_id,
                executor="openai",
                model="gpt-4o",
                prompt_tokens=1000 * (i + 1),
                completion_tokens=500,
                total_tokens=1500 + 1000 * i,
                cost_usd=0.01 * (i + 1),
            )
            cost_repo.create_cost_record(record)

        records = cost_repo.get_cost_records_for_project(test_project_id)
        assert len(records) == 3

    def test_get_total_cost_for_project(self, cost_repo, test_project_id):
        """Test calculating total cost for a project."""
        costs = [0.01, 0.02, 0.03]
        for c in costs:
            record = CostRecord(
                id=None,
                project_id=test_project_id,
                executor="openai",
                model="gpt-4o",
                prompt_tokens=1000,
                completion_tokens=500,
                total_tokens=1500,
                cost_usd=c,
            )
            cost_repo.create_cost_record(record)

        total = cost_repo.get_total_cost_for_project(test_project_id)
        assert total == pytest.approx(0.06, rel=0.001)

    def test_get_cost_breakdown_by_executor(self, cost_repo, test_project_id):
        """Test cost breakdown by executor."""
        # Create records for different executors
        for executor in ["openai", "openai", "claude-api"]:
            record = CostRecord(
                id=None,
                project_id=test_project_id,
                executor=executor,
                model="model-1",
                prompt_tokens=1000,
                completion_tokens=500,
                total_tokens=1500,
                cost_usd=0.01,
            )
            cost_repo.create_cost_record(record)

        breakdown = cost_repo.get_cost_breakdown_by_executor(test_project_id)
        assert "openai" in breakdown
        assert "claude-api" in breakdown
        assert breakdown["openai"]["record_count"] == 2
        assert breakdown["claude-api"]["record_count"] == 1


class TestCostBudget:
    """Test cost budget functionality."""

    def test_create_budget(self, cost_repo, test_project_id):
        """Test creating a budget."""
        budget = CostBudget(
            id=None,
            project_id=test_project_id,
            daily_budget_usd=10.0,
            monthly_budget_usd=100.0,
            alert_threshold_percent=80.0,
        )
        saved = cost_repo.create_or_update_budget(budget)
        assert saved.id is not None

    def test_get_budget(self, cost_repo, test_project_id):
        """Test retrieving a budget."""
        budget = CostBudget(
            id=None,
            project_id=test_project_id,
            daily_budget_usd=10.0,
            monthly_budget_usd=100.0,
        )
        cost_repo.create_or_update_budget(budget)

        retrieved = cost_repo.get_budget_for_project(test_project_id)
        assert retrieved is not None
        assert retrieved.daily_budget_usd == 10.0
        assert retrieved.monthly_budget_usd == 100.0

    def test_update_budget(self, cost_repo, test_project_id):
        """Test updating a budget."""
        budget = CostBudget(
            id=None,
            project_id=test_project_id,
            daily_budget_usd=10.0,
        )
        cost_repo.create_or_update_budget(budget)

        # Update
        budget.daily_budget_usd = 20.0
        cost_repo.create_or_update_budget(budget)

        retrieved = cost_repo.get_budget_for_project(test_project_id)
        assert retrieved.daily_budget_usd == 20.0

    def test_delete_budget(self, cost_repo, test_project_id):
        """Test deleting a budget."""
        budget = CostBudget(
            id=None,
            project_id=test_project_id,
            daily_budget_usd=10.0,
        )
        cost_repo.create_or_update_budget(budget)

        assert cost_repo.delete_budget(test_project_id) is True
        assert cost_repo.get_budget_for_project(test_project_id) is None


class TestCostAlerts:
    """Test cost alert functionality."""

    def test_create_alert(self, cost_repo, test_project_id):
        """Test creating an alert."""
        alert = CostAlert(
            id=None,
            project_id=test_project_id,
            alert_type=AlertType.DAILY_THRESHOLD,
            message="Daily budget threshold reached",
            budget_amount_usd=10.0,
            current_amount_usd=8.5,
            threshold_percent=85.0,
        )
        saved = cost_repo.create_alert(alert)
        assert saved.id is not None

    def test_get_alerts(self, cost_repo, test_project_id):
        """Test retrieving alerts."""
        alert = CostAlert(
            id=None,
            project_id=test_project_id,
            alert_type=AlertType.DAILY_THRESHOLD,
            message="Test alert",
        )
        cost_repo.create_alert(alert)

        alerts = cost_repo.get_alerts_for_project(test_project_id)
        assert len(alerts) == 1
        assert alerts[0].alert_type == AlertType.DAILY_THRESHOLD

    def test_acknowledge_alert(self, cost_repo, test_project_id):
        """Test acknowledging an alert."""
        alert = CostAlert(
            id=None,
            project_id=test_project_id,
            alert_type=AlertType.DAILY_THRESHOLD,
            message="Test alert",
        )
        saved = cost_repo.create_alert(alert)

        assert cost_repo.acknowledge_alert(saved.id) is True

        alerts = cost_repo.get_alerts_for_project(test_project_id, unacknowledged_only=True)
        assert len(alerts) == 0

    def test_acknowledge_all_alerts(self, cost_repo, test_project_id):
        """Test acknowledging all alerts."""
        for i in range(3):
            alert = CostAlert(
                id=None,
                project_id=test_project_id,
                alert_type=AlertType.DAILY_THRESHOLD,
                message=f"Test alert {i}",
            )
            cost_repo.create_alert(alert)

        count = cost_repo.acknowledge_all_alerts(test_project_id)
        assert count == 3


class TestCostTracker:
    """Test CostTracker service."""

    def test_record_cost(self, cost_tracker, test_project_id):
        """Test recording a cost."""
        record = cost_tracker.record_cost(
            project_id=test_project_id,
            executor="openai",
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
        )
        assert record.id is not None
        assert record.cost_usd > 0
        assert record.total_tokens == 1500

    def test_record_cost_with_metadata(self, cost_tracker, test_project_id):
        """Test recording a cost with metadata."""
        record = cost_tracker.record_cost(
            project_id=test_project_id,
            executor="openai",
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
            metadata={"task_id": "phase1-001"},
        )
        assert record.metadata == {"task_id": "phase1-001"}

    def test_get_budget_status_no_budget(self, cost_tracker, test_project_id):
        """Test budget status when no budget is set."""
        status = cost_tracker.get_budget_status(test_project_id)
        assert status.budget is None
        assert status.is_blocked is False

    def test_get_budget_status_with_budget(self, cost_tracker, test_project_id):
        """Test budget status with a budget set."""
        cost_tracker.set_budget(
            project_id=test_project_id,
            daily_budget_usd=10.0,
            monthly_budget_usd=100.0,
        )

        # Add some costs
        cost_tracker.record_cost(
            project_id=test_project_id,
            executor="openai",
            model="gpt-4o",
            prompt_tokens=100000,  # Should generate ~$0.5 cost
            completion_tokens=50000,
        )

        status = cost_tracker.get_budget_status(test_project_id)
        assert status.budget is not None
        assert status.daily_spent > 0
        assert status.total_spent > 0

    def test_budget_blocking_when_exceeded(self, cost_tracker, test_project_id):
        """Test budget blocking when hard limit exceeded."""
        cost_tracker.set_budget(
            project_id=test_project_id,
            daily_budget_usd=0.001,  # Very small budget
            is_hard_limit=True,
        )

        # Add cost that exceeds budget
        cost_tracker.record_cost(
            project_id=test_project_id,
            executor="openai",
            model="gpt-4o",
            prompt_tokens=10000,
            completion_tokens=5000,
        )

        allowed, reason = cost_tracker.check_budget_allows_execution(test_project_id)
        assert allowed is False
        assert "exceeded" in reason.lower()

    def test_budget_not_blocking_when_soft_limit(self, cost_tracker, test_project_id):
        """Test budget not blocking when soft limit exceeded."""
        cost_tracker.set_budget(
            project_id=test_project_id,
            daily_budget_usd=0.001,  # Very small budget
            is_hard_limit=False,  # Soft limit
        )

        # Add cost that exceeds budget
        cost_tracker.record_cost(
            project_id=test_project_id,
            executor="openai",
            model="gpt-4o",
            prompt_tokens=10000,
            completion_tokens=5000,
        )

        allowed, reason = cost_tracker.check_budget_allows_execution(test_project_id)
        assert allowed is True
        assert reason is None

    def test_get_project_cost_summary(self, cost_tracker, test_project_id):
        """Test getting project cost summary."""
        # Add some costs
        for _ in range(3):
            cost_tracker.record_cost(
                project_id=test_project_id,
                executor="openai",
                model="gpt-4o",
                prompt_tokens=1000,
                completion_tokens=500,
            )

        summary = cost_tracker.get_project_cost_summary(test_project_id)
        assert summary["project_id"] == test_project_id
        assert summary["total_cost_usd"] > 0
        assert "breakdown_by_executor" in summary
        assert "daily_costs" in summary

    def test_get_run_cost_summary(self, cost_tracker, test_project_id, temp_db):
        """Test getting run cost summary."""
        from src.db import RunRepository, Run

        # Create a run (create() returns the run ID)
        run_repo = RunRepository(temp_db)
        run_db_id = run_repo.create(Run(
            id=None,
            run_id="test-run-123",
            project_id=test_project_id,
            prd_path="/tmp/test.json",
        ))

        # Add costs for the run
        cost_tracker.record_cost(
            project_id=test_project_id,
            executor="openai",
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
            run_id=run_db_id,
        )

        summary = cost_tracker.get_run_cost_summary(run_db_id)
        assert summary["run_id"] == run_db_id
        assert summary["total_cost_usd"] > 0
        assert summary["task_count"] == 1

    def test_get_global_cost_summary(self, cost_tracker, test_project_id, temp_db):
        """Test getting global cost summary."""
        # Add costs
        cost_tracker.record_cost(
            project_id=test_project_id,
            executor="openai",
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
        )

        summary = cost_tracker.get_global_cost_summary()
        assert summary["total_cost_usd"] > 0
        assert summary["total_records"] >= 1
        assert summary["project_count"] >= 1


class TestCostTrackerSingleton:
    """Test cost tracker singleton pattern."""

    def test_get_cost_tracker_returns_same_instance(self, temp_db):
        """Test singleton pattern returns same instance."""
        # Reset singleton
        import src.engine.cost_tracker as ct
        ct._cost_tracker = None

        tracker1 = get_cost_tracker(temp_db)
        tracker2 = get_cost_tracker()

        assert tracker1 is tracker2


class TestAlertGeneration:
    """Test automatic alert generation."""

    def test_threshold_alert_generated(self, cost_tracker, test_project_id):
        """Test threshold alert is generated when threshold reached (not exceeded)."""
        # Set a larger budget so we can hit threshold without exceeding
        cost_tracker.set_budget(
            project_id=test_project_id,
            daily_budget_usd=0.10,  # 10 cents
            alert_threshold_percent=50.0,
        )

        # Add cost that hits ~60% threshold (between 50% and 100%)
        # GPT-4o: $5/1M input, $15/1M output
        # 1000 prompt + 500 completion = (1000/1M * 5) + (500/1M * 15) = 0.0125
        # This is 12.5% of 0.10 budget, not enough for threshold
        # Need about $0.05-$0.06 to hit 50-60% threshold
        # 4000 prompt + 2000 completion = (4000/1M * 5) + (2000/1M * 15) = 0.02 + 0.03 = 0.05
        cost_tracker.record_cost(
            project_id=test_project_id,
            executor="openai",
            model="gpt-4o",
            prompt_tokens=4000,
            completion_tokens=2000,
        )
        # Add a bit more to push past 50% threshold
        cost_tracker.record_cost(
            project_id=test_project_id,
            executor="openai",
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
        )

        alerts = cost_tracker.get_alerts(test_project_id, unacknowledged_only=True)
        # Should have at least one threshold alert (since we're at ~62.5% of budget)
        threshold_alerts = [a for a in alerts if "threshold" in a.alert_type.value.lower()]
        assert len(threshold_alerts) >= 1

    def test_exceeded_alert_generated(self, cost_tracker, test_project_id):
        """Test exceeded alert is generated when budget exceeded."""
        # Set a very small budget
        cost_tracker.set_budget(
            project_id=test_project_id,
            daily_budget_usd=0.0001,
            alert_threshold_percent=80.0,
        )

        # Add cost that exceeds budget
        cost_tracker.record_cost(
            project_id=test_project_id,
            executor="openai",
            model="gpt-4o",
            prompt_tokens=10000,
            completion_tokens=5000,
        )

        alerts = cost_tracker.get_alerts(test_project_id, unacknowledged_only=True)
        exceeded_alerts = [a for a in alerts if "exceeded" in a.alert_type.value.lower()]
        assert len(exceeded_alerts) >= 1
