# Executor Plugin Development Guide

Executors are the AI backends that power PRDForge's code generation. This guide covers creating custom executor plugins.

## Overview

Executors handle:
- Communication with AI services (APIs, CLI tools)
- Prompt construction and response parsing
- Retry logic and error handling
- Token counting and cost estimation

## Architecture

PRDForge supports a plugin-based executor system:

```
Priority (highest to lowest):
1. Project plugins   (.prdforge/plugins/)
2. User plugins      (~/.prdforge/plugins/)
3. Built-in plugins  (src/executors/)
```

## Built-in Executors

| Executor | Description |
|----------|-------------|
| `claude-cli` | Claude Code CLI (recommended for local dev) |
| `claude-api` | Direct Anthropic API calls |
| `openai` | OpenAI GPT-4/Codex |
| `gemini` | Google Gemini Pro |
| `dry-run` | Testing without AI calls |

## Creating an Executor Plugin

### Step 1: Implement ExecutorPlugin

```python
# my_executor.py
from dataclasses import dataclass
from typing import Any

from src.executors.base import ExecutorConfig, ExecutionResult, TaskContext
from src.executors.plugin import (
    ExecutorPlugin,
    PluginSchema,
    PluginConfigField,
)


class MyExecutor(ExecutorPlugin):
    """Custom AI executor implementation."""

    @property
    def name(self) -> str:
        return "my-executor"

    @property
    def version(self) -> str:
        return "1.0.0"

    @classmethod
    def get_plugin_info(cls) -> dict[str, Any]:
        """Return plugin metadata."""
        return {
            "name": "my-executor",
            "display_name": "My Custom Executor",
            "description": "Custom AI executor for special use cases",
            "version": "1.0.0",
            "author": "Your Name",
            "homepage": "https://github.com/...",
        }

    @classmethod
    def get_config_schema(cls) -> PluginSchema:
        """Define configuration options."""
        return PluginSchema(fields=[
            PluginConfigField(
                name="api_key",
                type="secret",
                description="API key for authentication",
                required=True,
            ),
            PluginConfigField(
                name="model",
                type="string",
                description="Model to use",
                default="default-model",
                enum=["default-model", "advanced-model"],
            ),
            PluginConfigField(
                name="temperature",
                type="number",
                description="Sampling temperature",
                default=0.0,
                min_value=0.0,
                max_value=2.0,
            ),
            PluginConfigField(
                name="max_tokens",
                type="integer",
                description="Maximum tokens in response",
                default=4096,
                min_value=1,
                max_value=100000,
            ),
        ])

    @classmethod
    def get_capabilities(cls) -> list[str]:
        """Declare supported capabilities."""
        return [
            "code_generation",
            "streaming",      # Supports streaming responses
            "tool_use",       # Supports tool/function calls
        ]

    def _execute_impl(self, context: TaskContext) -> ExecutionResult:
        """Implement the actual execution logic."""
        # Build the prompt
        prompt = self.build_prompt(context)

        try:
            # Call your AI service
            response = self._call_api(prompt)

            return ExecutionResult(
                success=True,
                output=response.text,
                tokens_used=response.total_tokens,
                metadata={
                    "model": self.config.model,
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                },
            )

        except RateLimitError as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Rate limited: {e}",
            )

        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
            )

    def _call_api(self, prompt: str):
        """Make the actual API call."""
        # Your API implementation here
        api_key = self.config.extra.get("api_key")
        model = self.config.model or self.config.extra.get("model", "default-model")

        # Example with httpx
        import httpx

        response = httpx.post(
            "https://api.myservice.com/generate",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "prompt": prompt,
                "max_tokens": self.config.max_tokens,
                "temperature": self.config.temperature,
            },
            timeout=self.config.timeout,
        )
        response.raise_for_status()
        return response.json()

    def health_check(self) -> bool:
        """Verify the executor is operational."""
        api_key = self.config.extra.get("api_key")
        if not api_key:
            return False

        try:
            # Make a simple API call to verify connectivity
            import httpx
            response = httpx.get(
                "https://api.myservice.com/health",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=5,
            )
            return response.status_code == 200
        except Exception:
            return False

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost in USD."""
        model = self.config.model or "default-model"

        # Define pricing per 1K tokens
        pricing = {
            "default-model": {"input": 0.001, "output": 0.002},
            "advanced-model": {"input": 0.01, "output": 0.03},
        }

        rates = pricing.get(model, pricing["default-model"])
        input_cost = (prompt_tokens / 1000) * rates["input"]
        output_cost = (completion_tokens / 1000) * rates["output"]

        return input_cost + output_cost
```

### Step 2: Install the Plugin

Place your executor file in one of these locations:

**User-level** (available to all projects):
```
~/.prdforge/plugins/my_executor.py
```

**Project-level** (specific to one project):
```
my-project/.prdforge/plugins/my_executor.py
```

### Step 3: Configure the Executor

In `prdforge.yaml`:

```yaml
executors:
  default: my-executor
  my-executor:
    api_key: "${MY_EXECUTOR_API_KEY}"
    model: advanced-model
    temperature: 0.1
    max_tokens: 8192
```

Or via environment variables:
```bash
export MY_EXECUTOR_API_KEY=your_api_key_here
```

## Core Interfaces

### ExecutorConfig

Base configuration shared by all executors:

```python
@dataclass
class ExecutorConfig:
    max_retries: int = 3        # Retry attempts
    base_delay: float = 1.0     # Base backoff delay (seconds)
    max_delay: float = 60.0     # Max backoff delay
    timeout: int = 600          # Timeout per execution (seconds)
    model: str | None = None    # Model identifier
    temperature: float = 0.0    # Generation temperature
    max_tokens: int | None = None
    extra: dict[str, Any] = {}  # Plugin-specific options
```

### TaskContext

Context provided to `_execute_impl`:

```python
@dataclass
class TaskContext:
    task_id: str           # Unique task identifier
    description: str       # Human-readable description
    steps: list[str]       # Steps to complete
    project_path: str      # Project root path
    prd_path: str         # Path to PRD file
    phase: int = 1        # Phase number
    category: str = "general"
    extra_context: dict[str, Any] = {}
```

### ExecutionResult

Return type from `_execute_impl`:

```python
@dataclass
class ExecutionResult:
    success: bool              # Whether execution succeeded
    output: str               # Raw output text
    error: str | None = None  # Error message if failed
    tokens_used: int | None = None
    duration_seconds: float = 0.0
    retries: int = 0
    metadata: dict[str, Any] = {}
```

## Configuration Schema

Define configuration fields with `PluginConfigField`:

```python
PluginConfigField(
    name="field_name",      # Configuration key
    type="string",          # Type: string, secret, integer, number, boolean, array
    description="...",      # Help text
    required=False,         # Is this field required?
    default=None,           # Default value
    enum=["a", "b"],       # Allowed values (optional)
    min_value=0,           # Minimum (for numbers)
    max_value=100,         # Maximum (for numbers)
    pattern="^[a-z]+$",    # Regex pattern (for strings)
)
```

Field types:
- `string` - Text input
- `secret` - Password/API key (hidden in UI)
- `integer` - Whole numbers
- `number` - Decimal numbers
- `boolean` - True/false toggle
- `array` - List of values

## Prompt Building

Override `build_prompt` to customize prompt generation:

```python
def build_prompt(self, context: TaskContext) -> str:
    """Build a custom prompt for this executor."""

    # Access project info
    project = context.project_path

    # Get task details
    steps = "\n".join(f"- {step}" for step in context.steps)

    # Include extra context if provided
    extra = context.extra_context.get("additional_instructions", "")

    return f"""You are a code generation assistant.

Project: {project}

Task: {context.description}

Steps to complete:
{steps}

{extra}

Please implement the task following best practices for this codebase.
"""
```

## Retry Logic

The base class handles retries automatically. Customize behavior by overriding:

```python
def _should_retry(self, result: ExecutionResult) -> bool:
    """Determine if execution should be retried."""
    if result.success:
        return False

    # Custom retry logic
    if "quota exceeded" in (result.error or "").lower():
        return True

    # Fall back to default behavior
    return super()._should_retry(result)

def _is_retryable_error(self, error: Exception) -> bool:
    """Determine if an exception should trigger retry."""
    if isinstance(error, MyRecoverableError):
        return True
    return super()._is_retryable_error(error)
```

## Health Checks

Implement `health_check` for monitoring:

```python
def health_check(self) -> bool:
    """Check if the executor is operational."""
    # Check required configuration
    if not self.config.extra.get("api_key"):
        return False

    # Test API connectivity
    try:
        response = self._make_test_request()
        return response.status_code == 200
    except Exception:
        return False
```

## Cost Estimation

Implement `estimate_cost` for budget tracking:

```python
def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate cost in USD for the given token counts."""
    model = self.config.model or "default"

    # Model-specific pricing (per 1K tokens)
    PRICING = {
        "fast-model": {"input": 0.0005, "output": 0.001},
        "smart-model": {"input": 0.01, "output": 0.03},
    }

    rates = PRICING.get(model, PRICING["fast-model"])

    return (
        (prompt_tokens / 1000) * rates["input"] +
        (completion_tokens / 1000) * rates["output"]
    )
```

## Streaming Support

For executors that support streaming:

```python
async def stream_execute(self, context: TaskContext):
    """Execute with streaming response."""
    prompt = self.build_prompt(context)

    async for chunk in self._stream_api(prompt):
        yield chunk

async def _stream_api(self, prompt: str):
    """Stream response from API."""
    import httpx

    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            "https://api.myservice.com/stream",
            json={"prompt": prompt},
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    yield line[6:]
```

## Testing Your Executor

```python
# tests/test_my_executor.py
import pytest
from unittest.mock import Mock, patch

from my_executor import MyExecutor
from src.executors.base import ExecutorConfig, TaskContext


class TestMyExecutor:
    @pytest.fixture
    def executor(self):
        config = ExecutorConfig(
            extra={"api_key": "test-key", "model": "default-model"}
        )
        return MyExecutor(config)

    @pytest.fixture
    def context(self):
        return TaskContext(
            task_id="test-001",
            description="Test task",
            steps=["Step 1", "Step 2"],
            project_path="/path/to/project",
            prd_path="/path/to/prd.json",
        )

    def test_execute_success(self, executor, context):
        with patch.object(executor, "_call_api") as mock_api:
            mock_api.return_value = Mock(
                text="Generated code...",
                total_tokens=100,
                input_tokens=50,
                output_tokens=50,
            )

            result = executor._execute_impl(context)

            assert result.success
            assert "Generated code" in result.output

    def test_health_check(self, executor):
        with patch("httpx.get") as mock_get:
            mock_get.return_value = Mock(status_code=200)
            assert executor.health_check() is True

    def test_cost_estimation(self, executor):
        cost = executor.estimate_cost(1000, 500)
        assert cost > 0
        assert isinstance(cost, float)
```

## Best Practices

1. **Handle errors gracefully** - Return `ExecutionResult` with descriptive errors
2. **Implement health checks** - Enable monitoring and status reporting
3. **Support cost estimation** - Allow budget tracking
4. **Validate configuration** - Use `PluginConfigField` for schema validation
5. **Log appropriately** - Use the provided logger for debugging
6. **Test thoroughly** - Cover success, failure, and edge cases
7. **Document configuration** - Clear descriptions for all config fields

## Example: Claude API Executor

See the built-in Claude API executor for a complete reference implementation:

```
src/executors/claude_api_executor.py
```

Key patterns:
- Uses `anthropic` Python SDK
- Handles rate limiting with exponential backoff
- Tracks tokens for cost estimation
- Implements streaming support
