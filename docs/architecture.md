# PRDForge Architecture

This document describes the architecture of PRDForge, a PRD-driven AI code generation platform.

## Overview

PRDForge follows a modular, layered architecture designed for extensibility and maintainability:

```
┌─────────────────────────────────────────────────────────────────┐
│                        Web Dashboard                             │
│                    (FastAPI + Jinja2 + Alpine.js)               │
├─────────────────────────────────────────────────────────────────┤
│                         REST API Layer                           │
│                      (FastAPI + Pydantic)                        │
├──────────────────┬────────────────────┬─────────────────────────┤
│   Run Engine     │   Skills System    │   Notification System   │
│   (Orchestrator) │   (Pluggable)      │   (Event-Driven)        │
├──────────────────┴────────────────────┴─────────────────────────┤
│                        Executor Layer                            │
│        (Claude CLI, Claude API, OpenAI, Gemini, DryRun)         │
├─────────────────────────────────────────────────────────────────┤
│                        Data Layer                                │
│                   (SQLite + Repositories)                        │
└─────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
src/
├── api/              # Web layer
│   ├── routes.py     # API endpoints and page routes
│   ├── templates/    # Jinja2 HTML templates
│   └── static/       # Static assets (CSS, JS)
├── engine/           # Core execution engine
│   ├── run_manager.py      # Run orchestration
│   ├── git_manager.py      # Git operations
│   ├── quality_gates.py    # Quality gate checks
│   ├── cost_tracker.py     # Token/cost tracking
│   └── notification_service.py  # Notification dispatch
├── executors/        # AI backend plugins
│   ├── base.py       # BaseExecutor interface
│   ├── claude_cli.py # Claude CLI implementation
│   ├── claude_api_executor.py  # Claude API implementation
│   ├── openai_executor.py      # OpenAI implementation
│   ├── gemini_executor.py      # Gemini implementation
│   └── factory.py    # Executor factory
├── prd/              # PRD handling
│   ├── models.py     # PRD data models
│   ├── json_parser.py      # JSON PRD parser
│   ├── markdown_parser.py  # Markdown PRD parser
│   └── converter.py  # Format converter
├── skills/           # Skills system
│   ├── base.py       # BaseSkill interface
│   ├── registry.py   # Skill registration
│   └── builtin/      # Built-in skills
├── db/               # Data layer
│   ├── database.py   # SQLite connection management
│   ├── models.py     # Data models (dataclasses)
│   ├── repositories.py     # Repository pattern
│   ├── migrations.py # Schema migrations
│   └── *_repository.py     # Domain-specific repos
├── config/           # Configuration
│   ├── models.py     # Config data models
│   ├── loader.py     # Config file loading
│   └── validator.py  # Config validation
└── cli.py            # CLI entry point
```

## Core Components

### 1. Run Engine (`src/engine/`)

The run engine orchestrates PRD execution:

**RunManager** - Central orchestrator
- Creates and manages run instances
- Coordinates task execution order
- Handles pause/resume/cancel operations
- Tracks progress and updates status

**GitManager** - Git operations
- Creates feature branches per run
- Manages commits with standardized messages
- Handles merge workflows (PRD → base → develop)
- Branch cleanup and conflict resolution

**PRDExecutor** - Task execution
- Iterates through PRD tasks in dependency order
- Invokes the appropriate AI executor
- Validates task completion
- Updates task status in database

### 2. Executor Layer (`src/executors/`)

All executors implement the `BaseExecutor` interface:

```python
class BaseExecutor(ABC):
    @abstractmethod
    async def execute(
        self,
        task: PRDTask,
        context: ExecutionContext
    ) -> ExecutionResult:
        """Execute a single PRD task."""
        pass

    @abstractmethod
    def get_capabilities(self) -> ExecutorCapabilities:
        """Return executor capabilities."""
        pass
```

**Available Executors:**
- `ClaudeCLIExecutor` - Uses Claude Code CLI
- `ClaudeAPIExecutor` - Direct Anthropic API calls
- `OpenAIExecutor` - OpenAI GPT-4/Codex
- `GeminiExecutor` - Google Gemini Pro
- `DryRunExecutor` - Testing without AI calls

### 3. Skills System (`src/skills/`)

Skills extend executor capabilities:

```python
class BaseSkill(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @abstractmethod
    def execute(self, context: SkillContext) -> SkillResult: ...
```

Skills can be:
- **Built-in**: Shipped with PRDForge
- **Project-level**: Defined in project's `.prdforge/skills/`
- **Global**: Installed in `~/.prdforge/skills/`

### 4. Data Layer (`src/db/`)

Uses SQLite with the repository pattern:

**Models** (dataclasses):
- `Project` - Project configuration
- `Run` - Execution run instance
- `Task` - Individual PRD task
- `TaskExecution` - Task execution attempt
- `LogEntry` - Execution logs
- `User` - User accounts
- `Notification` - In-app notifications
- `CostRecord` - Token/cost tracking

**Repositories**:
- Handle all database operations
- Provide type-safe CRUD operations
- Encapsulate SQL queries
- Support migrations

### 5. Notification System (`src/engine/notification_service.py`)

Event-driven notification system:

```python
class NotificationEvent:
    event_type: NotificationEventType
    project_id: int
    run_id: Optional[str]
    task_id: Optional[str]
    data: dict
```

**Channels:**
- In-app (stored in database)
- Webhooks (HTTP POST with HMAC signing)
- Email (placeholder for future)
- Slack (placeholder for future)

### 6. Quality Gates (`src/engine/quality_gates.py`)

Configurable checks that run before/after tasks:

```python
class QualityGateCheck:
    name: str
    command: str
    timeout_seconds: int
    required: bool
```

Gate types:
- Pre-task checks (before execution)
- Post-task checks (after execution)
- Run-level checks (at start/end)

## Data Flow

### PRD Execution Flow

```
1. User starts run via API/UI
       │
       ▼
2. RunManager creates run record
       │
       ▼
3. GitManager creates feature branch
       │
       ▼
4. PRDExecutor loads and parses PRD
       │
       ▼
5. For each task (respecting dependencies):
   │
   ├── Check blocked_by dependencies
   │
   ├── Run pre-task quality gates
   │
   ├── Execute task via Executor
   │       │
   │       ├── Build prompt with context
   │       ├── Call AI backend
   │       └── Parse and apply changes
   │
   ├── Run post-task quality gates
   │
   ├── GitManager commits changes
   │
   ├── Update task status
   │
   └── Send notifications
       │
       ▼
6. Run completion
   │
   ├── Run final quality gates
   ├── Update run status
   └── Send completion notification
```

### API Request Flow

```
HTTP Request
    │
    ▼
FastAPI Router
    │
    ├── Validate request (Pydantic)
    │
    ├── Execute business logic
    │   │
    │   ├── Repository operations
    │   └── Engine operations
    │
    └── Return response (JSON/HTML)
```

## Configuration

### Environment Variables

```bash
# Server
PRDFORGE_PORT=8000
PRDFORGE_HOST=0.0.0.0
PRDFORGE_LOG_LEVEL=INFO

# Database
PRDFORGE_DB_PATH=~/.prdforge/prdforge.db

# AI Backends
ANTHROPIC_API_KEY=sk-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...

# Security
PRDFORGE_SECRET_KEY=...
PRDFORGE_WEBHOOK_SECRET=...
```

### Project Configuration

Per-project settings in `prdforge.yaml`:

```yaml
name: my-project
path: /path/to/project
git:
  default_branch: main
  remote: origin
executor:
  type: claude-api
  model: claude-sonnet-4-20250514
quality_gates:
  pre_task:
    - name: lint
      command: npm run lint
  post_task:
    - name: test
      command: npm test
notifications:
  events: [run_completed, run_failed, task_failed]
  channels: [in_app, webhook]
  webhook_url: https://...
```

## Security Considerations

1. **Authentication**: Session-based auth with secure token storage
2. **API Keys**: Stored in environment variables, never in code
3. **Webhooks**: HMAC-SHA256 signed payloads
4. **Database**: SQLite with parameterized queries (no SQL injection)
5. **File Access**: Sandboxed to project directories

## Extensibility Points

1. **New Executors**: Implement `BaseExecutor` interface
2. **New Skills**: Implement `BaseSkill` interface
3. **Custom Quality Gates**: Add command-based checks
4. **Notification Channels**: Extend `NotificationService`
5. **PRD Formats**: Add new parser in `src/prd/`

## Performance Considerations

1. **Database**: SQLite with WAL mode for concurrent reads
2. **Polling**: 30-second intervals for notifications (configurable)
3. **Caching**: In-memory caching for frequently accessed data
4. **Async**: FastAPI async endpoints for non-blocking I/O
5. **Streaming**: SSE for real-time log streaming (planned)

## Testing Strategy

```
tests/
├── unit/           # Unit tests for individual components
├── integration/    # Tests with real database
└── e2e/            # End-to-end API tests
```

Run tests: `pytest tests/ -v`
