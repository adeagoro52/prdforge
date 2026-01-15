# Contributing to PRDForge

Thank you for your interest in contributing to PRDForge! This document provides guidelines for contributing to the project.

## Code of Conduct

Be respectful and constructive in all interactions. We welcome contributors of all backgrounds and experience levels.

## Getting Started

### Prerequisites

- Python 3.10+
- Git
- Docker (optional, for container testing)

### Development Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/prdforge.git
cd prdforge

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies
pip install -e ".[dev,web]"

# Set up pre-commit hooks (optional but recommended)
pre-commit install
```

### Running Tests

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run specific test file
pytest tests/unit/test_database.py

# Run tests matching pattern
pytest -k "test_project"
```

### Running the Server

```bash
# Development mode with auto-reload
python -m src.cli serve --reload

# Or use Docker
docker-compose --profile dev up
```

## Project Structure

```
prdforge/
├── src/
│   ├── api/          # Web API and templates
│   ├── db/           # Database layer
│   ├── engine/       # Core execution engine
│   ├── executors/    # AI backend plugins
│   ├── prd/          # PRD parsing
│   ├── skills/       # Skills system
│   ├── config/       # Configuration
│   └── cli.py        # CLI entry point
├── tests/
│   ├── unit/         # Unit tests
│   ├── integration/  # Integration tests
│   └── e2e/          # End-to-end tests
├── docs/             # Documentation
└── config/           # Configuration files
```

## Making Changes

### Branch Naming

- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation
- `refactor/description` - Code refactoring

### Commit Messages

Follow conventional commits format:

```
type(scope): description

[optional body]

[optional footer]
```

Types:
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation
- `refactor` - Code refactoring
- `test` - Adding tests
- `chore` - Maintenance

Examples:
```
feat(executors): add Gemini AI backend support

Implements GeminiExecutor with support for:
- Text generation
- Token counting
- Cost estimation

Closes #42
```

```
fix(api): handle empty PRD file gracefully

Return 400 Bad Request instead of 500 when PRD file is empty.
```

### Code Style

We use:
- **Ruff** for linting and formatting
- **Black** for code formatting (via Ruff)
- **isort** for import sorting (via Ruff)
- **mypy** for type checking

```bash
# Format code
ruff format .

# Fix linting issues
ruff check --fix .

# Run type checking
mypy src/
```

### Type Hints

Use type hints for all function signatures:

```python
# Good
def create_project(
    name: str,
    path: Path,
    tags: list[str] | None = None,
) -> Project:
    ...

# Avoid
def create_project(name, path, tags=None):
    ...
```

### Documentation

- Add docstrings to all public functions, classes, and modules
- Follow Google docstring format
- Update docs/ when adding new features

```python
def execute_task(task: PRDTask, context: ExecutionContext) -> TaskResult:
    """Execute a single PRD task.

    Args:
        task: The PRD task to execute.
        context: Execution context including project path and config.

    Returns:
        Result of the task execution.

    Raises:
        ExecutorError: If the AI backend fails.
    """
    ...
```

## Pull Request Process

### Before Submitting

1. **Test your changes**
   ```bash
   pytest tests/
   ```

2. **Format code**
   ```bash
   ruff format .
   ruff check --fix .
   ```

3. **Update documentation** if needed

4. **Update CHANGELOG.md** for user-facing changes

### PR Template

When opening a PR, include:

```markdown
## Summary
[Brief description of changes]

## Changes
- Change 1
- Change 2

## Testing
[How you tested the changes]

## Screenshots
[If UI changes, include before/after screenshots]

## Checklist
- [ ] Tests pass locally
- [ ] Code follows project style
- [ ] Documentation updated
- [ ] CHANGELOG updated (if applicable)
```

### Review Process

1. Submit PR against `develop` branch
2. Wait for CI checks to pass
3. Address reviewer feedback
4. Once approved, maintainer will merge

## Adding Features

### New Executor

1. Create file in `src/executors/`
2. Implement `ExecutorPlugin` interface
3. Add tests in `tests/unit/`
4. Update documentation

See [Executor Development Guide](docs/executors.md).

### New Skill

1. Create file in `src/skills/builtin/` (or project-level)
2. Implement `Skill` interface
3. Add tests
4. Update documentation

See [Skills Development Guide](docs/skills.md).

### New API Endpoint

1. Add route in `src/api/routes.py`
2. Create Pydantic models for request/response
3. Add tests
4. Update API documentation

## Testing Guidelines

### Unit Tests

- Test individual functions and classes
- Mock external dependencies
- Aim for high coverage of business logic

```python
class TestProjectRepository:
    def test_create_and_get(self, db):
        repo = ProjectRepository(db)
        project = Project(name="test", path="/tmp")

        project_id = repo.create(project)

        retrieved = repo.get_by_id(project_id)
        assert retrieved.name == "test"
```

### Integration Tests

- Test component interactions
- Use real database (SQLite in memory)
- Test API endpoints

```python
def test_create_project_api(client):
    response = client.post("/api/projects", json={
        "name": "test-project",
        "path": "/tmp/test",
    })

    assert response.status_code == 201
    assert response.json()["name"] == "test-project"
```

### Test Fixtures

Use pytest fixtures for common setup:

```python
@pytest.fixture
def db(tmp_path):
    db = Database(tmp_path / "test.db")
    db.initialize()
    return db

@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)
```

## Issue Guidelines

### Bug Reports

Include:
- PRDForge version
- Python version
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Error messages/logs

### Feature Requests

Include:
- Use case description
- Proposed solution (if any)
- Alternatives considered

## Getting Help

- **Questions**: Open a GitHub Discussion
- **Bugs**: Open a GitHub Issue
- **Security**: Email security@example.com

## License

By contributing, you agree that your contributions will be licensed under the project's license.

Thank you for contributing to PRDForge!
