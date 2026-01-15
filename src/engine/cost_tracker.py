"""Cost tracking service for PRDForge.

This module provides centralized cost tracking, budget management,
and alert generation for AI executor usage.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from src.db.database import Database
from src.db.models import AlertType, CostAlert, CostBudget, CostRecord
from src.db.cost_repository import CostRepository
from src.engine.logging import logger


# Consolidated pricing information per 1M tokens
# This is the single source of truth for all pricing
EXECUTOR_PRICING: dict[str, dict[str, dict[str, float]]] = {
    "claude-api": {
        "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},
        "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
        "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
        "claude-3-opus-20240229": {"input": 15.0, "output": 75.0},
        "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
        # Default pricing for unknown models
        "_default": {"input": 3.0, "output": 15.0},
    },
    "claude-cli": {
        # CLI uses same pricing as API
        "_default": {"input": 3.0, "output": 15.0},
    },
    "openai": {
        "gpt-4o": {"input": 5.0, "output": 15.0},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4-turbo": {"input": 10.0, "output": 30.0},
        "gpt-4": {"input": 30.0, "output": 60.0},
        "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
        "_default": {"input": 5.0, "output": 15.0},
    },
    "gemini": {
        "gemini-1.5-pro": {"input": 3.50, "output": 10.50},
        "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
        "gemini-1.5-flash-8b": {"input": 0.0375, "output": 0.15},
        "gemini-1.0-pro": {"input": 0.50, "output": 1.50},
        "_default": {"input": 3.50, "output": 10.50},
    },
    "dry-run": {
        "_default": {"input": 0.0, "output": 0.0},
    },
}


@dataclass
class CostEstimate:
    """Cost estimate for a potential operation."""

    executor: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float


@dataclass
class BudgetStatus:
    """Current budget status for a project."""

    project_id: int
    budget: CostBudget | None

    # Current spending
    daily_spent: float = 0.0
    monthly_spent: float = 0.0
    total_spent: float = 0.0

    # Budget utilization percentages
    daily_utilization: float | None = None
    monthly_utilization: float | None = None
    total_utilization: float | None = None

    # Whether budgets are exceeded
    daily_exceeded: bool = False
    monthly_exceeded: bool = False
    total_exceeded: bool = False

    # Whether any threshold is reached
    threshold_reached: bool = False
    is_blocked: bool = False  # Hard limit hit


class CostTracker:
    """Service for tracking AI executor costs.

    Features:
    - Cost calculation based on executor pricing
    - Token and cost tracking per task/run/project
    - Budget management with alerts
    - Cost reporting and analytics
    """

    def __init__(self, database: Database | None = None):
        """Initialize the cost tracker.

        Args:
            database: Optional database instance. If not provided,
                     a new default instance will be created.
        """
        self.db = database or Database()
        self.repository = CostRepository(self.db)

    def calculate_cost(
        self,
        executor: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float:
        """Calculate cost for an execution.

        Args:
            executor: Executor name (e.g., "openai", "claude-api").
            model: Model identifier.
            prompt_tokens: Number of input tokens.
            completion_tokens: Number of output tokens.

        Returns:
            Estimated cost in USD.
        """
        pricing = self._get_pricing(executor, model)

        input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
        output_cost = (completion_tokens / 1_000_000) * pricing["output"]

        return round(input_cost + output_cost, 6)

    def _get_pricing(self, executor: str, model: str) -> dict[str, float]:
        """Get pricing for an executor/model combination.

        Args:
            executor: Executor name.
            model: Model identifier.

        Returns:
            Dict with "input" and "output" prices per 1M tokens.
        """
        executor_pricing = EXECUTOR_PRICING.get(
            executor, EXECUTOR_PRICING.get("claude-api", {})
        )
        return executor_pricing.get(model, executor_pricing.get("_default", {"input": 3.0, "output": 15.0}))

    def estimate_cost(
        self,
        executor: str,
        model: str,
        prompt_tokens: int,
        estimated_completion_tokens: int | None = None,
    ) -> CostEstimate:
        """Estimate cost before execution.

        Args:
            executor: Executor name.
            model: Model identifier.
            prompt_tokens: Number of input tokens.
            estimated_completion_tokens: Estimated output tokens (defaults to prompt_tokens * 2).

        Returns:
            CostEstimate with projected cost.
        """
        if estimated_completion_tokens is None:
            # Heuristic: assume 2x prompt tokens for completion
            estimated_completion_tokens = prompt_tokens * 2

        cost = self.calculate_cost(
            executor, model, prompt_tokens, estimated_completion_tokens
        )

        return CostEstimate(
            executor=executor,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=estimated_completion_tokens,
            estimated_cost_usd=cost,
        )

    def record_cost(
        self,
        project_id: int,
        executor: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        run_id: int | None = None,
        task_execution_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CostRecord:
        """Record a cost after execution.

        Args:
            project_id: Project ID.
            executor: Executor name.
            model: Model identifier.
            prompt_tokens: Number of input tokens.
            completion_tokens: Number of output tokens.
            run_id: Optional run ID.
            task_execution_id: Optional task execution ID.
            metadata: Optional additional metadata.

        Returns:
            Created CostRecord.
        """
        total_tokens = prompt_tokens + completion_tokens
        cost = self.calculate_cost(executor, model, prompt_tokens, completion_tokens)

        record = CostRecord(
            id=None,
            project_id=project_id,
            run_id=run_id,
            task_execution_id=task_execution_id,
            executor=executor,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost,
            metadata_json=json.dumps(metadata or {}),
        )

        record = self.repository.create_cost_record(record)

        logger.debug(
            f"Recorded cost: ${cost:.6f} for {executor}/{model} "
            f"({total_tokens} tokens) - project {project_id}"
        )

        # Check budgets and create alerts if needed
        self._check_and_alert(project_id)

        return record

    def _check_and_alert(self, project_id: int) -> None:
        """Check budgets and create alerts if thresholds reached.

        Args:
            project_id: Project ID to check.
        """
        status = self.get_budget_status(project_id)

        if not status.budget:
            return

        # Check daily threshold
        if (
            status.daily_utilization is not None
            and status.daily_utilization >= status.budget.alert_threshold_percent
            and not status.daily_exceeded
        ):
            self._create_threshold_alert(
                project_id,
                AlertType.DAILY_THRESHOLD,
                status.budget.daily_budget_usd or 0,
                status.daily_spent,
                status.daily_utilization,
            )

        # Check daily exceeded
        if status.daily_exceeded:
            self._create_exceeded_alert(
                project_id,
                AlertType.DAILY_EXCEEDED,
                status.budget.daily_budget_usd or 0,
                status.daily_spent,
            )

        # Check monthly threshold
        if (
            status.monthly_utilization is not None
            and status.monthly_utilization >= status.budget.alert_threshold_percent
            and not status.monthly_exceeded
        ):
            self._create_threshold_alert(
                project_id,
                AlertType.MONTHLY_THRESHOLD,
                status.budget.monthly_budget_usd or 0,
                status.monthly_spent,
                status.monthly_utilization,
            )

        # Check monthly exceeded
        if status.monthly_exceeded:
            self._create_exceeded_alert(
                project_id,
                AlertType.MONTHLY_EXCEEDED,
                status.budget.monthly_budget_usd or 0,
                status.monthly_spent,
            )

        # Check total threshold
        if (
            status.total_utilization is not None
            and status.total_utilization >= status.budget.alert_threshold_percent
            and not status.total_exceeded
        ):
            self._create_threshold_alert(
                project_id,
                AlertType.TOTAL_THRESHOLD,
                status.budget.total_budget_usd or 0,
                status.total_spent,
                status.total_utilization,
            )

        # Check total exceeded
        if status.total_exceeded:
            self._create_exceeded_alert(
                project_id,
                AlertType.TOTAL_EXCEEDED,
                status.budget.total_budget_usd or 0,
                status.total_spent,
            )

    def _create_threshold_alert(
        self,
        project_id: int,
        alert_type: AlertType,
        budget_amount: float,
        current_amount: float,
        threshold_percent: float,
    ) -> None:
        """Create a threshold alert if one doesn't already exist.

        Args:
            project_id: Project ID.
            alert_type: Type of alert.
            budget_amount: Budget amount.
            current_amount: Current spending.
            threshold_percent: Threshold percentage.
        """
        # Check if similar unacknowledged alert exists
        existing = self.repository.get_alerts_for_project(
            project_id, unacknowledged_only=True
        )
        for alert in existing:
            if alert.alert_type == alert_type:
                return  # Don't create duplicate

        period = alert_type.value.split("_")[0].title()
        message = (
            f"{period} budget threshold reached: ${current_amount:.2f} "
            f"of ${budget_amount:.2f} ({threshold_percent:.1f}%)"
        )

        alert = CostAlert(
            id=None,
            project_id=project_id,
            alert_type=alert_type,
            message=message,
            budget_amount_usd=budget_amount,
            current_amount_usd=current_amount,
            threshold_percent=threshold_percent,
        )

        self.repository.create_alert(alert)
        logger.warning(f"Cost alert for project {project_id}: {message}")

    def _create_exceeded_alert(
        self,
        project_id: int,
        alert_type: AlertType,
        budget_amount: float,
        current_amount: float,
    ) -> None:
        """Create a budget exceeded alert if one doesn't already exist.

        Args:
            project_id: Project ID.
            alert_type: Type of alert.
            budget_amount: Budget amount.
            current_amount: Current spending.
        """
        # Check if similar unacknowledged alert exists
        existing = self.repository.get_alerts_for_project(
            project_id, unacknowledged_only=True
        )
        for alert in existing:
            if alert.alert_type == alert_type:
                return  # Don't create duplicate

        period = alert_type.value.split("_")[0].title()
        message = (
            f"{period} budget EXCEEDED: ${current_amount:.2f} "
            f"of ${budget_amount:.2f}"
        )

        alert = CostAlert(
            id=None,
            project_id=project_id,
            alert_type=alert_type,
            message=message,
            budget_amount_usd=budget_amount,
            current_amount_usd=current_amount,
            threshold_percent=100.0,
        )

        self.repository.create_alert(alert)
        logger.error(f"Budget exceeded for project {project_id}: {message}")

    def get_budget_status(self, project_id: int) -> BudgetStatus:
        """Get current budget status for a project.

        Args:
            project_id: Project ID.

        Returns:
            BudgetStatus with current spending and utilization.
        """
        budget = self.repository.get_budget_for_project(project_id)

        # Calculate current spending
        now = datetime.utcnow()
        daily_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        monthly_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        daily_spent = self.repository.get_total_cost_for_project(
            project_id, start_date=daily_start
        )
        monthly_spent = self.repository.get_total_cost_for_project(
            project_id, start_date=monthly_start
        )
        total_spent = self.repository.get_total_cost_for_project(project_id)

        status = BudgetStatus(
            project_id=project_id,
            budget=budget,
            daily_spent=daily_spent,
            monthly_spent=monthly_spent,
            total_spent=total_spent,
        )

        if budget:
            # Calculate utilization percentages
            if budget.daily_budget_usd and budget.daily_budget_usd > 0:
                status.daily_utilization = (daily_spent / budget.daily_budget_usd) * 100
                status.daily_exceeded = daily_spent > budget.daily_budget_usd

            if budget.monthly_budget_usd and budget.monthly_budget_usd > 0:
                status.monthly_utilization = (monthly_spent / budget.monthly_budget_usd) * 100
                status.monthly_exceeded = monthly_spent > budget.monthly_budget_usd

            if budget.total_budget_usd and budget.total_budget_usd > 0:
                status.total_utilization = (total_spent / budget.total_budget_usd) * 100
                status.total_exceeded = total_spent > budget.total_budget_usd

            # Check threshold
            status.threshold_reached = (
                (status.daily_utilization is not None and status.daily_utilization >= budget.alert_threshold_percent) or
                (status.monthly_utilization is not None and status.monthly_utilization >= budget.alert_threshold_percent) or
                (status.total_utilization is not None and status.total_utilization >= budget.alert_threshold_percent)
            )

            # Check hard limit
            status.is_blocked = (
                budget.is_hard_limit and
                (status.daily_exceeded or status.monthly_exceeded or status.total_exceeded)
            )

        return status

    def check_budget_allows_execution(self, project_id: int) -> tuple[bool, str | None]:
        """Check if budget allows execution.

        Args:
            project_id: Project ID.

        Returns:
            Tuple of (allowed, reason_if_blocked).
        """
        status = self.get_budget_status(project_id)

        if status.is_blocked:
            if status.daily_exceeded:
                return False, "Daily budget exceeded (hard limit)"
            if status.monthly_exceeded:
                return False, "Monthly budget exceeded (hard limit)"
            if status.total_exceeded:
                return False, "Total budget exceeded (hard limit)"

        return True, None

    def set_budget(
        self,
        project_id: int,
        daily_budget_usd: float | None = None,
        monthly_budget_usd: float | None = None,
        total_budget_usd: float | None = None,
        alert_threshold_percent: float = 80.0,
        is_hard_limit: bool = False,
    ) -> CostBudget:
        """Set budget for a project.

        Args:
            project_id: Project ID.
            daily_budget_usd: Daily budget limit.
            monthly_budget_usd: Monthly budget limit.
            total_budget_usd: Total budget limit.
            alert_threshold_percent: Alert threshold (0-100).
            is_hard_limit: Whether to block execution when exceeded.

        Returns:
            Created/updated budget.
        """
        budget = CostBudget(
            id=None,
            project_id=project_id,
            daily_budget_usd=daily_budget_usd,
            monthly_budget_usd=monthly_budget_usd,
            total_budget_usd=total_budget_usd,
            alert_threshold_percent=alert_threshold_percent,
            is_hard_limit=is_hard_limit,
        )

        return self.repository.create_or_update_budget(budget)

    def remove_budget(self, project_id: int) -> bool:
        """Remove budget for a project.

        Args:
            project_id: Project ID.

        Returns:
            True if removed, False if not found.
        """
        return self.repository.delete_budget(project_id)

    # ==================== Reporting ====================

    def get_project_cost_summary(
        self,
        project_id: int,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict:
        """Get cost summary for a project.

        Args:
            project_id: Project ID.
            start_date: Optional start date.
            end_date: Optional end date.

        Returns:
            Dict with cost summary.
        """
        total_cost = self.repository.get_total_cost_for_project(
            project_id, start_date, end_date
        )
        breakdown = self.repository.get_cost_breakdown_by_executor(
            project_id, start_date, end_date
        )
        daily_costs = self.repository.get_daily_costs(project_id)

        return {
            "project_id": project_id,
            "total_cost_usd": total_cost,
            "breakdown_by_executor": breakdown,
            "daily_costs": daily_costs,
            "period": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None,
            },
        }

    def get_run_cost_summary(self, run_id: int) -> dict:
        """Get cost summary for a run.

        Args:
            run_id: Run ID.

        Returns:
            Dict with cost summary.
        """
        records = self.repository.get_cost_records_for_run(run_id)
        total_cost = sum(r.cost_usd for r in records)
        total_tokens = sum(r.total_tokens for r in records)

        by_executor: dict[str, dict] = {}
        for record in records:
            if record.executor not in by_executor:
                by_executor[record.executor] = {
                    "cost": 0.0,
                    "tokens": 0,
                    "count": 0,
                }
            by_executor[record.executor]["cost"] += record.cost_usd
            by_executor[record.executor]["tokens"] += record.total_tokens
            by_executor[record.executor]["count"] += 1

        return {
            "run_id": run_id,
            "total_cost_usd": total_cost,
            "total_tokens": total_tokens,
            "task_count": len(records),
            "by_executor": by_executor,
        }

    def get_alerts(
        self,
        project_id: int,
        unacknowledged_only: bool = False,
    ) -> list[CostAlert]:
        """Get alerts for a project.

        Args:
            project_id: Project ID.
            unacknowledged_only: Only return unacknowledged alerts.

        Returns:
            List of alerts.
        """
        return self.repository.get_alerts_for_project(
            project_id, unacknowledged_only
        )

    def acknowledge_alert(self, alert_id: int) -> bool:
        """Acknowledge an alert.

        Args:
            alert_id: Alert ID.

        Returns:
            True if acknowledged.
        """
        return self.repository.acknowledge_alert(alert_id)

    def acknowledge_all_alerts(self, project_id: int) -> int:
        """Acknowledge all alerts for a project.

        Args:
            project_id: Project ID.

        Returns:
            Number of alerts acknowledged.
        """
        return self.repository.acknowledge_all_alerts(project_id)

    def get_global_cost_summary(self) -> dict:
        """Get cost summary across all projects.

        Returns:
            Dict with global cost summary.
        """
        summaries = self.repository.get_all_projects_cost_summary()

        total_cost = sum(s["total_cost"] for s in summaries)
        total_tokens = sum(s["total_tokens"] for s in summaries)
        total_records = sum(s["record_count"] for s in summaries)

        return {
            "total_cost_usd": total_cost,
            "total_tokens": total_tokens,
            "total_records": total_records,
            "project_count": len(summaries),
            "by_project": summaries,
        }


# Singleton instance for easy access
_cost_tracker: CostTracker | None = None


def get_cost_tracker(database: Database | None = None) -> CostTracker:
    """Get the global cost tracker instance.

    Args:
        database: Optional database instance.

    Returns:
        CostTracker instance.
    """
    global _cost_tracker
    if _cost_tracker is None:
        _cost_tracker = CostTracker(database)
    return _cost_tracker
