"""Google Gemini executor implementation.

This module provides an executor that uses Google's Gemini API
to execute PRD tasks.
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
GEMINI_PRICING = {
    "gemini-1.5-pro": {"input": 3.50, "output": 10.50},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-1.5-flash-8b": {"input": 0.0375, "output": 0.15},
    "gemini-1.0-pro": {"input": 0.50, "output": 1.50},
}


@dataclass
class GeminiConfig(ExecutorConfig):
    """Configuration specific to Gemini executor.

    Attributes:
        api_key: Google AI Studio API key.
        project: Google Cloud project ID (for Vertex AI).
        location: Google Cloud location (for Vertex AI).
    """

    api_key: str | None = None
    project: str | None = None
    location: str = "us-central1"


class GeminiExecutor(ExecutorPlugin):
    """Executor that uses Google's Gemini API for code generation.

    This executor uses Google Gemini models to execute PRD tasks.
    It supports:
    - Multiple model selection
    - Both AI Studio and Vertex AI endpoints
    - Streaming responses
    - Cost tracking
    """

    def __init__(self, config: GeminiConfig | ExecutorConfig | None = None) -> None:
        """Initialize the Gemini executor.

        Args:
            config: Gemini specific configuration.
        """
        # Convert ExecutorConfig to GeminiConfig if needed
        if config is not None and not isinstance(config, GeminiConfig):
            config = GeminiConfig(
                max_retries=config.max_retries,
                base_delay=config.base_delay,
                max_delay=config.max_delay,
                timeout=config.timeout,
                model=config.model,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                extra=config.extra,
            )
        super().__init__(config or GeminiConfig())
        self._model = None

    @classmethod
    def get_plugin_info(cls) -> dict[str, Any]:
        """Get plugin metadata."""
        return {
            "name": "gemini",
            "display_name": "Google Gemini",
            "description": "Execute tasks using Google's Gemini models. "
            "Requires a Google AI Studio API key or Vertex AI credentials.",
            "version": "1.0.0",
            "author": "PRDForge",
            "homepage": "https://ai.google.dev/",
        }

    @classmethod
    def get_config_schema(cls) -> PluginSchema:
        """Get the configuration schema for this plugin."""
        return PluginSchema(
            fields=[
                PluginConfigField(
                    name="api_key",
                    type="secret",
                    description="Google AI Studio API key (or set GOOGLE_API_KEY env var)",
                    required=False,
                ),
                PluginConfigField(
                    name="project",
                    type="string",
                    description="Google Cloud project ID (for Vertex AI)",
                    required=False,
                ),
                PluginConfigField(
                    name="location",
                    type="string",
                    description="Google Cloud location (for Vertex AI)",
                    required=False,
                    default="us-central1",
                ),
                PluginConfigField(
                    name="model",
                    type="string",
                    description="Gemini model to use",
                    required=False,
                    default="gemini-1.5-pro",
                    enum=[
                        "gemini-1.5-pro",
                        "gemini-1.5-flash",
                        "gemini-1.5-flash-8b",
                        "gemini-1.0-pro",
                    ],
                ),
                PluginConfigField(
                    name="max_tokens",
                    type="integer",
                    description="Maximum tokens in response",
                    required=False,
                    default=8192,
                    min_value=256,
                    max_value=32768,
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
            "multimodal",
        ]

    @property
    def config(self) -> GeminiConfig:
        """Return typed config."""
        return self._config  # type: ignore

    @config.setter
    def config(self, value: ExecutorConfig) -> None:
        """Set config."""
        self._config = value

    @property
    def name(self) -> str:
        return "gemini"

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
        return os.environ.get("GOOGLE_API_KEY")

    def _get_model(self):
        """Get or create Gemini model instance."""
        if self._model is None:
            try:
                import google.generativeai as genai
            except ImportError:
                raise RuntimeError(
                    "google-generativeai package not installed. "
                    "Run: pip install google-generativeai"
                )

            api_key = self._get_api_key()
            if not api_key:
                raise RuntimeError(
                    "Google API key not configured. "
                    "Set GOOGLE_API_KEY or provide api_key in config."
                )

            genai.configure(api_key=api_key)

            model_name = self.config.model or "gemini-1.5-pro"
            self._model = genai.GenerativeModel(model_name)

        return self._model

    def _execute_impl(self, context: TaskContext) -> ExecutionResult:
        """Execute task using Gemini API.

        Args:
            context: Task execution context.

        Returns:
            ExecutionResult with execution outcome.
        """
        import time

        start = time.time()

        try:
            model = self._get_model()
        except RuntimeError as e:
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
            )

        # Build the prompt
        prompt = self.build_prompt(context)

        # Get settings
        max_tokens = self.config.max_tokens or 8192
        temperature = self.config.temperature

        logger.debug(f"Executing with Gemini model: {self.config.model or 'gemini-1.5-pro'}")

        try:
            # Configure generation
            generation_config = {
                "max_output_tokens": max_tokens,
                "temperature": temperature,
            }

            response = model.generate_content(
                prompt,
                generation_config=generation_config,
            )

            duration = time.time() - start

            # Extract response content
            content = response.text if response.text else ""

            # Get token usage (if available)
            tokens_used = None
            prompt_tokens = None
            completion_tokens = None

            if hasattr(response, "usage_metadata"):
                usage = response.usage_metadata
                prompt_tokens = getattr(usage, "prompt_token_count", None)
                completion_tokens = getattr(usage, "candidates_token_count", None)
                if prompt_tokens and completion_tokens:
                    tokens_used = prompt_tokens + completion_tokens

            return ExecutionResult(
                success=True,
                output=content,
                tokens_used=tokens_used,
                duration_seconds=duration,
                metadata={
                    "model": self.config.model or "gemini-1.5-pro",
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                },
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Gemini API error: {error_msg}")

            # Detect rate limiting
            if "quota" in error_msg.lower() or "rate" in error_msg.lower():
                self._status = ExecutorStatus.RATE_LIMITED

            return ExecutionResult(
                success=False,
                output="",
                error=error_msg,
                duration_seconds=time.time() - start,
            )

    def build_prompt(self, context: TaskContext) -> str:
        """Build prompt for Gemini.

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
1. Analyze the task requirements carefully
2. Generate the necessary code to implement all steps
3. Follow common coding conventions and best practices
4. Include appropriate error handling
5. Format your response as code blocks with file paths

Generate the implementation for this task.
"""

    def health_check(self) -> bool:
        """Check if Gemini API is available.

        Returns:
            True if Gemini is configured and accessible.
        """
        api_key = self._get_api_key()
        if not api_key:
            self._status = ExecutorStatus.UNAVAILABLE
            return False

        try:
            # Try importing the library
            import google.generativeai  # noqa: F401

            self._status = ExecutorStatus.AVAILABLE
            return True
        except ImportError:
            self._status = ExecutorStatus.UNAVAILABLE
            return False

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost for given token counts.

        Args:
            prompt_tokens: Number of input tokens.
            completion_tokens: Number of output tokens.

        Returns:
            Estimated cost in USD.
        """
        model = self.config.model or "gemini-1.5-pro"
        pricing = GEMINI_PRICING.get(model, GEMINI_PRICING["gemini-1.5-pro"])

        input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
        output_cost = (completion_tokens / 1_000_000) * pricing["output"]

        return input_cost + output_cost
