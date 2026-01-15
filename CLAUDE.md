# CLAUDE.md - PRDForge

This file provides guidance to Claude Code when working with this codebase.

## Project Overview

PRDForge is a standalone platform for PRD-driven AI code generation. It's being built from scratch based on patterns extracted from JobHunterAI's meta_prd_runner.sh.

## Current Status

**Phase 1: Core Engine Extraction** - Not started

See `docs/prds/prd_prdforge_standalone_project.json` for the full roadmap.

## Development Workflow

1. Check the PRD for the next task to implement
2. Implement the task
3. Update this file if architecture decisions are made
4. Mark task as complete in PRD (set `passes: true`)

## Key Decisions Made

- **Storage**: SQLite for simplicity
- **Deployment**: Docker Compose
- **CLI**: Minimal (serve, init, version)
- **AI Backends**: Pluggable, Claude CLI primary

## Commands

```bash
# Run CLI (once implemented)
python -m src.cli version

# Run tests (once implemented)
pytest tests/

# Start server (once implemented)
python -m src.cli serve
```

## Directory Structure

```
src/
├── engine/      # Core execution: RunManager, PRDExecutor, GitManager
├── executors/   # AI backends: ClaudeCLI, Codex, Gemini
├── prd/         # PRD handling: JSONParser, MarkdownParser, Converter
├── skills/      # Skills system: BaseSkill, Registry
├── db/          # Data layer: SQLite models, repositories
├── api/         # Web API: REST endpoints, WebSocket
└── cli.py       # CLI entry point
```
