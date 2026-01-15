# Getting Started with PRDForge

PRDForge is a PRD-driven AI code generation platform. This guide covers installation, configuration, and basic usage.

## Prerequisites

- Python 3.10 or higher
- Docker and Docker Compose (recommended)
- Git

## Installation

### Option 1: Docker Compose (Recommended)

```bash
# Clone the repository
git clone https://github.com/yourusername/prdforge.git
cd prdforge

# Copy environment configuration
cp .env.example .env

# Edit .env with your API keys
# ANTHROPIC_API_KEY=your_key_here

# Start the server
docker-compose up -d

# Open the dashboard
open http://localhost:8000
```

### Option 2: Local Development

```bash
# Clone and enter the repository
git clone https://github.com/yourusername/prdforge.git
cd prdforge

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install with web dependencies
pip install -e ".[web,dev]"

# Initialize the database
prdforge db-init

# Start the server
prdforge serve
```

## Configuration

### Environment Variables

Create a `.env` file or set environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `PRDFORGE_PORT` | Web server port | `8000` |
| `PRDFORGE_LOG_LEVEL` | Log level (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `PRDFORGE_DB_PATH` | SQLite database path | `~/.prdforge/prdforge.db` |
| `ANTHROPIC_API_KEY` | API key for Claude executor | - |
| `OPENAI_API_KEY` | API key for Codex executor | - |

### Project Configuration

Each project can have a `prdforge.yaml` or `prdforge.json` file:

```yaml
# prdforge.yaml
name: my-project
path: /path/to/project
git:
  default_branch: main
executor:
  type: claude-cli
  model: claude-sonnet-4-20250514
```

## Quick Start Tutorial

### 1. Add a Project

Navigate to http://localhost:8000/projects and click "Add Project":

- **Name**: my-awesome-app
- **Path**: /path/to/your/project
- **Type**: Local Path

### 2. Create a PRD File

Create a PRD file in your project (e.g., `docs/prds/feature.json`):

```json
{
  "meta": {
    "feature_name": "User Authentication",
    "description": "Add basic user auth with login/logout"
  },
  "phases": [
    {
      "phase": 1,
      "name": "Core Auth",
      "description": "Implement authentication backend"
    }
  ],
  "tasks": [
    {
      "id": "auth-001",
      "phase": 1,
      "category": "backend",
      "description": "Create User model and database migrations",
      "steps": [
        "Define User model with email, password_hash",
        "Create database migration",
        "Add password hashing utility"
      ],
      "passes": false,
      "blocked_by": []
    }
  ]
}
```

### 3. Start a Run

From the project detail page, click "Start Run":

- **PRD Path**: `docs/prds/feature.json`
- **Base Branch**: `develop`

### 4. Monitor Progress

The run detail page shows:

- **Progress bar** with completed/failed tasks
- **Task list** with status indicators
- **Control panel** to pause/resume/cancel

## CLI Commands

```bash
# Show version
prdforge version

# Start the web server
prdforge serve --port 8000

# Initialize a project configuration
prdforge init --name my-project --path /path/to/project

# Initialize the database
prdforge db-init

# List PRDs in current directory
prdforge list-prds

# Execute a PRD (dry run)
prdforge run docs/prds/feature.json --dry-run

# Execute a PRD
prdforge run docs/prds/feature.json --base-branch develop
```

## PRD Format

PRDForge supports two PRD formats:

### JSON Format

The standard format with explicit structure:

```json
{
  "meta": {
    "feature_name": "Feature Name",
    "description": "Feature description"
  },
  "phases": [...],
  "tasks": [...]
}
```

### Markdown Format (Ralph-style)

Human-readable markdown with checkboxes:

```markdown
# My Feature PRD

## Phase 1: Core Implementation

- [ ] **Task ID:** task-001
  **Category:** backend
  **Description:** Implement the core logic

  Steps:
  - Step 1
  - Step 2
```

## Troubleshooting

### Server won't start

1. Check if the port is already in use:
   ```bash
   lsof -i :8000
   ```

2. Verify database path is writable:
   ```bash
   ls -la ~/.prdforge/
   ```

### Docker issues

1. Rebuild the container:
   ```bash
   docker-compose build --no-cache
   docker-compose up -d
   ```

2. Check container logs:
   ```bash
   docker-compose logs -f api
   ```

### API errors

Check the server logs and ensure your API keys are configured correctly in `.env`.

## Next Steps

- Explore the [API Reference](api-reference.md)
- Learn about [Skills System](skills.md)
- Configure [Quality Gates](quality-gates.md)
