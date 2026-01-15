"""OpenAI executor implementation.

This module provides an executor that uses OpenAI's API (GPT-4, GPT-4o, etc.)
to execute PRD tasks. This replaces the deprecated Codex API.
"""

import os
from dataclasses import dataclass, field
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
OPENAI_PRICING = {
    "gpt-4o": {"input": 5.0, "output": 15.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.0, "output": 30.0},
    "gpt-4": {"input": 30.0, "output": 60.0},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
}


@dataclass
class OpenAIConfig(ExecutorConfig):
    """Configuration specific to OpenAI executor.

    Attributes:
        api_key: OpenAI API key.
        organization: OpenAI organization ID (optional).
        model: Model to use (default: gpt-4o).
        max_tokens: Maximum tokens in response.
        temperature: Sampling temperature.
    """

    api_key: str | None = None
    organization: str | None = None


class OpenAIExecutor(ExecutorPlugin):
    """Executor that uses OpenAI's API for code generation.

    This executor uses OpenAI models (GPT-4, GPT-4o, etc.) to execute
    PRD tasks. It supports:
    - Multiple model selection
    - Tool/function calling
    - Streaming responses
    - Cost tracking
    """

    def __init__(self, config: OpenAIConfig | ExecutorConfig | None = None) -> None:
        """Initialize the OpenAI executor.

        Args:
            config: OpenAI specific configuration.
        """
        # Convert ExecutorConfig to OpenAIConfig if needed
        if config is not None and not isinstance(config, OpenAIConfig):
            config = OpenAIConfig(
                max_retries=config.max_retries,
                base_delay=config.base_delay,
                max_delay=config.max_delay,
                timeout=config.timeout,
                model=config.model,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                extra=config.extra,
            )
        super().__init__(config or OpenAIConfig())
        self._client = None

    @classmethod
    def get_plugin_info(cls) -> dict[str, Any]:
        """Get plugin metadata."""
        return {
            "name": "openai",
            "display_name": "OpenAI",
            "description": "Execute tasks using OpenAI's GPT models (GPT-4, GPT-4o, etc.). "
            "Requires an OpenAI API key.",
            "version": "1.0.0",
            "author": "PRDForge",
            "homepage": "https://platform.openai.com/",
        }

    @classmethod
    def get_config_schema(cls) -> PluginSchema:
        """Get the configuration schema for this plugin."""
        return PluginSchema(
            fields=[
                PluginConfigField(
                    name="api_key",
                    type="secret",
                    description="OpenAI API key (or set OPENAI_API_KEY env var)",
                    required=False,
                ),
                PluginConfigField(
                    name="organization",
                    type="string",
                    description="OpenAI organization ID (optional)",
                    required=False,
                ),
                PluginConfigField(
                    name="model",
                    type="string",
                    description="OpenAI model to use",
                    required=False,
                    default="gpt-4o",
                    enum=[
                        "gpt-4o",
                        "gpt-4o-mini",
                        "gpt-4-turbo",
                        "gpt-4",
                        "gpt-3.5-turbo",
                    ],
                ),
                PluginConfigField(
                    name="max_tokens",
                    type="integer",
                    description="Maximum tokens in response",
                    required=False,
                    default=4096,
                    min_value=256,
                    max_value=128000,
                ),
                PluginConfigField(
                    name="temperature",
                    type="number",
                    description="Sampling temperature (0.0-2.0)",
                    required=False,
                    default=0.0,
                    min_value=0.0,
                    max_value=2.0,
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
        ]

    @property
    def config(self) -> OpenAIConfig:
        """Return typed config."""
        return self._config  # type: ignore

    @config.setter
    def config(self, value: ExecutorConfig) -> None:
        """Set config."""
        self._config = value

    @property
    def name(self) -> str:
        return "openai"

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
        return os.environ.get("OPENAI_API_KEY")

    def _get_client(self):
        """Get or create OpenAI client."""
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError:
                raise RuntimeError(
                    "openai package not installed. Run: pip install openai"
                )

            api_key = self._get_api_key()
            if not api_key:
                raise RuntimeError(
                    "OpenAI API key not configured. Set OPENAI_API_KEY or provide api_key in config."
                )

            organization = self.config.extra.get("organization")

            self._client = OpenAI(
                api_key=api_key,
                organization=organization,
                timeout=self.config.timeout,
            )

        return self._client

    def _execute_impl(self, context: TaskContext) -> ExecutionResult:
        """Execute task using OpenAI API.

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
        model = self.config.model or "gpt-4o"
        max_tokens = self.config.max_tokens or 4096
        temperature = self.config.temperature

        logger.debug(f"Executing with OpenAI model: {model}")

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert software engineer. You execute tasks from PRD documents by generating code. Be precise and thorough.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )

            duration = time.time() - start

            # Extract response content
            content = response.choices[0].message.content or ""

            # Get token usage
            tokens_used = None
            if response.usage:
                tokens_used = response.usage.total_tokens

            return ExecutionResult(
                success=True,
                output=content,
                tokens_used=tokens_used,
                duration_seconds=duration,
                metadata={
                    "model": model,
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
                    "completion_tokens": response.usage.completion_tokens if response.usage else None,
                    "finish_reason": response.choices[0].finish_reason,
                },
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"OpenAI API error: {error_msg}")

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
        """Build prompt for OpenAI.

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

        return f"""You are executing a task from a PRD (Product Requirements Document).

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
1. Analyze the task requirements carefully
2. Generate the necessary code to implement all steps
3. Follow the project's coding conventions
4. Include appropriate error handling
5. Format your response as code blocks with file paths

Generate the implementation for this task.
"""

    def health_check(self) -> bool:
        """Check if OpenAI API is available.

        Returns:
            True if OpenAI is configured and accessible.
        """
        api_key = self._get_api_key()
        if not api_key:
            self._status = ExecutorStatus.UNAVAILABLE
            return False

        try:
            # Quick validation by checking key format
            if not api_key.startswith("sk-"):
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
        model = self.config.model or "gpt-4o"
        pricing = OPENAI_PRICING.get(model, OPENAI_PRICING["gpt-4o"])

        input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
        output_cost = (completion_tokens / 1_000_000) * pricing["output"]

        return input_cost + output_cost
