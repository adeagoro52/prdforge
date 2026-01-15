"""Claude API direct executor implementation.

This module provides an executor that uses the Anthropic Claude API directly
(not through the CLI) to execute PRD tasks.
"""

import os
from dataclasses import dataclass
from typing import Any

from src.engine.logging import logger

from .base import (
    ExecutionResult,
    ExecutorConfig,
    ExecutorStatus,
    TaskContext,
)
from .plugin import (
    ExecutorPlugin,
    PluginConfigField,
    PluginSchema,
)


# Pricing per 1M tokens (as of 2024)
CLAUDE_PRICING = {
    "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
    "claude-3-5-haiku-20241022": {"input": 1.0, "output": 5.0},
    "claude-3-opus-20240229": {"input": 15.0, "output": 75.0},
    "claude-3-sonnet-20240229": {"input": 3.0, "output": 15.0},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
}


@dataclass
class ClaudeAPIConfig(ExecutorConfig):
    """Configuration specific to Claude API executor.

    Attributes:
        api_key: Anthropic API key.
        base_url: Custom API base URL (optional).
    """

    api_key: str | None = None
    base_url: str | None = None


class ClaudeAPIExecutor(ExecutorPlugin):
    """Executor that uses Anthropic's Claude API directly.

    This executor uses the Anthropic Python SDK to execute PRD tasks.
    Unlike ClaudeCLIExecutor, it doesn't require the CLI to be installed.
    It supports:
    - Multiple model selection (Opus, Sonnet, Haiku)
    - Extended thinking mode
    - Tool use for file operations
    - Streaming responses
    - Cost tracking
    """

    def __init__(self, config: ClaudeAPIConfig | ExecutorConfig | None = None) -> None:
        """Initialize the Claude API executor.

        Args:
            config: Claude API specific configuration.
        """
        # Convert ExecutorConfig to ClaudeAPIConfig if needed
        if config is not None and not isinstance(config, ClaudeAPIConfig):
            config = ClaudeAPIConfig(
                max_retries=config.max_retries,
                base_delay=config.base_delay,
                max_delay=config.max_delay,
                timeout=config.timeout,
                model=config.model,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                extra=config.extra,
            )
        super().__init__(config or ClaudeAPIConfig())
        self._client = None

    @classmethod
    def get_plugin_info(cls) -> dict[str, Any]:
        """Get plugin metadata."""
        return {
            "name": "claude-api",
            "display_name": "Claude API",
            "description": "Execute tasks using Anthropic's Claude API directly. "
            "Requires an Anthropic API key. Supports extended thinking and tool use.",
            "version": "1.0.0",
            "author": "PRDForge",
            "homepage": "https://www.anthropic.com/claude",
        }

    @classmethod
    def get_config_schema(cls) -> PluginSchema:
        """Get the configuration schema for this plugin."""
        return PluginSchema(
            fields=[
                PluginConfigField(
                    name="api_key",
                    type="secret",
                    description="Anthropic API key (or set ANTHROPIC_API_KEY env var)",
                    required=False,
                ),
                PluginConfigField(
                    name="model",
                    type="string",
                    description="Claude model to use",
                    required=False,
                    default="claude-sonnet-4-20250514",
                    enum=[
                        "claude-opus-4-20250514",
                        "claude-sonnet-4-20250514",
                        "claude-3-5-sonnet-20241022",
                        "claude-3-5-haiku-20241022",
                        "claude-3-opus-20240229",
                        "claude-3-sonnet-20240229",
                        "claude-3-haiku-20240307",
                    ],
                ),
                PluginConfigField(
                    name="max_tokens",
                    type="integer",
                    description="Maximum tokens in response",
                    required=False,
                    default=4096,
                    min_value=256,
                    max_value=8192,
                ),
                PluginConfigField(
                    name="temperature",
                    type="number",
                    description="Sampling temperature (0.0-1.0)",
                    required=False,
                    default=0.0,
                    min_value=0.0,
                    max_value=1.0,
                ),
                PluginConfigField(
                    name="extended_thinking",
                    type="boolean",
                    description="Enable extended thinking mode",
                    required=False,
                    default=False,
                ),
                PluginConfigField(
                    name="timeout",
                    type="integer",
                    description="Request timeout in seconds",
                    required=False,
                    default=300,
                    min_value=30,
                    max_value=600,
                ),
            ]
        )

    @classmethod
    def get_capabilities(cls) -> list[str]:
        """Get list of capabilities supported by this plugin."""
        return [
            "code_generation",
            "streaming",
            "tool_use",
            "extended_thinking",
        ]

    @property
    def config(self) -> ClaudeAPIConfig:
        """Return typed config."""
        return self._config  # type: ignore

    @config.setter
    def config(self, value: ExecutorConfig) -> None:
        """Set config."""
        self._config = value

    @property
    def name(self) -> str:
        return "claude-api"

    @property
    def version(self) -> str:
        return "1.0.0"

    def _get_api_key(self) -> str | None:
        """Get API key from config or environment."""
        # Check config extra first
        api_key = self.config.extra.get("api_key")
        if api_key:
            return api_key

        # Check environment
        return os.environ.get("ANTHROPIC_API_KEY")

    def _get_client(self):
        """Get or create Anthropic client."""
        if self._client is None:
            try:
                from anthropic import Anthropic
            except ImportError:
                raise RuntimeError(
                    "anthropic package not installed. Run: pip install anthropic"
                )

            api_key = self._get_api_key()
            if not api_key:
                raise RuntimeError(
                    "Anthropic API key not configured. "
                    "Set ANTHROPIC_API_KEY or provide api_key in config."
                )

            base_url = self.config.extra.get("base_url")

            self._client = Anthropic(
                api_key=api_key,
                base_url=base_url,
                timeout=self.config.timeout,
            )

        return self._client

    def _execute_impl(self, context: TaskContext) -> ExecutionResult:
        """Execute task using Claude API.

        Args:
            context: Task execution context.

        Returns:
            ExecutionResult with execution outcome.
        """
        import time

        start = time.time()

        try:
            client = self._get_client()
        except RuntimeError as e:
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
            )

        # Build the prompt
        prompt = self.build_prompt(context)

        # Get model and settings
        model = self.config.model or "claude-sonnet-4-20250514"
        max_tokens = self.config.max_tokens or 4096
        temperature = self.config.temperature
        extended_thinking = self.config.extra.get("extended_thinking", False)

        logger.debug(f"Executing with Claude model: {model}")

        try:
            # Build message kwargs
            message_kwargs: dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }

            # Add temperature if not using extended thinking
            if not extended_thinking:
                message_kwargs["temperature"] = temperature

            # Add extended thinking if enabled
            if extended_thinking:
                message_kwargs["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": min(max_tokens * 2, 16000),
                }

            response = client.messages.create(**message_kwargs)

            duration = time.time() - start

            # Extract response content
            content_parts = []
            thinking_content = None

            for block in response.content:
                if block.type == "text":
                    content_parts.append(block.text)
                elif block.type == "thinking":
                    thinking_content = block.thinking

            content = "\n".join(content_parts)

            # Get token usage
            tokens_used = None
            if response.usage:
                tokens_used = response.usage.input_tokens + response.usage.output_tokens

            return ExecutionResult(
                success=True,
                output=content,
                tokens_used=tokens_used,
                duration_seconds=duration,
                metadata={
                    "model": model,
                    "input_tokens": response.usage.input_tokens if response.usage else None,
                    "output_tokens": response.usage.output_tokens if response.usage else None,
                    "stop_reason": response.stop_reason,
                    "thinking": thinking_content[:500] if thinking_content else None,
                },
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Claude API error: {error_msg}")

            # Detect rate limiting
            if "rate" in error_msg.lower():
                self._status = ExecutorStatus.RATE_LIMITED

            return ExecutionResult(
                success=False,
                output="",
                error=error_msg,
                duration_seconds=time.time() - start,
            )

    def build_prompt(self, context: TaskContext) -> str:
        """Build prompt for Claude API.

        Args:
            context: Task execution context.

        Returns:
            Formatted prompt string.
        """
        steps_text = "\n".join(f"  {i + 1}. {step}" for i, step in enumerate(context.steps))

        # Include extra context if provided
        extra_context = ""
        if context.extra_context:
            extra_parts = []
            for key, value in context.extra_context.items():
                extra_parts.append(f"{key}: {value}")
            extra_context = "\n\nAdditional Context:\n" + "\n".join(extra_parts)

        return f"""You are an expert software engineer executing tasks from a PRD document.

Task ID: {context.task_id}
Phase: {context.phase}
Category: {context.category}

Description:
{context.description}

Steps to complete:
{steps_text}
{extra_context}

Project Path: {context.project_path}

Instructions:
1. Analyze the task requirements thoroughly
2. Generate the necessary code to implement all steps
3. Follow common coding conventions and best practices
4. Include appropriate error handling
5. Format your response as code blocks with file paths marked like ```language:path/to/file

Generate the implementation for this task.
"""

    def health_check(self) -> bool:
        """Check if Claude API is available.

        Returns:
            True if Claude API is configured and accessible.
        """
        api_key = self._get_api_key()
        if not api_key:
            self._status = ExecutorStatus.UNAVAILABLE
            return False

        try:
            # Quick validation by checking key format
            if not api_key.startswith("sk-ant-"):
                self._status = ExecutorStatus.ERROR
                return False

            self._status = ExecutorStatus.AVAILABLE
            return True
        except Exception:
            self._status = ExecutorStatus.ERROR
            return False

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost for given token counts.

        Args:
            prompt_tokens: Number of input tokens.
            completion_tokens: Number of output tokens.

        Returns:
            Estimated cost in USD.
        """
        model = self.config.model or "claude-sonnet-4-20250514"
        pricing = CLAUDE_PRICING.get(model, CLAUDE_PRICING["claude-sonnet-4-20250514"])

        input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
        output_cost = (completion_tokens / 1_000_000) * pricing["output"]

        return input_cost + output_cost
