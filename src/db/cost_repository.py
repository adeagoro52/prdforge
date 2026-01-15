"""Cost tracking repository for PRDForge.

This module provides database operations for cost records, budgets, and alerts.
"""

import json
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from .models import AlertType, CostAlert, CostBudget, CostRecord

if TYPE_CHECKING:
    from .database import Database


class CostRepository:
    """Repository for cost tracking data."""

    def __init__(self, database: "Database"):
        """Initialize cost repository.

        Args:
            database: Database instance.
        """
        self.db = database

    # ==================== Cost Records ====================

    def create_cost_record(self, record: CostRecord) -> CostRecord:
        """Create a new cost record.

        Args:
            record: Cost record to create.

        Returns:
            Created record with ID.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO cost_records (
                    project_id, run_id, task_execution_id, executor, model,
                    prompt_tokens, completion_tokens, total_tokens, cost_usd,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.project_id,
                    record.run_id,
                    record.task_execution_id,
                    record.executor,
                    record.model,
                    record.prompt_tokens,
                    record.completion_tokens,
                    record.total_tokens,
                    record.cost_usd,
                    record.metadata_json,
                ),
            )
            record.id = cursor.lastrowid
            return record

    def get_cost_records_for_project(
        self,
        project_id: int,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
    ) -> list[CostRecord]:
        """Get cost records for a project.

        Args:
            project_id: Project ID.
            start_date: Optional start date filter.
            end_date: Optional end date filter.
            limit: Maximum number of records.

        Returns:
            List of cost records.
        """
        query = "SELECT * FROM cost_records WHERE project_id = ?"
        params: list = [project_id]

        if start_date:
            query += " AND created_at >= ?"
            params.append(start_date)
        if end_date:
            query += " AND created_at <= ?"
            params.append(end_date)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self.db.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_cost_record(row) for row in rows]

    def get_cost_records_for_run(self, run_id: int) -> list[CostRecord]:
        """Get cost records for a specific run.

        Args:
            run_id: Run ID.

        Returns:
            List of cost records.
        """
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM cost_records WHERE run_id = ? ORDER BY created_at",
                (run_id,),
            ).fetchall()
            return [self._row_to_cost_record(row) for row in rows]

    def get_total_cost_for_project(
        self,
        project_id: int,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> float:
        """Get total cost for a project.

        Args:
            project_id: Project ID.
            start_date: Optional start date filter.
            end_date: Optional end date filter.

        Returns:
            Total cost in USD.
        """
        query = "SELECT COALESCE(SUM(cost_usd), 0) FROM cost_records WHERE project_id = ?"
        params: list = [project_id]

        if start_date:
            query += " AND created_at >= ?"
            params.append(start_date)
        if end_date:
            query += " AND created_at <= ?"
            params.append(end_date)

        with self.db.connection() as conn:
            result = conn.execute(query, params).fetchone()
            return float(result[0]) if result else 0.0

    def get_total_cost_for_run(self, run_id: int) -> float:
        """Get total cost for a run.

        Args:
            run_id: Run ID.

        Returns:
            Total cost in USD.
        """
        with self.db.connection() as conn:
            result = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) FROM cost_records WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            return float(result[0]) if result else 0.0

    def get_cost_breakdown_by_executor(
        self,
        project_id: int,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, dict]:
        """Get cost breakdown by executor for a project.

        Args:
            project_id: Project ID.
            start_date: Optional start date filter.
            end_date: Optional end date filter.

        Returns:
            Dict mapping executor names to cost/token stats.
        """
        query = """
            SELECT executor, model,
                   SUM(prompt_tokens) as prompt_tokens,
                   SUM(completion_tokens) as completion_tokens,
                   SUM(total_tokens) as total_tokens,
                   SUM(cost_usd) as total_cost,
                   COUNT(*) as record_count
            FROM cost_records WHERE project_id = ?
        """
        params: list = [project_id]

        if start_date:
            query += " AND created_at >= ?"
            params.append(start_date)
        if end_date:
            query += " AND created_at <= ?"
            params.append(end_date)

        query += " GROUP BY executor, model"

        with self.db.connection() as conn:
            rows = conn.execute(query, params).fetchall()

        breakdown: dict[str, dict] = {}
        for row in rows:
            executor = row[0]
            if executor not in breakdown:
                breakdown[executor] = {
                    "total_cost": 0.0,
                    "total_tokens": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "record_count": 0,
                    "models": {},
                }

            model = row[1]
            model_stats = {
                "prompt_tokens": row[2] or 0,
                "completion_tokens": row[3] or 0,
                "total_tokens": row[4] or 0,
                "cost": row[5] or 0.0,
                "count": row[6] or 0,
            }

            breakdown[executor]["models"][model] = model_stats
            breakdown[executor]["total_cost"] += model_stats["cost"]
            breakdown[executor]["total_tokens"] += model_stats["total_tokens"]
            breakdown[executor]["prompt_tokens"] += model_stats["prompt_tokens"]
            breakdown[executor]["completion_tokens"] += model_stats["completion_tokens"]
            breakdown[executor]["record_count"] += model_stats["count"]

        return breakdown

    def get_daily_costs(
        self,
        project_id: int,
        days: int = 30,
    ) -> list[dict]:
        """Get daily cost breakdown for a project.

        Args:
            project_id: Project ID.
            days: Number of days to look back.

        Returns:
            List of dicts with date and cost.
        """
        start_date = datetime.utcnow() - timedelta(days=days)

        query = """
            SELECT DATE(created_at) as date,
                   SUM(cost_usd) as total_cost,
                   SUM(total_tokens) as total_tokens
            FROM cost_records
            WHERE project_id = ? AND created_at >= ?
            GROUP BY DATE(created_at)
            ORDER BY date
        """

        with self.db.connection() as conn:
            rows = conn.execute(query, (project_id, start_date)).fetchall()

        return [
            {
                "date": row[0],
                "cost": row[1] or 0.0,
                "tokens": row[2] or 0,
            }
            for row in rows
        ]

    def _row_to_cost_record(self, row) -> CostRecord:
        """Convert a database row to a CostRecord.

        Args:
            row: Database row.

        Returns:
            CostRecord instance.
        """
        return CostRecord(
            id=row[0],
            project_id=row[1],
            run_id=row[2],
            task_execution_id=row[3],
            executor=row[4],
            model=row[5],
            prompt_tokens=row[6],
            completion_tokens=row[7],
            total_tokens=row[8],
            cost_usd=row[9],
            created_at=row[10],
            metadata_json=row[11],
        )

    # ==================== Cost Budgets ====================

    def get_budget_for_project(self, project_id: int) -> CostBudget | None:
        """Get budget for a project.

        Args:
            project_id: Project ID.

        Returns:
            CostBudget or None.
        """
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM cost_budgets WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            return self._row_to_budget(row) if row else None

    def create_or_update_budget(self, budget: CostBudget) -> CostBudget:
        """Create or update a budget for a project.

        Args:
            budget: Budget to save.

        Returns:
            Saved budget with ID.
        """
        existing = self.get_budget_for_project(budget.project_id)

        with self.db.connection() as conn:
            if existing:
                conn.execute(
                    """
                    UPDATE cost_budgets SET
                        daily_budget_usd = ?,
                        monthly_budget_usd = ?,
                        total_budget_usd = ?,
                        alert_threshold_percent = ?,
                        is_hard_limit = ?,
                        updated_at = ?
                    WHERE project_id = ?
                    """,
                    (
                        budget.daily_budget_usd,
                        budget.monthly_budget_usd,
                        budget.total_budget_usd,
                        budget.alert_threshold_percent,
                        budget.is_hard_limit,
                        datetime.utcnow(),
                        budget.project_id,
                    ),
                )
                budget.id = existing.id
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO cost_budgets (
                        project_id, daily_budget_usd, monthly_budget_usd,
                        total_budget_usd, alert_threshold_percent, is_hard_limit
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        budget.project_id,
                        budget.daily_budget_usd,
                        budget.monthly_budget_usd,
                        budget.total_budget_usd,
                        budget.alert_threshold_percent,
                        budget.is_hard_limit,
                    ),
                )
                budget.id = cursor.lastrowid

        return budget

    def delete_budget(self, project_id: int) -> bool:
        """Delete budget for a project.

        Args:
            project_id: Project ID.

        Returns:
            True if deleted, False if not found.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                "DELETE FROM cost_budgets WHERE project_id = ?",
                (project_id,),
            )
            return cursor.rowcount > 0

    def _row_to_budget(self, row) -> CostBudget:
        """Convert a database row to a CostBudget.

        Args:
            row: Database row.

        Returns:
            CostBudget instance.
        """
        return CostBudget(
            id=row[0],
            project_id=row[1],
            daily_budget_usd=row[2],
            monthly_budget_usd=row[3],
            total_budget_usd=row[4],
            alert_threshold_percent=row[5],
            is_hard_limit=bool(row[6]),
            created_at=row[7],
            updated_at=row[8],
        )

    # ==================== Cost Alerts ====================

    def create_alert(self, alert: CostAlert) -> CostAlert:
        """Create a new cost alert.

        Args:
            alert: Alert to create.

        Returns:
            Created alert with ID.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO cost_alerts (
                    project_id, alert_type, message, budget_amount_usd,
                    current_amount_usd, threshold_percent
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    alert.project_id,
                    alert.alert_type.value,
                    alert.message,
                    alert.budget_amount_usd,
                    alert.current_amount_usd,
                    alert.threshold_percent,
                ),
            )
            alert.id = cursor.lastrowid
            return alert

    def get_alerts_for_project(
        self,
        project_id: int,
        unacknowledged_only: bool = False,
        limit: int = 50,
    ) -> list[CostAlert]:
        """Get alerts for a project.

        Args:
            project_id: Project ID.
            unacknowledged_only: Only return unacknowledged alerts.
            limit: Maximum number of alerts.

        Returns:
            List of alerts.
        """
        query = "SELECT * FROM cost_alerts WHERE project_id = ?"
        params: list = [project_id]

        if unacknowledged_only:
            query += " AND acknowledged = 0"

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self.db.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_alert(row) for row in rows]

    def acknowledge_alert(self, alert_id: int) -> bool:
        """Acknowledge an alert.

        Args:
            alert_id: Alert ID.

        Returns:
            True if acknowledged, False if not found.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE cost_alerts SET
                    acknowledged = 1,
                    acknowledged_at = ?
                WHERE id = ?
                """,
                (datetime.utcnow(), alert_id),
            )
            return cursor.rowcount > 0

    def acknowledge_all_alerts(self, project_id: int) -> int:
        """Acknowledge all alerts for a project.

        Args:
            project_id: Project ID.

        Returns:
            Number of alerts acknowledged.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE cost_alerts SET
                    acknowledged = 1,
                    acknowledged_at = ?
                WHERE project_id = ? AND acknowledged = 0
                """,
                (datetime.utcnow(), project_id),
            )
            return cursor.rowcount

    def _row_to_alert(self, row) -> CostAlert:
        """Convert a database row to a CostAlert.

        Args:
            row: Database row.

        Returns:
            CostAlert instance.
        """
        return CostAlert(
            id=row[0],
            project_id=row[1],
            alert_type=AlertType(row[2]),
            message=row[3],
            budget_amount_usd=row[4],
            current_amount_usd=row[5],
            threshold_percent=row[6],
            acknowledged=bool(row[7]),
            acknowledged_at=row[8],
            created_at=row[9],
        )

    # ==================== Summary Statistics ====================

    def get_all_projects_cost_summary(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict]:
        """Get cost summary for all projects.

        Args:
            start_date: Optional start date filter.
            end_date: Optional end date filter.

        Returns:
            List of dicts with project_id and cost stats.
        """
        query = """
            SELECT
                project_id,
                SUM(cost_usd) as total_cost,
                SUM(total_tokens) as total_tokens,
                COUNT(*) as record_count
            FROM cost_records WHERE 1=1
        """
        params: list = []

        if start_date:
            query += " AND created_at >= ?"
            params.append(start_date)
        if end_date:
            query += " AND created_at <= ?"
            params.append(end_date)

        query += " GROUP BY project_id"

        with self.db.connection() as conn:
            rows = conn.execute(query, params).fetchall()

        return [
            {
                "project_id": row[0],
                "total_cost": row[1] or 0.0,
                "total_tokens": row[2] or 0,
                "record_count": row[3] or 0,
            }
            for row in rows
        ]
