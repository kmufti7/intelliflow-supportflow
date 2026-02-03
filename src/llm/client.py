"""Unified LLM client for OpenAI and Anthropic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI
from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import Settings, get_settings
from ..utils.enums import LLMProvider
from ..utils.exceptions import LLMError
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class LLMResponse:
    """Response from an LLM call."""

    content: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0
    finish_reason: str | None = None
    raw_response: Any = None


class LLMClient:
    """Unified client for OpenAI and Anthropic APIs."""

    def __init__(self, settings: Settings | None = None):
        """Initialize the LLM client.

        Args:
            settings: Application settings
        """
        self.settings = settings or get_settings()
        self._openai_client: AsyncOpenAI | None = None
        self._anthropic_client: AsyncAnthropic | None = None

    @property
    def openai_client(self) -> AsyncOpenAI:
        """Get or create the OpenAI client."""
        if self._openai_client is None:
            if not self.settings.openai_api_key:
                raise LLMError(
                    "OpenAI API key not configured",
                    provider="openai",
                )
            self._openai_client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        return self._openai_client

    @property
    def anthropic_client(self) -> AsyncAnthropic:
        """Get or create the Anthropic client."""
        if self._anthropic_client is None:
            if not self.settings.anthropic_api_key:
                raise LLMError(
                    "Anthropic API key not configured",
                    provider="anthropic",
                )
            self._anthropic_client = AsyncAnthropic(api_key=self.settings.anthropic_api_key)
        return self._anthropic_client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        model: str | None = None,
        provider: LLMProvider | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Send a completion request to the LLM.

        Args:
            system_prompt: System prompt for the model
            user_message: User message to process
            model: Model name (optional, uses settings default)
            provider: LLM provider (optional, uses settings default)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature

        Returns:
            LLMResponse with content and usage data
        """
        provider = provider or self.settings.llm_provider
        model = model or self.settings.active_model

        logger.debug(
            "llm_request",
            provider=provider.value,
            model=model,
            user_message_length=len(user_message),
        )

        try:
            if provider == LLMProvider.OPENAI:
                return await self._complete_openai(
                    system_prompt=system_prompt,
                    user_message=user_message,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            else:
                return await self._complete_anthropic(
                    system_prompt=system_prompt,
                    user_message=user_message,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )

        except LLMError:
            raise
        except Exception as e:
            logger.error(
                "llm_request_failed",
                provider=provider.value,
                model=model,
                error=str(e),
            )
            raise LLMError(
                f"LLM request failed: {e}",
                provider=provider.value,
                model=model,
            )

    async def _complete_openai(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        """Send completion request to OpenAI.

        Args:
            system_prompt: System prompt
            user_message: User message
            model: Model name
            max_tokens: Max tokens
            temperature: Temperature

        Returns:
            LLMResponse
        """
        response = await self.openai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )

        content = response.choices[0].message.content or ""
        usage = response.usage

        logger.debug(
            "llm_response",
            provider="openai",
            model=model,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )

        # Extract cached tokens if available
        cached_tokens = 0
        if usage and hasattr(usage, "prompt_tokens_details") and usage.prompt_tokens_details:
            cached_tokens = getattr(usage.prompt_tokens_details, "cached_tokens", 0) or 0

        return LLMResponse(
            content=content,
            model=model,
            provider="openai",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            cached_tokens=cached_tokens,
            finish_reason=response.choices[0].finish_reason,
            raw_response=response,
        )

    async def _complete_anthropic(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        """Send completion request to Anthropic.

        Args:
            system_prompt: System prompt
            user_message: User message
            model: Model name
            max_tokens: Max tokens
            temperature: Temperature

        Returns:
            LLMResponse
        """
        response = await self.anthropic_client.messages.create(
            model=model,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_message},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )

        content = response.content[0].text if response.content else ""
        usage = response.usage

        # Get cached tokens from usage if available
        cached_tokens = 0
        if hasattr(usage, "cache_read_input_tokens"):
            cached_tokens = usage.cache_read_input_tokens

        logger.debug(
            "llm_response",
            provider="anthropic",
            model=model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )

        return LLMResponse(
            content=content,
            model=model,
            provider="anthropic",
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached_tokens=cached_tokens,
            finish_reason=response.stop_reason,
            raw_response=response,
        )

    async def close(self) -> None:
        """Close the client connections."""
        if self._openai_client:
            await self._openai_client.close()
            self._openai_client = None

        if self._anthropic_client:
            await self._anthropic_client.close()
            self._anthropic_client = None


# Global client instance
_llm_client: LLMClient | None = None


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    """Get or create the global LLM client.

    Args:
        settings: Optional settings instance

    Returns:
        LLM client instance
    """
    global _llm_client

    if _llm_client is None:
        _llm_client = LLMClient(settings)

    return _llm_client


async def close_llm_client() -> None:
    """Close the global LLM client."""
    global _llm_client

    if _llm_client:
        await _llm_client.close()
        _llm_client = None
