# PRDForge

> Where PRDs are forged into code.

PRDForge is a standalone, project-agnostic platform for PRD-driven AI code generation. It provides a web dashboard to manage, visualize, and control autonomous PRD execution across multiple projects with pluggable AI backends.

## Features

### Implemented (Phase 1-2)

- **Core Execution Engine** - RunManager, PRDExecutor, GitManager
- **AI Executor Abstraction** - Pluggable backend system with Claude CLI executor
- **PRD Parsing** - JSON and Markdown (Ralph-style) format support
- **Project Configuration** - YAML/JSON config with environment variable support
- **SQLite Database** - Persistent storage with migration system
- **CLI** - Commands for init, serve, run, and more
- **Web Dashboard** - HTMX-powered UI with real-time updates
- **REST API** - Full CRUD for projects and runs
- **WebSocket** - Real-time run progress and log streaming
- **Docker Support** - Production and development containers

### Planned (Phase 3-5)

- **Multi-Project Management** - Central dashboard for multiple projects
- **Skills System** - Base skills with project-specific overrides
- **AI Backend Plugins** - Codex, Gemini, direct Claude API
- **Cost Tracking** - Token usage and cost analytics
- **Quality Gates** - Configurable acceptance criteria per task
- **Team Features** - User authentication and audit logging

## Quick Start

### Docker Compose

```bash
# Clone and configure
git clone https://github.com/yourusername/prdforge.git
cd prdforge
cp .env.example .env
# Edit .env with your settings

# Start the server
docker-compose up -d

# Open dashboard
open http://localhost:8000
```

### Local Development

```bash
# Install with dependencies
pip install -e ".[web,dev]"

# Initialize database
prdforge db-init

# Start server
prdforge serve

# Run tests
pytest tests/
```

## CLI Commands

```bash
prdforge version              # Show version
prdforge serve                # Start web server
prdforge init                 # Initialize project config
prdforge db-init              # Initialize database
prdforge list-prds            # List PRD files
prdforge run <prd> --dry-run  # Execute PRD (dry run)
```

## Documentation

- [Getting Started Guide](docs/getting-started.md)
- [PRD Format](docs/prd-format.md)
- [Configuration Reference](docs/configuration.md)

## Development

See `docs/prds/prd_prdforge_standalone_project.json` for the full implementation roadmap.

### Project Structure

```
prdforge/
├── src/
│   ├── engine/      # RunManager, PRDExecutor, GitManager
│   ├── executors/   # AI backend plugins (Claude, Codex, Gemini)
│   ├── prd/         # PRD parsers (JSON, Markdown)
│   ├── config/      # Configuration system
│   ├── db/          # SQLite models and repositories
│   ├── api/         # REST + WebSocket + Templates
│   └── cli.py       # CLI entry point
├── config/          # Configuration templates
├── docs/            # Documentation
└── tests/           # Unit and integration tests
```

### Running Tests

```bash
# All tests
pytest tests/

# With coverage
pytest tests/ --cov=src

# Specific test file
pytest tests/unit/test_database.py -v
```

## Inspiration

- [Ralph](https://github.com/aymenfurter/ralph) - VSCode extension for Copilot PRD execution
- [Geoffrey Huntley's Ralph technique](https://ghuntley.com/ralph/)

## License

Proprietary (internal tool) - potential open source release later.
