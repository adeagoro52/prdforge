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
