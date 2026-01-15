# PRDForge

> Where PRDs are forged into code.

PRDForge is a standalone, project-agnostic platform for PRD-driven AI code generation. It provides a web dashboard to manage, visualize, and control autonomous PRD execution across multiple projects with pluggable AI backends.

## Features (Planned)

- **Web Dashboard** - Central UI to manage multiple projects
- **Multi-AI Backend** - Claude CLI, Codex, Gemini support
- **Skills System** - Base skills with project-specific overrides
- **Visual Controls** - Start, pause, stop task execution
- **Rich Visualizations** - Task timeline, git branch graph, cost tracking
- **Quality Gates** - Configurable acceptance criteria per task

## Quick Start

```bash
# Start with Docker Compose (once implemented)
docker-compose up -d

# Open dashboard
open http://localhost:3000
```

## Development

See `docs/prds/prd_prdforge_standalone_project.json` for the full implementation roadmap.

### Project Structure

```
prdforge/
├── src/
│   ├── engine/      # RunManager, PRDExecutor, GitManager
│   ├── executors/   # AI backend plugins (Claude, Codex, Gemini)
│   ├── prd/         # PRD parsers (JSON, Markdown)
│   ├── skills/      # Base skills and registry
│   ├── db/          # SQLite models and repositories
│   └── api/         # REST + WebSocket endpoints
├── frontend/        # Web dashboard (TBD: Vue/Svelte or Next.js)
├── config/          # Configuration templates
├── docs/prds/       # PRD files
└── tests/           # Unit and integration tests
```

### Working with Claude

```bash
# Start Claude Code in this directory
claude

# Ask Claude to implement tasks from the PRD
# "Implement task phase1-001 from docs/prds/prd_prdforge_standalone_project.json"
```

## Inspiration

- [Ralph](https://github.com/aymenfurter/ralph) - VSCode extension for Copilot PRD execution
- [Geoffrey Huntley's Ralph technique](https://ghuntley.com/ralph/)

## License

Proprietary (internal tool) - potential open source release later.
