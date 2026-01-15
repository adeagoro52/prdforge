"""API routes for PRDForge dashboard."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from src.db import Database, Project, ProjectHealth, ProjectRepository, Run, RunRepository, TaskRepository
from src.db.models import RunStatus
from src.skills import SkillRegistry
from src.skills.base import SkillSource

# Template configuration
_API_DIR = Path(__file__).parent
_TEMPLATES_DIR = _API_DIR / "templates"
_templates: Jinja2Templates | None = None


def get_templates() -> Jinja2Templates:
    """Get configured Jinja2 templates with custom filters."""
    global _templates
    if _templates is None:
        _templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

        # Add custom filters
        def fromjson(value: str) -> list | dict:
            """Parse a JSON string into a Python object."""
            try:
                return json.loads(value) if value else []
            except (json.JSONDecodeError, TypeError):
                return []

        _templates.env.filters["fromjson"] = fromjson

    return _templates

# API Router for JSON endpoints
api_router = APIRouter(tags=["api"])

# Pages Router for HTML pages
pages_router = APIRouter(tags=["pages"])


# Health check endpoint
@api_router.get("/health")
def health_check():
    """Health check endpoint for container orchestration."""
    return {"status": "healthy", "version": "0.1.0"}


# Database dependency
def get_db() -> Database:
    """Get database instance."""
    db_path = Path("~/.prdforge/prdforge.db").expanduser()
    db = Database(db_path)
    db.initialize()
    return db


# Pydantic models for request/response
class ProjectCreate(BaseModel):
    """Request model for creating a project."""

    name: str = Field(..., min_length=1, max_length=100)
    path: str = Field(..., min_length=1)
    project_type: str = Field(default="local")


class ProjectResponse(BaseModel):
    """Response model for a project."""

    id: int
    name: str
    path: str
    project_type: str
    tags: list[str] = []
    health: Optional[str] = None
    is_archived: bool = False
    created_at: Optional[datetime] = None
    is_active: bool = True


class ProjectTagsUpdate(BaseModel):
    """Request model for updating project tags."""

    tags: list[str]


class HealthSummaryResponse(BaseModel):
    """Response model for health summary."""

    healthy: int = 0
    warning: int = 0
    failing: int = 0
    inactive: int = 0
    unknown: int = 0


class SkillResponse(BaseModel):
    """Response model for a skill."""

    name: str
    description: str
    category: str
    source: str
    enabled: bool = True


class RunCreate(BaseModel):
    """Request model for creating a run."""

    prd_path: str = Field(..., min_length=1)
    base_branch: str = Field(default="develop")
    executor: str = Field(default="claude-cli")


class RunResponse(BaseModel):
    """Response model for a run."""

    id: int
    run_id: str
    project_id: int
    prd_path: str
    status: str
    base_branch: str
    run_branch: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0


# API Endpoints
@api_router.get("/projects", response_model=list[ProjectResponse])
def list_projects(
    active_only: bool = Query(True),
    include_archived: bool = Query(False),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    db: Database = Depends(get_db),
):
    """List all projects."""
    repo = ProjectRepository(db)
    if tag:
        projects = repo.list_by_tag(tag, include_archived=include_archived)
    else:
        projects = repo.list_all(active_only=active_only, include_archived=include_archived)

    return [
        ProjectResponse(
            id=p.id,
            name=p.name,
            path=p.path,
            project_type=p.project_type,
            tags=p.tags,
            health=repo.get_health(p.id).value,
            is_archived=p.is_archived,
            created_at=p.created_at,
            is_active=p.is_active,
        )
        for p in projects
    ]


@api_router.get("/projects/health-summary", response_model=HealthSummaryResponse)
def get_health_summary(db: Database = Depends(get_db)):
    """Get health status summary across all projects."""
    repo = ProjectRepository(db)
    summary = repo.get_health_summary()
    return HealthSummaryResponse(**summary)


@api_router.get("/projects/tags")
def list_all_tags(db: Database = Depends(get_db)):
    """Get all unique tags across projects."""
    repo = ProjectRepository(db)
    return {"tags": repo.get_all_tags()}


@api_router.get("/projects/archived", response_model=list[ProjectResponse])
def list_archived_projects(db: Database = Depends(get_db)):
    """List all archived projects."""
    repo = ProjectRepository(db)
    projects = repo.list_archived()
    return [
        ProjectResponse(
            id=p.id,
            name=p.name,
            path=p.path,
            project_type=p.project_type,
            tags=p.tags,
            health=repo.get_health(p.id).value,
            is_archived=p.is_archived,
            created_at=p.created_at,
            is_active=p.is_active,
        )
        for p in projects
    ]


@api_router.post("/projects", response_model=ProjectResponse, status_code=201)
def create_project(
    project: ProjectCreate,
    db: Database = Depends(get_db),
):
    """Create a new project."""
    repo = ProjectRepository(db)

    # Check if project with same name exists
    existing = repo.get_by_name(project.name)
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Project with name '{project.name}' already exists",
        )

    new_project = Project(
        id=None,
        name=project.name,
        path=project.path,
        project_type=project.project_type,
    )
    project_id = repo.create(new_project)
    created = repo.get_by_id(project_id)

    return ProjectResponse(
        id=created.id,
        name=created.name,
        path=created.path,
        project_type=created.project_type,
        tags=created.tags,
        health=repo.get_health(created.id).value,
        is_archived=created.is_archived,
        created_at=created.created_at,
        is_active=created.is_active,
    )


@api_router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: int,
    db: Database = Depends(get_db),
):
    """Get a project by ID."""
    repo = ProjectRepository(db)
    project = repo.get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return ProjectResponse(
        id=project.id,
        name=project.name,
        path=project.path,
        project_type=project.project_type,
        tags=project.tags,
        health=repo.get_health(project.id).value,
        is_archived=project.is_archived,
        created_at=project.created_at,
        is_active=project.is_active,
    )


@api_router.put("/projects/{project_id}/tags", response_model=ProjectResponse)
def update_project_tags(
    project_id: int,
    tags_update: ProjectTagsUpdate,
    db: Database = Depends(get_db),
):
    """Update tags for a project."""
    repo = ProjectRepository(db)
    project = repo.get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    repo.set_tags(project_id, tags_update.tags)
    updated = repo.get_by_id(project_id)

    return ProjectResponse(
        id=updated.id,
        name=updated.name,
        path=updated.path,
        project_type=updated.project_type,
        tags=updated.tags,
        health=repo.get_health(updated.id).value,
        is_archived=updated.is_archived,
        created_at=updated.created_at,
        is_active=updated.is_active,
    )


@api_router.post("/projects/{project_id}/archive", status_code=200)
def archive_project(
    project_id: int,
    db: Database = Depends(get_db),
):
    """Archive a project."""
    repo = ProjectRepository(db)
    project = repo.get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.is_archived:
        raise HTTPException(status_code=400, detail="Project is already archived")

    repo.archive(project_id)
    return {"status": "archived"}


@api_router.post("/projects/{project_id}/unarchive", status_code=200)
def unarchive_project(
    project_id: int,
    db: Database = Depends(get_db),
):
    """Unarchive (restore) a project."""
    repo = ProjectRepository(db)
    project = repo.get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.is_archived:
        raise HTTPException(status_code=400, detail="Project is not archived")

    repo.unarchive(project_id)
    return {"status": "unarchived"}


@api_router.delete("/projects/{project_id}", status_code=204)
def delete_project(
    project_id: int,
    db: Database = Depends(get_db),
):
    """Delete a project."""
    repo = ProjectRepository(db)
    project = repo.get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    repo.delete(project_id)


@api_router.get("/projects/{project_id}/runs", response_model=list[RunResponse])
def list_project_runs(
    project_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_db),
):
    """List runs for a project."""
    # Verify project exists
    project_repo = ProjectRepository(db)
    if not project_repo.get_by_id(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    run_repo = RunRepository(db)
    runs = run_repo.list_by_project(project_id, limit=limit, offset=offset)

    return [
        RunResponse(
            id=r.id,
            run_id=r.run_id,
            project_id=r.project_id,
            prd_path=r.prd_path,
            status=r.status.value,
            base_branch=r.base_branch,
            run_branch=r.run_branch,
            started_at=r.started_at,
            completed_at=r.completed_at,
            total_tasks=r.total_tasks,
            completed_tasks=r.completed_tasks,
            failed_tasks=r.failed_tasks,
        )
        for r in runs
    ]


@api_router.post("/projects/{project_id}/runs", response_model=RunResponse, status_code=201)
def create_run(
    project_id: int,
    run_data: RunCreate,
    db: Database = Depends(get_db),
):
    """Start a new run for a project."""
    # Verify project exists
    project_repo = ProjectRepository(db)
    project = project_repo.get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Create run
    run_id = str(uuid4())
    run = Run(
        id=None,
        run_id=run_id,
        project_id=project_id,
        prd_path=run_data.prd_path,
        status=RunStatus.PENDING,
        base_branch=run_data.base_branch,
        executor=run_data.executor,
        started_at=datetime.utcnow(),
    )

    run_repo = RunRepository(db)
    db_id = run_repo.create(run)
    created = run_repo.get_by_id(db_id)

    return RunResponse(
        id=created.id,
        run_id=created.run_id,
        project_id=created.project_id,
        prd_path=created.prd_path,
        status=created.status.value,
        base_branch=created.base_branch,
        run_branch=created.run_branch,
        started_at=created.started_at,
        completed_at=created.completed_at,
        total_tasks=created.total_tasks,
        completed_tasks=created.completed_tasks,
        failed_tasks=created.failed_tasks,
    )


@api_router.get("/runs/{run_id}", response_model=RunResponse)
def get_run(
    run_id: str,
    db: Database = Depends(get_db),
):
    """Get a run by ID."""
    run_repo = RunRepository(db)
    run = run_repo.get_by_run_id(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    return RunResponse(
        id=run.id,
        run_id=run.run_id,
        project_id=run.project_id,
        prd_path=run.prd_path,
        status=run.status.value,
        base_branch=run.base_branch,
        run_branch=run.run_branch,
        started_at=run.started_at,
        completed_at=run.completed_at,
        total_tasks=run.total_tasks,
        completed_tasks=run.completed_tasks,
        failed_tasks=run.failed_tasks,
    )


@api_router.post("/runs/{run_id}/pause", status_code=200)
def pause_run(
    run_id: str,
    db: Database = Depends(get_db),
):
    """Pause a running run."""
    run_repo = RunRepository(db)
    run = run_repo.get_by_run_id(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.status != RunStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Can only pause running runs")

    run_repo.update_status(run_id, RunStatus.PAUSED)
    return {"status": "paused"}


@api_router.post("/runs/{run_id}/resume", status_code=200)
def resume_run(
    run_id: str,
    db: Database = Depends(get_db),
):
    """Resume a paused run."""
    run_repo = RunRepository(db)
    run = run_repo.get_by_run_id(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.status != RunStatus.PAUSED:
        raise HTTPException(status_code=400, detail="Can only resume paused runs")

    run_repo.update_status(run_id, RunStatus.RUNNING)
    return {"status": "running"}


@api_router.post("/runs/{run_id}/cancel", status_code=200)
def cancel_run(
    run_id: str,
    db: Database = Depends(get_db),
):
    """Cancel a run."""
    run_repo = RunRepository(db)
    run = run_repo.get_by_run_id(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.status not in [RunStatus.RUNNING, RunStatus.PAUSED, RunStatus.PENDING]:
        raise HTTPException(status_code=400, detail="Cannot cancel completed or failed runs")

    run_repo.update_status(run_id, RunStatus.CANCELLED, datetime.utcnow())
    return {"status": "cancelled"}


# Skills Endpoints
def get_skill_registry(project_path: Optional[str] = None) -> SkillRegistry:
    """Get skill registry with discovered skills."""
    registry = SkillRegistry()
    registry.discover_builtin()
    registry.discover_user_skills()
    if project_path:
        registry.discover_project_skills(Path(project_path))
    return registry


@api_router.get("/skills", response_model=list[SkillResponse])
def list_skills(project_path: Optional[str] = Query(None)):
    """List all available skills."""
    registry = get_skill_registry(project_path)
    skills = registry.list_all()
    return [
        SkillResponse(
            name=s.name,
            description=s.description,
            category=s.category,
            source=s.source.value,
        )
        for s in skills
    ]


@api_router.get("/skills/{skill_name}", response_model=SkillResponse)
def get_skill(skill_name: str, project_path: Optional[str] = Query(None)):
    """Get a skill by name."""
    registry = get_skill_registry(project_path)
    skill = registry.get(skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

    return SkillResponse(
        name=skill.name,
        description=skill.description,
        category=skill.category,
        source=skill.source.value,
    )


# Executor Plugin Endpoints
from src.executors import PluginManager, ExecutorSelection


class ExecutorPluginResponse(BaseModel):
    """Response model for an executor plugin."""

    model_config = {"populate_by_name": True}

    name: str
    display_name: str
    description: str
    version: str
    source: str
    capabilities: list[str] = []
    config_schema: Optional[dict] = Field(None, alias="schema")
    error: Optional[str] = None


class ExecutorHealthResponse(BaseModel):
    """Response model for executor health check."""

    name: str
    healthy: bool
    status: str
    error: Optional[str] = None
    info: Optional[dict] = None


class ExecutorConfigUpdate(BaseModel):
    """Request model for updating executor config."""

    config: dict


def get_plugin_manager() -> PluginManager:
    """Get a plugin manager instance."""
    manager = PluginManager()
    manager.refresh()
    return manager


@api_router.get("/executors", response_model=list[ExecutorPluginResponse])
def list_executors():
    """List all available executor plugins."""
    manager = get_plugin_manager()
    plugins = manager.get_available_plugins()
    return [
        ExecutorPluginResponse(
            name=p["name"],
            display_name=p["display_name"],
            description=p["description"],
            version=p["version"],
            source=p["source"],
            capabilities=p.get("capabilities", []),
            config_schema=p.get("schema"),
            error=p.get("error"),
        )
        for p in plugins
    ]


@api_router.get("/executors/{executor_name}", response_model=ExecutorPluginResponse)
def get_executor(executor_name: str):
    """Get an executor plugin by name."""
    manager = get_plugin_manager()
    plugin = manager.discovery.get_plugin(executor_name)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Executor '{executor_name}' not found")

    return ExecutorPluginResponse(
        name=plugin.name,
        display_name=plugin.display_name,
        description=plugin.description,
        version=plugin.version,
        source=plugin.source_type,
        capabilities=plugin.capabilities,
        config_schema=plugin.schema.to_json_schema() if plugin.schema else None,
        error=plugin.error,
    )


@api_router.get("/executors/{executor_name}/health", response_model=ExecutorHealthResponse)
def check_executor_health(executor_name: str):
    """Check health status of an executor."""
    manager = get_plugin_manager()
    health = manager.check_health(executor_name)
    return ExecutorHealthResponse(
        name=health["name"],
        healthy=health["healthy"],
        status=health["status"],
        error=health.get("error"),
        info=health.get("info"),
    )


@api_router.get("/executors/health/all", response_model=list[ExecutorHealthResponse])
def check_all_executor_health():
    """Check health status of all executors."""
    manager = get_plugin_manager()
    results = manager.check_all_health()
    return [
        ExecutorHealthResponse(
            name=r["name"],
            healthy=r["healthy"],
            status=r["status"],
            error=r.get("error"),
            info=r.get("info"),
        )
        for r in results
    ]


@api_router.post("/executors/{executor_name}/test")
def test_executor(executor_name: str, config: ExecutorConfigUpdate):
    """Test an executor with the provided configuration."""
    manager = get_plugin_manager()

    try:
        # Try to create an executor instance with the config
        executor = manager.create_executor(executor_name, config=config.config)
        healthy = executor.health_check()

        return {
            "success": True,
            "name": executor_name,
            "healthy": healthy,
            "info": executor.get_info(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        return {
            "success": False,
            "name": executor_name,
            "error": str(e),
        }


# Cost Tracking Endpoints
from src.engine.cost_tracker import CostTracker, get_cost_tracker


class CostRecordCreate(BaseModel):
    """Request model for creating a cost record."""

    executor: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    run_id: Optional[int] = None
    task_execution_id: Optional[int] = None
    metadata: Optional[dict] = None


class CostRecordResponse(BaseModel):
    """Response model for a cost record."""

    id: int
    project_id: int
    run_id: Optional[int]
    task_execution_id: Optional[int]
    executor: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    created_at: Optional[datetime]


class CostBudgetCreate(BaseModel):
    """Request model for creating/updating a budget."""

    daily_budget_usd: Optional[float] = None
    monthly_budget_usd: Optional[float] = None
    total_budget_usd: Optional[float] = None
    alert_threshold_percent: float = 80.0
    is_hard_limit: bool = False


class CostBudgetResponse(BaseModel):
    """Response model for a cost budget."""

    id: int
    project_id: int
    daily_budget_usd: Optional[float]
    monthly_budget_usd: Optional[float]
    total_budget_usd: Optional[float]
    alert_threshold_percent: float
    is_hard_limit: bool


class BudgetStatusResponse(BaseModel):
    """Response model for budget status."""

    project_id: int
    daily_spent: float
    monthly_spent: float
    total_spent: float
    daily_utilization: Optional[float]
    monthly_utilization: Optional[float]
    total_utilization: Optional[float]
    daily_exceeded: bool
    monthly_exceeded: bool
    total_exceeded: bool
    threshold_reached: bool
    is_blocked: bool
    budget: Optional[CostBudgetResponse]


class CostAlertResponse(BaseModel):
    """Response model for a cost alert."""

    id: int
    project_id: int
    alert_type: str
    message: str
    budget_amount_usd: Optional[float]
    current_amount_usd: Optional[float]
    threshold_percent: Optional[float]
    acknowledged: bool
    acknowledged_at: Optional[datetime]
    created_at: Optional[datetime]


class CostSummaryResponse(BaseModel):
    """Response model for cost summary."""

    project_id: int
    total_cost_usd: float
    breakdown_by_executor: dict
    daily_costs: list[dict]
    period: dict


class GlobalCostSummaryResponse(BaseModel):
    """Response model for global cost summary."""

    total_cost_usd: float
    total_tokens: int
    total_records: int
    project_count: int
    by_project: list[dict]


def get_cost_tracker_instance(db: Database = Depends(get_db)) -> CostTracker:
    """Get cost tracker instance."""
    return get_cost_tracker(db)


@api_router.post("/projects/{project_id}/costs", response_model=CostRecordResponse, status_code=201)
def create_cost_record(
    project_id: int,
    record: CostRecordCreate,
    tracker: CostTracker = Depends(get_cost_tracker_instance),
):
    """Record a cost for a project."""
    cost_record = tracker.record_cost(
        project_id=project_id,
        executor=record.executor,
        model=record.model,
        prompt_tokens=record.prompt_tokens,
        completion_tokens=record.completion_tokens,
        run_id=record.run_id,
        task_execution_id=record.task_execution_id,
        metadata=record.metadata,
    )

    return CostRecordResponse(
        id=cost_record.id,
        project_id=cost_record.project_id,
        run_id=cost_record.run_id,
        task_execution_id=cost_record.task_execution_id,
        executor=cost_record.executor,
        model=cost_record.model,
        prompt_tokens=cost_record.prompt_tokens,
        completion_tokens=cost_record.completion_tokens,
        total_tokens=cost_record.total_tokens,
        cost_usd=cost_record.cost_usd,
        created_at=cost_record.created_at,
    )


@api_router.get("/projects/{project_id}/costs", response_model=list[CostRecordResponse])
def get_project_costs(
    project_id: int,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    limit: int = Query(100, le=500),
    tracker: CostTracker = Depends(get_cost_tracker_instance),
):
    """Get cost records for a project."""
    records = tracker.repository.get_cost_records_for_project(
        project_id=project_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )

    return [
        CostRecordResponse(
            id=r.id,
            project_id=r.project_id,
            run_id=r.run_id,
            task_execution_id=r.task_execution_id,
            executor=r.executor,
            model=r.model,
            prompt_tokens=r.prompt_tokens,
            completion_tokens=r.completion_tokens,
            total_tokens=r.total_tokens,
            cost_usd=r.cost_usd,
            created_at=r.created_at,
        )
        for r in records
    ]


@api_router.get("/projects/{project_id}/costs/summary", response_model=CostSummaryResponse)
def get_project_cost_summary(
    project_id: int,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    tracker: CostTracker = Depends(get_cost_tracker_instance),
):
    """Get cost summary for a project."""
    summary = tracker.get_project_cost_summary(
        project_id=project_id,
        start_date=start_date,
        end_date=end_date,
    )

    return CostSummaryResponse(
        project_id=summary["project_id"],
        total_cost_usd=summary["total_cost_usd"],
        breakdown_by_executor=summary["breakdown_by_executor"],
        daily_costs=summary["daily_costs"],
        period=summary["period"],
    )


@api_router.get("/runs/{run_id}/costs")
def get_run_cost_summary(
    run_id: str,
    db: Database = Depends(get_db),
    tracker: CostTracker = Depends(get_cost_tracker_instance),
):
    """Get cost summary for a run."""
    run_repo = RunRepository(db)
    run = run_repo.get_by_run_id(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    return tracker.get_run_cost_summary(run.id)


@api_router.get("/projects/{project_id}/budget", response_model=Optional[CostBudgetResponse])
def get_project_budget(
    project_id: int,
    tracker: CostTracker = Depends(get_cost_tracker_instance),
):
    """Get budget for a project."""
    budget = tracker.repository.get_budget_for_project(project_id)
    if not budget:
        return None

    return CostBudgetResponse(
        id=budget.id,
        project_id=budget.project_id,
        daily_budget_usd=budget.daily_budget_usd,
        monthly_budget_usd=budget.monthly_budget_usd,
        total_budget_usd=budget.total_budget_usd,
        alert_threshold_percent=budget.alert_threshold_percent,
        is_hard_limit=budget.is_hard_limit,
    )


@api_router.put("/projects/{project_id}/budget", response_model=CostBudgetResponse)
def set_project_budget(
    project_id: int,
    budget: CostBudgetCreate,
    tracker: CostTracker = Depends(get_cost_tracker_instance),
):
    """Set or update budget for a project."""
    saved = tracker.set_budget(
        project_id=project_id,
        daily_budget_usd=budget.daily_budget_usd,
        monthly_budget_usd=budget.monthly_budget_usd,
        total_budget_usd=budget.total_budget_usd,
        alert_threshold_percent=budget.alert_threshold_percent,
        is_hard_limit=budget.is_hard_limit,
    )

    return CostBudgetResponse(
        id=saved.id,
        project_id=saved.project_id,
        daily_budget_usd=saved.daily_budget_usd,
        monthly_budget_usd=saved.monthly_budget_usd,
        total_budget_usd=saved.total_budget_usd,
        alert_threshold_percent=saved.alert_threshold_percent,
        is_hard_limit=saved.is_hard_limit,
    )


@api_router.delete("/projects/{project_id}/budget", status_code=204)
def delete_project_budget(
    project_id: int,
    tracker: CostTracker = Depends(get_cost_tracker_instance),
):
    """Remove budget for a project."""
    if not tracker.remove_budget(project_id):
        raise HTTPException(status_code=404, detail="Budget not found")


@api_router.get("/projects/{project_id}/budget/status", response_model=BudgetStatusResponse)
def get_budget_status(
    project_id: int,
    tracker: CostTracker = Depends(get_cost_tracker_instance),
):
    """Get current budget status for a project."""
    status = tracker.get_budget_status(project_id)

    budget_response = None
    if status.budget:
        budget_response = CostBudgetResponse(
            id=status.budget.id,
            project_id=status.budget.project_id,
            daily_budget_usd=status.budget.daily_budget_usd,
            monthly_budget_usd=status.budget.monthly_budget_usd,
            total_budget_usd=status.budget.total_budget_usd,
            alert_threshold_percent=status.budget.alert_threshold_percent,
            is_hard_limit=status.budget.is_hard_limit,
        )

    return BudgetStatusResponse(
        project_id=status.project_id,
        daily_spent=status.daily_spent,
        monthly_spent=status.monthly_spent,
        total_spent=status.total_spent,
        daily_utilization=status.daily_utilization,
        monthly_utilization=status.monthly_utilization,
        total_utilization=status.total_utilization,
        daily_exceeded=status.daily_exceeded,
        monthly_exceeded=status.monthly_exceeded,
        total_exceeded=status.total_exceeded,
        threshold_reached=status.threshold_reached,
        is_blocked=status.is_blocked,
        budget=budget_response,
    )


@api_router.get("/projects/{project_id}/alerts", response_model=list[CostAlertResponse])
def get_project_alerts(
    project_id: int,
    unacknowledged_only: bool = Query(False),
    tracker: CostTracker = Depends(get_cost_tracker_instance),
):
    """Get cost alerts for a project."""
    alerts = tracker.get_alerts(project_id, unacknowledged_only)

    return [
        CostAlertResponse(
            id=a.id,
            project_id=a.project_id,
            alert_type=a.alert_type.value,
            message=a.message,
            budget_amount_usd=a.budget_amount_usd,
            current_amount_usd=a.current_amount_usd,
            threshold_percent=a.threshold_percent,
            acknowledged=a.acknowledged,
            acknowledged_at=a.acknowledged_at,
            created_at=a.created_at,
        )
        for a in alerts
    ]


@api_router.post("/alerts/{alert_id}/acknowledge", status_code=200)
def acknowledge_alert(
    alert_id: int,
    tracker: CostTracker = Depends(get_cost_tracker_instance),
):
    """Acknowledge a cost alert."""
    if not tracker.acknowledge_alert(alert_id):
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"status": "acknowledged"}


@api_router.post("/projects/{project_id}/alerts/acknowledge-all", status_code=200)
def acknowledge_all_project_alerts(
    project_id: int,
    tracker: CostTracker = Depends(get_cost_tracker_instance),
):
    """Acknowledge all alerts for a project."""
    count = tracker.acknowledge_all_alerts(project_id)
    return {"acknowledged": count}


@api_router.get("/costs/summary", response_model=GlobalCostSummaryResponse)
def get_global_cost_summary(
    tracker: CostTracker = Depends(get_cost_tracker_instance),
):
    """Get global cost summary across all projects."""
    summary = tracker.get_global_cost_summary()

    return GlobalCostSummaryResponse(
        total_cost_usd=summary["total_cost_usd"],
        total_tokens=summary["total_tokens"],
        total_records=summary["total_records"],
        project_count=summary["project_count"],
        by_project=summary["by_project"],
    )


@api_router.get("/costs/estimate")
def estimate_cost(
    executor: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: Optional[int] = None,
    tracker: CostTracker = Depends(get_cost_tracker_instance),
):
    """Estimate cost for an execution before it happens."""
    estimate = tracker.estimate_cost(
        executor=executor,
        model=model,
        prompt_tokens=prompt_tokens,
        estimated_completion_tokens=completion_tokens,
    )

    return {
        "executor": estimate.executor,
        "model": estimate.model,
        "prompt_tokens": estimate.prompt_tokens,
        "completion_tokens": estimate.completion_tokens,
        "estimated_cost_usd": estimate.estimated_cost_usd,
    }


# HTML Pages
@pages_router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Database = Depends(get_db)):
    """Dashboard home page."""
    templates = get_templates()

    project_repo = ProjectRepository(db)
    projects = project_repo.list_all()

    run_repo = RunRepository(db)
    active_runs = run_repo.list_active()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "projects": projects,
            "active_runs": active_runs,
        },
    )


@pages_router.get("/projects", response_class=HTMLResponse)
def projects_page(request: Request, db: Database = Depends(get_db)):
    """Projects list page."""
    templates = get_templates()

    project_repo = ProjectRepository(db)
    projects = project_repo.list_all()

    return templates.TemplateResponse(
        "projects.html",
        {
            "request": request,
            "projects": projects,
        },
    )


@pages_router.get("/projects/{project_id}", response_class=HTMLResponse)
def project_detail_page(
    request: Request,
    project_id: int,
    db: Database = Depends(get_db),
):
    """Project detail page."""
    templates = get_templates()

    project_repo = ProjectRepository(db)
    project = project_repo.get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    run_repo = RunRepository(db)
    runs = run_repo.list_by_project(project_id, limit=20)

    return templates.TemplateResponse(
        "project_detail.html",
        {
            "request": request,
            "project": project,
            "runs": runs,
        },
    )


@pages_router.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail_page(
    request: Request,
    run_id: str,
    db: Database = Depends(get_db),
):
    """Run detail page."""
    templates = get_templates()

    run_repo = RunRepository(db)
    run = run_repo.get_by_run_id(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    task_repo = TaskRepository(db)
    tasks = task_repo.list_by_run(run.id)

    project_repo = ProjectRepository(db)
    project = project_repo.get_by_id(run.project_id)

    return templates.TemplateResponse(
        "run_detail.html",
        {
            "request": request,
            "run": run,
            "tasks": tasks,
            "project": project,
        },
    )


@pages_router.get("/skills", response_class=HTMLResponse)
def skills_page(request: Request):
    """Skills management page."""
    templates = get_templates()

    registry = get_skill_registry()
    skills = registry.list_all()

    # Group skills by source
    skills_by_source = {
        "package": [],
        "user": [],
        "project": [],
    }
    for skill in skills:
        skills_by_source[skill.source.value].append(skill)

    return templates.TemplateResponse(
        "skills.html",
        {
            "request": request,
            "skills": skills,
            "skills_by_source": skills_by_source,
        },
    )


@pages_router.get("/executors", response_class=HTMLResponse)
def executors_page(request: Request):
    """Executor plugins management page."""
    templates = get_templates()

    manager = get_plugin_manager()
    plugins = manager.get_available_plugins()

    # Add health status to each executor
    executors_with_health = []
    for p in plugins:
        health = manager.check_health(p["name"])
        executors_with_health.append({
            **p,
            "healthy": health.get("healthy", False),
            "status": health.get("status", "unknown"),
        })

    return templates.TemplateResponse(
        "executors.html",
        {
            "request": request,
            "executors": executors_with_health,
        },
    )


@pages_router.get("/costs", response_class=HTMLResponse)
def costs_page(request: Request):
    """Cost tracking dashboard page."""
    templates = get_templates()

    return templates.TemplateResponse(
        "costs.html",
        {
            "request": request,
        },
    )


@pages_router.get("/quality-gates", response_class=HTMLResponse)
def quality_gates_page(request: Request):
    """Quality gates configuration page."""
    templates = get_templates()

    return templates.TemplateResponse(
        "quality_gates.html",
        {
            "request": request,
        },
    )


# Git Branch API Endpoints
from src.engine.git_manager import GitManager


@api_router.get("/projects/{project_id}/branches")
def list_project_branches(
    project_id: int,
    include_remote: bool = Query(False),
    db: Database = Depends(get_db),
):
    """List branches for a project's repository."""
    project_repo = ProjectRepository(db)
    project = project_repo.get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        git_manager = GitManager(Path(project.path))
        branches = git_manager.list_branches(include_remote=include_remote)
        return {
            "branches": branches,
            "current_branch": git_manager.get_current_branch(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list branches: {e}")


@api_router.get("/projects/{project_id}/branches/graph")
def get_branch_graph(
    project_id: int,
    count: int = Query(50, le=200),
    db: Database = Depends(get_db),
):
    """Get branch graph data for visualization."""
    project_repo = ProjectRepository(db)
    project = project_repo.get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        git_manager = GitManager(Path(project.path))
        return git_manager.get_branch_graph(count=count)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get branch graph: {e}")


@api_router.get("/projects/{project_id}/branches/{branch_name}/commits")
def get_branch_commits(
    project_id: int,
    branch_name: str,
    count: int = Query(20, le=100),
    base_branch: Optional[str] = Query(None),
    db: Database = Depends(get_db),
):
    """Get commits for a specific branch."""
    project_repo = ProjectRepository(db)
    project = project_repo.get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        git_manager = GitManager(Path(project.path))
        commits = git_manager.get_branch_commits(
            branch=branch_name,
            count=count,
            since_branch=base_branch,
        )
        return {"branch": branch_name, "commits": commits}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get commits: {e}")


@api_router.get("/projects/{project_id}/branches/compare")
def compare_branches(
    project_id: int,
    base: str = Query(...),
    head: str = Query(...),
    db: Database = Depends(get_db),
):
    """Compare two branches."""
    project_repo = ProjectRepository(db)
    project = project_repo.get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        git_manager = GitManager(Path(project.path))
        return git_manager.compare_branches(base, head)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compare branches: {e}")


@pages_router.get("/projects/{project_id}/branches", response_class=HTMLResponse)
def branches_page(request: Request, project_id: int, db: Database = Depends(get_db)):
    """Git branch visualization page."""
    templates = get_templates()

    project_repo = ProjectRepository(db)
    project = project_repo.get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return templates.TemplateResponse(
        "branches.html",
        {
            "request": request,
            "project": project,
        },
    )


# Quality Gates API Endpoints
from src.engine.quality_gates import (
    AcceptanceCriteria,
    GateCheckResult,
    GateResult,
    GateType,
    QualityGateChecker,
    QualityGateConfig,
    QualityGateManager,
    BUILTIN_GATES,
)


class GateConfigCreate(BaseModel):
    """Request model for creating a quality gate configuration."""

    name: str
    gate_type: str  # test, lint, typecheck, custom
    command: Optional[str] = None
    args: list[str] = []
    enabled: bool = True
    blocking: bool = True
    retry_on_fail: bool = False
    max_retries: int = 1
    timeout: int = 300


class QualityGateConfigUpdate(BaseModel):
    """Request model for updating quality gate settings."""

    gates: list[GateConfigCreate] = []
    run_on_task_complete: bool = True
    run_on_commit: bool = False
    fail_task_on_failure: bool = True
    auto_detect: bool = True


class GateCheckResultResponse(BaseModel):
    """Response model for a gate check result."""

    gate_name: str
    gate_type: str
    result: str
    output: str
    error: Optional[str]
    duration_seconds: float
    timestamp: Optional[datetime]
    exit_code: Optional[int]


class GateSummaryResponse(BaseModel):
    """Response model for gate run summary."""

    total: int
    passed: int
    failed: int
    skipped: int
    errors: int
    total_duration_seconds: float
    all_passed: bool
    results: list[dict]


@api_router.get("/quality-gates/builtin")
def list_builtin_gates():
    """List all available built-in quality gates."""
    return {
        "gates": [
            {
                "name": name,
                **config,
            }
            for name, config in BUILTIN_GATES.items()
        ]
    }


@api_router.get("/projects/{project_id}/quality-gates/detect")
def detect_project_gates(
    project_id: int,
    db: Database = Depends(get_db),
):
    """Auto-detect quality gates based on project structure."""
    project_repo = ProjectRepository(db)
    project = project_repo.get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        checker = QualityGateChecker(Path(project.path))
        detected = checker.detect_project_gates()
        return {
            "detected_gates": [gate.to_dict() for gate in detected],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to detect gates: {e}")


@api_router.post("/projects/{project_id}/quality-gates/run", response_model=GateSummaryResponse)
def run_quality_gates(
    project_id: int,
    gates: Optional[list[GateConfigCreate]] = None,
    stop_on_failure: bool = Query(True),
    db: Database = Depends(get_db),
):
    """Run quality gates for a project."""
    project_repo = ProjectRepository(db)
    project = project_repo.get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        # Build gate config
        config = QualityGateConfig(auto_detect=gates is None)
        if gates:
            for g in gates:
                config.gates.append(AcceptanceCriteria(
                    name=g.name,
                    gate_type=GateType(g.gate_type),
                    command=g.command,
                    args=g.args,
                    enabled=g.enabled,
                    blocking=g.blocking,
                    retry_on_fail=g.retry_on_fail,
                    max_retries=g.max_retries,
                    timeout=g.timeout,
                ))

        manager = QualityGateManager(config, Path(project.path))
        passed, results = manager.run_gates(stop_on_failure=stop_on_failure)

        summary = manager.get_summary(results)
        return GateSummaryResponse(**summary)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to run gates: {e}")


@api_router.post("/projects/{project_id}/quality-gates/check/{gate_name}")
def run_single_gate(
    project_id: int,
    gate_name: str,
    db: Database = Depends(get_db),
):
    """Run a specific quality gate by name."""
    project_repo = ProjectRepository(db)
    project = project_repo.get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check if it's a builtin gate
    if gate_name not in BUILTIN_GATES:
        raise HTTPException(status_code=404, detail=f"Built-in gate '{gate_name}' not found")

    try:
        gate = AcceptanceCriteria.from_dict(BUILTIN_GATES[gate_name])
        checker = QualityGateChecker(Path(project.path))
        result = checker.check(gate)

        return {
            "gate_name": result.gate.name,
            "gate_type": result.gate.gate_type.value,
            "result": result.result.value,
            "output": result.output,
            "error": result.error,
            "duration_seconds": result.duration_seconds,
            "exit_code": result.exit_code,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to run gate: {e}")


@api_router.post("/projects/{project_id}/quality-gates/custom")
def run_custom_gate(
    project_id: int,
    gate: GateConfigCreate,
    db: Database = Depends(get_db),
):
    """Run a custom quality gate with specified command."""
    project_repo = ProjectRepository(db)
    project = project_repo.get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not gate.command:
        raise HTTPException(status_code=400, detail="Custom gates require a command")

    try:
        criteria = AcceptanceCriteria(
            name=gate.name,
            gate_type=GateType(gate.gate_type),
            command=gate.command,
            args=gate.args,
            enabled=gate.enabled,
            blocking=gate.blocking,
            timeout=gate.timeout,
        )

        checker = QualityGateChecker(Path(project.path))
        result = checker.check(criteria)

        return {
            "gate_name": result.gate.name,
            "gate_type": result.gate.gate_type.value,
            "result": result.result.value,
            "output": result.output,
            "error": result.error,
            "duration_seconds": result.duration_seconds,
            "exit_code": result.exit_code,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to run gate: {e}")


# Authentication API Endpoints
from src.engine.auth_service import AuthService, CurrentUser, get_auth_service
from src.db.models import UserRole
from src.db.user_repository import AuditLogRepository


class LoginRequest(BaseModel):
    """Request model for login."""

    username: str
    password: str


class LoginResponse(BaseModel):
    """Response model for login."""

    success: bool
    token: Optional[str] = None
    user: Optional[dict] = None
    error: Optional[str] = None


class RegisterRequest(BaseModel):
    """Request model for user registration."""

    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(...)
    password: str = Field(..., min_length=8)
    display_name: Optional[str] = None


class UserResponse(BaseModel):
    """Response model for a user."""

    id: int
    username: str
    email: str
    role: str
    display_name: Optional[str]
    is_active: bool
    created_at: Optional[datetime]
    last_login_at: Optional[datetime]


class UserUpdateRequest(BaseModel):
    """Request model for updating a user."""

    email: Optional[str] = None
    display_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class PasswordChangeRequest(BaseModel):
    """Request model for changing password."""

    current_password: str
    new_password: str = Field(..., min_length=8)


class SettingsUpdateRequest(BaseModel):
    """Request model for updating settings."""

    settings: dict


class AuditLogResponse(BaseModel):
    """Response model for an audit log entry."""

    id: int
    user_id: Optional[int]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    details: dict
    ip_address: Optional[str]
    created_at: Optional[datetime]


def get_auth_service_instance(db: Database = Depends(get_db)) -> AuthService:
    """Get auth service instance."""
    return get_auth_service(db)


def get_client_info(request: Request) -> tuple[str | None, str | None]:
    """Extract client IP and user agent from request."""
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return ip, user_agent


@api_router.post("/auth/login", response_model=LoginResponse)
def login(
    request: Request,
    login_data: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service_instance),
):
    """Authenticate a user and get a session token."""
    ip, user_agent = get_client_info(request)

    result = auth_service.login(
        username=login_data.username,
        password=login_data.password,
        ip_address=ip,
        user_agent=user_agent,
    )

    if not result.success:
        return LoginResponse(success=False, error=result.error)

    return LoginResponse(
        success=True,
        token=result.session.token,
        user={
            "id": result.user.id,
            "username": result.user.username,
            "email": result.user.email,
            "role": result.user.role.value,
            "display_name": result.user.display_name,
        },
    )


@api_router.post("/auth/logout", status_code=200)
def logout(
    request: Request,
    token: str = Query(...),
    auth_service: AuthService = Depends(get_auth_service_instance),
):
    """Log out and invalidate the session."""
    ip, user_agent = get_client_info(request)

    if auth_service.logout(token, ip, user_agent):
        return {"status": "logged_out"}
    raise HTTPException(status_code=400, detail="Invalid session")


@api_router.get("/auth/me", response_model=UserResponse)
def get_current_user(
    token: str = Query(...),
    auth_service: AuthService = Depends(get_auth_service_instance),
):
    """Get the current authenticated user."""
    current = auth_service.validate_session(token)
    if not current:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    return UserResponse(
        id=current.user.id,
        username=current.user.username,
        email=current.user.email,
        role=current.user.role.value,
        display_name=current.user.display_name,
        is_active=current.user.is_active,
        created_at=current.user.created_at,
        last_login_at=current.user.last_login_at,
    )


@api_router.post("/auth/extend", status_code=200)
def extend_session(
    token: str = Query(...),
    hours: int = Query(24, ge=1, le=168),
    auth_service: AuthService = Depends(get_auth_service_instance),
):
    """Extend the current session."""
    if auth_service.extend_session(token, hours):
        return {"status": "extended", "hours": hours}
    raise HTTPException(status_code=400, detail="Invalid session")


@api_router.post("/users", response_model=UserResponse, status_code=201)
def create_user(
    request: Request,
    user_data: RegisterRequest,
    token: Optional[str] = Query(None),
    auth_service: AuthService = Depends(get_auth_service_instance),
):
    """Create a new user account."""
    ip, user_agent = get_client_info(request)

    # Check if this is admin creating user or self-registration
    admin_id = None
    if token:
        current = auth_service.validate_session(token)
        if current and current.is_admin:
            admin_id = current.user.id

    user = auth_service.create_user(
        username=user_data.username,
        email=user_data.email,
        password=user_data.password,
        display_name=user_data.display_name,
        created_by_user_id=admin_id,
        ip_address=ip,
        user_agent=user_agent,
    )

    if not user:
        raise HTTPException(status_code=400, detail="Username or email already exists")

    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role.value,
        display_name=user.display_name,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


@api_router.get("/users", response_model=list[UserResponse])
def list_users(
    token: str = Query(...),
    active_only: bool = Query(True),
    auth_service: AuthService = Depends(get_auth_service_instance),
):
    """List all users (admin only)."""
    current = auth_service.validate_session(token)
    if not current:
        raise HTTPException(status_code=401, detail="Invalid session")
    if not current.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    users = auth_service.user_repo.list_all(active_only)
    return [
        UserResponse(
            id=u.id,
            username=u.username,
            email=u.email,
            role=u.role.value,
            display_name=u.display_name,
            is_active=u.is_active,
            created_at=u.created_at,
            last_login_at=u.last_login_at,
        )
        for u in users
    ]


@api_router.get("/users/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    token: str = Query(...),
    auth_service: AuthService = Depends(get_auth_service_instance),
):
    """Get a user by ID."""
    current = auth_service.validate_session(token)
    if not current:
        raise HTTPException(status_code=401, detail="Invalid session")

    # Users can view themselves, admins can view anyone
    if current.user.id != user_id and not current.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")

    user = auth_service.user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role.value,
        display_name=user.display_name,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


@api_router.put("/users/{user_id}", response_model=UserResponse)
def update_user(
    request: Request,
    user_id: int,
    user_data: UserUpdateRequest,
    token: str = Query(...),
    auth_service: AuthService = Depends(get_auth_service_instance),
):
    """Update a user."""
    ip, user_agent = get_client_info(request)
    current = auth_service.validate_session(token)
    if not current:
        raise HTTPException(status_code=401, detail="Invalid session")

    # Users can update themselves (limited), admins can update anyone
    if current.user.id != user_id and not current.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")

    user = auth_service.user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Apply updates
    if user_data.email is not None:
        user.email = user_data.email
    if user_data.display_name is not None:
        user.display_name = user_data.display_name

    # Only admins can change role and active status
    if current.is_admin:
        if user_data.role is not None:
            user.role = UserRole(user_data.role)
        if user_data.is_active is not None:
            user.is_active = user_data.is_active

    auth_service.update_user(user, current.user.id, ip, user_agent)

    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role.value,
        display_name=user.display_name,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


@api_router.post("/users/{user_id}/password", status_code=200)
def change_password(
    request: Request,
    user_id: int,
    password_data: PasswordChangeRequest,
    token: str = Query(...),
    auth_service: AuthService = Depends(get_auth_service_instance),
):
    """Change user password."""
    ip, user_agent = get_client_info(request)
    current = auth_service.validate_session(token)
    if not current:
        raise HTTPException(status_code=401, detail="Invalid session")

    # Users can only change their own password this way
    if current.user.id != user_id:
        raise HTTPException(status_code=403, detail="Can only change your own password")

    if auth_service.change_password(
        user_id,
        password_data.current_password,
        password_data.new_password,
        ip,
        user_agent,
    ):
        return {"status": "password_changed"}

    raise HTTPException(status_code=400, detail="Invalid current password")


@api_router.post("/users/{user_id}/reset-password", status_code=200)
def reset_password(
    request: Request,
    user_id: int,
    new_password: str = Query(..., min_length=8),
    token: str = Query(...),
    auth_service: AuthService = Depends(get_auth_service_instance),
):
    """Admin reset of user password."""
    ip, user_agent = get_client_info(request)
    current = auth_service.validate_session(token)
    if not current or not current.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    if auth_service.reset_password(user_id, new_password, current.user.id, ip, user_agent):
        return {"status": "password_reset"}

    raise HTTPException(status_code=404, detail="User not found")


@api_router.get("/users/{user_id}/settings")
def get_user_settings(
    user_id: int,
    token: str = Query(...),
    auth_service: AuthService = Depends(get_auth_service_instance),
):
    """Get user settings."""
    current = auth_service.validate_session(token)
    if not current:
        raise HTTPException(status_code=401, detail="Invalid session")

    if current.user.id != user_id and not current.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")

    return {"settings": auth_service.get_user_settings(user_id)}


@api_router.put("/users/{user_id}/settings")
def update_user_settings(
    request: Request,
    user_id: int,
    settings_data: SettingsUpdateRequest,
    token: str = Query(...),
    auth_service: AuthService = Depends(get_auth_service_instance),
):
    """Update user settings."""
    ip, user_agent = get_client_info(request)
    current = auth_service.validate_session(token)
    if not current:
        raise HTTPException(status_code=401, detail="Invalid session")

    if current.user.id != user_id and not current.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")

    if auth_service.update_settings(user_id, settings_data.settings, ip, user_agent):
        return {"status": "updated"}

    raise HTTPException(status_code=404, detail="User not found")


@api_router.delete("/users/{user_id}", status_code=200)
def deactivate_user(
    request: Request,
    user_id: int,
    token: str = Query(...),
    auth_service: AuthService = Depends(get_auth_service_instance),
):
    """Deactivate a user (admin only)."""
    ip, user_agent = get_client_info(request)
    current = auth_service.validate_session(token)
    if not current or not current.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    if auth_service.deactivate_user(user_id, current.user.id, ip, user_agent):
        return {"status": "deactivated"}

    raise HTTPException(status_code=404, detail="User not found")


@api_router.get("/audit-logs", response_model=list[AuditLogResponse])
def list_audit_logs(
    token: str = Query(...),
    limit: int = Query(100, le=500),
    user_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    auth_service: AuthService = Depends(get_auth_service_instance),
):
    """List audit logs (admin only)."""
    current = auth_service.validate_session(token)
    if not current or not current.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    audit_repo = auth_service.audit_repo

    if user_id:
        logs = audit_repo.list_for_user(user_id, limit)
    elif action:
        from src.db.models import AuditAction as AuditActionEnum
        try:
            logs = audit_repo.list_by_action(AuditActionEnum(action), limit)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid action: {action}")
    else:
        logs = audit_repo.list_recent(limit)

    return [
        AuditLogResponse(
            id=log.id,
            user_id=log.user_id,
            action=log.action.value,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            details=log.details,
            ip_address=log.ip_address,
            created_at=log.created_at,
        )
        for log in logs
    ]


# Authentication Pages
@pages_router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    """Login page."""
    templates = get_templates()
    return templates.TemplateResponse(
        "login.html",
        {"request": request},
    )


@pages_router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    """User registration page."""
    templates = get_templates()
    return templates.TemplateResponse(
        "register.html",
        {"request": request},
    )


@pages_router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    """User settings page."""
    templates = get_templates()
    return templates.TemplateResponse(
        "settings.html",
        {"request": request},
    )


# Notification API Endpoints
from src.engine.notification_service import (
    NotificationService,
    NotificationEvent,
    get_notification_service,
)
from src.db.models import (
    NotificationEventType,
    NotificationChannel,
    NotificationPriority,
)


class NotificationConfigCreate(BaseModel):
    """Request model for creating/updating notification config."""

    events: list[str] = []
    channels: list[str] = ["in_app"]
    webhook_url: Optional[str] = None
    is_enabled: bool = True
    generate_secret: bool = False


class NotificationConfigResponse(BaseModel):
    """Response model for notification config."""

    id: int
    project_id: int
    events: list[str]
    channels: list[str]
    webhook_url: Optional[str]
    has_secret: bool
    is_enabled: bool


class NotificationResponse(BaseModel):
    """Response model for a notification."""

    id: int
    user_id: int
    project_id: Optional[int]
    event_type: str
    channel: str
    priority: str
    title: str
    message: str
    data: dict
    is_read: bool
    read_at: Optional[datetime]
    created_at: Optional[datetime]


class WebhookDeliveryResponse(BaseModel):
    """Response model for a webhook delivery."""

    id: int
    project_id: int
    notification_id: Optional[int]
    event_type: str
    url: str
    response_status: Optional[int]
    success: bool
    attempt: int
    created_at: Optional[datetime]


class WebhookStatsResponse(BaseModel):
    """Response model for webhook statistics."""

    total: int
    successful: int
    failed: int
    success_rate: float


def get_notification_service_instance(db: Database = Depends(get_db)) -> NotificationService:
    """Get notification service instance."""
    return get_notification_service(db)


@api_router.get("/projects/{project_id}/notifications/config", response_model=Optional[NotificationConfigResponse])
def get_notification_config(
    project_id: int,
    token: str = Query(...),
    auth_service: AuthService = Depends(get_auth_service_instance),
    notification_service: NotificationService = Depends(get_notification_service_instance),
):
    """Get notification configuration for a project."""
    current = auth_service.validate_session(token)
    if not current:
        raise HTTPException(status_code=401, detail="Invalid session")

    config = notification_service.get_config(project_id)
    if not config:
        return None

    return NotificationConfigResponse(
        id=config.id,
        project_id=config.project_id,
        events=config.events,
        channels=config.channels,
        webhook_url=config.webhook_url,
        has_secret=config.webhook_secret is not None,
        is_enabled=config.is_enabled,
    )


@api_router.put("/projects/{project_id}/notifications/config", response_model=NotificationConfigResponse)
def set_notification_config(
    project_id: int,
    config_data: NotificationConfigCreate,
    token: str = Query(...),
    auth_service: AuthService = Depends(get_auth_service_instance),
    notification_service: NotificationService = Depends(get_notification_service_instance),
):
    """Set or update notification configuration for a project."""
    current = auth_service.validate_session(token)
    if not current or not current.can_write:
        raise HTTPException(status_code=403, detail="Write access required")

    config = notification_service.set_config(
        project_id=project_id,
        events=config_data.events,
        channels=config_data.channels,
        webhook_url=config_data.webhook_url,
        is_enabled=config_data.is_enabled,
        generate_secret=config_data.generate_secret,
    )

    return NotificationConfigResponse(
        id=config.id,
        project_id=config.project_id,
        events=config.events,
        channels=config.channels,
        webhook_url=config.webhook_url,
        has_secret=config.webhook_secret is not None,
        is_enabled=config.is_enabled,
    )


@api_router.delete("/projects/{project_id}/notifications/config", status_code=204)
def delete_notification_config(
    project_id: int,
    token: str = Query(...),
    auth_service: AuthService = Depends(get_auth_service_instance),
    notification_service: NotificationService = Depends(get_notification_service_instance),
):
    """Delete notification configuration for a project."""
    current = auth_service.validate_session(token)
    if not current or not current.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    if not notification_service.delete_config(project_id):
        raise HTTPException(status_code=404, detail="Config not found")


@api_router.get("/notifications", response_model=list[NotificationResponse])
def get_notifications(
    token: str = Query(...),
    unread_only: bool = Query(False),
    limit: int = Query(50, le=100),
    auth_service: AuthService = Depends(get_auth_service_instance),
    notification_service: NotificationService = Depends(get_notification_service_instance),
):
    """Get notifications for the current user."""
    current = auth_service.validate_session(token)
    if not current:
        raise HTTPException(status_code=401, detail="Invalid session")

    notifications = notification_service.get_notifications(
        user_id=current.user.id,
        unread_only=unread_only,
        limit=limit,
    )

    return [
        NotificationResponse(
            id=n.id,
            user_id=n.user_id,
            project_id=n.project_id,
            event_type=n.event_type.value,
            channel=n.channel.value,
            priority=n.priority.value,
            title=n.title,
            message=n.message,
            data=n.data,
            is_read=n.is_read,
            read_at=n.read_at,
            created_at=n.created_at,
        )
        for n in notifications
    ]


@api_router.get("/notifications/count")
def get_notification_count(
    token: str = Query(...),
    auth_service: AuthService = Depends(get_auth_service_instance),
    notification_service: NotificationService = Depends(get_notification_service_instance),
):
    """Get unread notification count for the current user."""
    current = auth_service.validate_session(token)
    if not current:
        raise HTTPException(status_code=401, detail="Invalid session")

    return {"unread_count": notification_service.get_unread_count(current.user.id)}


@api_router.post("/notifications/{notification_id}/read", status_code=200)
def mark_notification_read(
    notification_id: int,
    token: str = Query(...),
    auth_service: AuthService = Depends(get_auth_service_instance),
    notification_service: NotificationService = Depends(get_notification_service_instance),
):
    """Mark a notification as read."""
    current = auth_service.validate_session(token)
    if not current:
        raise HTTPException(status_code=401, detail="Invalid session")

    if not notification_service.mark_as_read(notification_id):
        raise HTTPException(status_code=404, detail="Notification not found or already read")

    return {"status": "read"}


@api_router.post("/notifications/read-all", status_code=200)
def mark_all_notifications_read(
    token: str = Query(...),
    auth_service: AuthService = Depends(get_auth_service_instance),
    notification_service: NotificationService = Depends(get_notification_service_instance),
):
    """Mark all notifications as read for the current user."""
    current = auth_service.validate_session(token)
    if not current:
        raise HTTPException(status_code=401, detail="Invalid session")

    count = notification_service.mark_all_as_read(current.user.id)
    return {"marked_read": count}


@api_router.delete("/notifications/{notification_id}", status_code=200)
def delete_notification(
    notification_id: int,
    token: str = Query(...),
    auth_service: AuthService = Depends(get_auth_service_instance),
    notification_service: NotificationService = Depends(get_notification_service_instance),
):
    """Delete a notification."""
    current = auth_service.validate_session(token)
    if not current:
        raise HTTPException(status_code=401, detail="Invalid session")

    if not notification_service.delete_notification(notification_id):
        raise HTTPException(status_code=404, detail="Notification not found")

    return {"status": "deleted"}


@api_router.get("/projects/{project_id}/webhooks", response_model=list[WebhookDeliveryResponse])
def get_webhook_deliveries(
    project_id: int,
    token: str = Query(...),
    limit: int = Query(50, le=100),
    auth_service: AuthService = Depends(get_auth_service_instance),
    notification_service: NotificationService = Depends(get_notification_service_instance),
):
    """Get webhook deliveries for a project."""
    current = auth_service.validate_session(token)
    if not current:
        raise HTTPException(status_code=401, detail="Invalid session")

    deliveries = notification_service.get_webhook_deliveries(project_id, limit)

    return [
        WebhookDeliveryResponse(
            id=d.id,
            project_id=d.project_id,
            notification_id=d.notification_id,
            event_type=d.event_type.value,
            url=d.url,
            response_status=d.response_status,
            success=d.success,
            attempt=d.attempt,
            created_at=d.created_at,
        )
        for d in deliveries
    ]


@api_router.get("/projects/{project_id}/webhooks/stats", response_model=WebhookStatsResponse)
def get_webhook_stats(
    project_id: int,
    token: str = Query(...),
    days: int = Query(7, ge=1, le=30),
    auth_service: AuthService = Depends(get_auth_service_instance),
    notification_service: NotificationService = Depends(get_notification_service_instance),
):
    """Get webhook delivery statistics for a project."""
    current = auth_service.validate_session(token)
    if not current:
        raise HTTPException(status_code=401, detail="Invalid session")

    stats = notification_service.get_webhook_stats(project_id, days)

    return WebhookStatsResponse(
        total=stats["total"],
        successful=stats["successful"],
        failed=stats["failed"],
        success_rate=stats["success_rate"],
    )


@api_router.get("/notifications/event-types")
def get_notification_event_types():
    """Get available notification event types."""
    return {
        "event_types": [
            {"value": e.value, "name": e.name}
            for e in NotificationEventType
        ]
    }


@api_router.get("/notifications/channels")
def get_notification_channels():
    """Get available notification channels."""
    return {
        "channels": [
            {"value": c.value, "name": c.name}
            for c in NotificationChannel
        ]
    }
