"""Token usage and cost tracking."""

from __future__ import annotations

from ..db.models import TokenUsage, ModelPricing
from ..db.connection import DatabaseConnection
from ..db.repositories.usage_repository import UsageRepository
from ..utils.logger import get_logger
from .client import LLMResponse

logger = get_logger(__name__)


class TokenTracker:
    """Tracks token usage and calculates costs."""

    def __init__(self, db: DatabaseConnection):
        """Initialize the token tracker.

        Args:
            db: Database connection
        """
        self.usage_repo = UsageRepository(db)
        self._pricing_cache: dict[str, ModelPricing] = {}

    async def track_usage(
        self,
        ticket_id: str,
        agent_name: str,
        response: LLMResponse,
    ) -> TokenUsage:
        """Track token usage from an LLM response.

        Args:
            ticket_id: Associated ticket ID
            agent_name: Name of the agent making the request
            response: LLM response with usage data

        Returns:
            Created TokenUsage record
        """
        # Get pricing for the model
        pricing = await self._get_pricing(response.model)

        # Calculate costs
        input_cost = 0.0
        output_cost = 0.0

        if pricing:
            # Calculate input cost (considering cached tokens)
            regular_input_tokens = response.input_tokens - response.cached_tokens
            cached_input_cost = (response.cached_tokens / 1000) * pricing.cached_input_cost_per_1k
            regular_input_cost = (regular_input_tokens / 1000) * pricing.input_cost_per_1k
            input_cost = regular_input_cost + cached_input_cost

            # Calculate output cost
            output_cost = (response.output_tokens / 1000) * pricing.output_cost_per_1k

        # Create usage record
        usage = TokenUsage(
            ticket_id=ticket_id,
            agent_name=agent_name,
            model_name=response.model,
            provider=response.provider,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            input_cost_usd=input_cost,
            output_cost_usd=output_cost,
            cached_tokens=response.cached_tokens,
        )

        # Save to database
        await self.usage_repo.create(usage)

        logger.info(
            "token_usage_tracked",
            ticket_id=ticket_id,
            agent_name=agent_name,
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            total_cost_usd=usage.total_cost_usd,
        )

        return usage

    async def _get_pricing(self, model_name: str) -> ModelPricing | None:
        """Get pricing for a model, using cache.

        Args:
            model_name: Name of the model

        Returns:
            Model pricing or None if not found
        """
        if model_name not in self._pricing_cache:
            pricing = await self.usage_repo.get_model_pricing(model_name)
            if pricing:
                self._pricing_cache[model_name] = pricing

        return self._pricing_cache.get(model_name)

    async def get_ticket_cost(self, ticket_id: str) -> float:
        """Get total cost for a ticket.

        Args:
            ticket_id: Ticket ID

        Returns:
            Total cost in USD
        """
        return await self.usage_repo.get_total_cost_by_ticket(ticket_id)

    async def get_ticket_usage(self, ticket_id: str) -> list[TokenUsage]:
        """Get all usage records for a ticket.

        Args:
            ticket_id: Ticket ID

        Returns:
            List of token usage records
        """
        return await self.usage_repo.get_by_ticket(ticket_id)

    async def get_summary(self) -> dict:
        """Get overall usage summary.

        Returns:
            Usage summary statistics
        """
        return await self.usage_repo.get_summary()

    async def get_cost_by_agent(self) -> dict[str, float]:
        """Get total cost breakdown by agent.

        Returns:
            Dictionary of agent name to total cost
        """
        return await self.usage_repo.get_total_cost_by_agent()

    async def get_cost_by_model(self) -> dict[str, float]:
        """Get total cost breakdown by model.

        Returns:
            Dictionary of model name to total cost
        """
        return await self.usage_repo.get_total_cost_by_model()

    async def get_tokens_by_agent(self) -> dict[str, dict[str, int]]:
        """Get token usage breakdown by agent.

        Returns:
            Dictionary of agent name to token counts
        """
        return await self.usage_repo.get_total_tokens_by_agent()

    def clear_pricing_cache(self) -> None:
        """Clear the pricing cache."""
        self._pricing_cache.clear()
