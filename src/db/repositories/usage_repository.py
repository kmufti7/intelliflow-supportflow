"""Repository for token usage CRUD operations."""

from __future__ import annotations

from typing import List

from ..connection import DatabaseConnection
from ..models import TokenUsage, ModelPricing
from ...utils.exceptions import DatabaseError
from ...utils.logger import get_logger

logger = get_logger(__name__)


class UsageRepository:
    """Repository for token usage database operations."""

    def __init__(self, db: DatabaseConnection):
        """Initialize the repository.

        Args:
            db: Database connection instance
        """
        self.db = db

    async def create(self, usage: TokenUsage) -> TokenUsage:
        """Create a new token usage record.

        Args:
            usage: Token usage to create

        Returns:
            The created token usage
        """
        data = usage.to_dict()

        try:
            await self.db.execute(
                """
                INSERT INTO token_usage
                (id, ticket_id, agent_name, model_name, provider,
                 input_tokens, output_tokens, input_cost_usd, output_cost_usd,
                 cached_tokens, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["id"],
                    data["ticket_id"],
                    data["agent_name"],
                    data["model_name"],
                    data["provider"],
                    data["input_tokens"],
                    data["output_tokens"],
                    data["input_cost_usd"],
                    data["output_cost_usd"],
                    data["cached_tokens"],
                    data["created_at"],
                ),
            )

            logger.debug(
                "token_usage_created",
                usage_id=usage.id,
                ticket_id=usage.ticket_id,
                total_tokens=usage.total_tokens,
            )
            return usage

        except Exception as e:
            raise DatabaseError(f"Failed to create token usage: {e}", operation="create")

    async def get_by_ticket(self, ticket_id: str) -> List[TokenUsage]:
        """Get all token usage records for a ticket.

        Args:
            ticket_id: Ticket ID

        Returns:
            List of token usage records
        """
        rows = await self.db.fetch_all(
            "SELECT * FROM token_usage WHERE ticket_id = ? ORDER BY created_at ASC",
            (ticket_id,),
        )

        return [TokenUsage.from_dict(dict(row)) for row in rows]

    async def get_by_agent(self, agent_name: str, limit: int = 100) -> List[TokenUsage]:
        """Get token usage records for a specific agent.

        Args:
            agent_name: Name of the agent
            limit: Maximum number of records to return

        Returns:
            List of token usage records
        """
        rows = await self.db.fetch_all(
            """
            SELECT * FROM token_usage
            WHERE agent_name = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (agent_name, limit),
        )

        return [TokenUsage.from_dict(dict(row)) for row in rows]

    async def get_total_cost_by_ticket(self, ticket_id: str) -> float:
        """Get total cost for a ticket.

        Args:
            ticket_id: Ticket ID

        Returns:
            Total cost in USD
        """
        row = await self.db.fetch_one(
            """
            SELECT SUM(input_cost_usd + output_cost_usd) as total_cost
            FROM token_usage
            WHERE ticket_id = ?
            """,
            (ticket_id,),
        )

        return row["total_cost"] if row and row["total_cost"] else 0.0

    async def get_total_tokens_by_agent(self) -> dict[str, dict[str, int]]:
        """Get total tokens by agent.

        Returns:
            Dictionary of agent name to token counts
        """
        rows = await self.db.fetch_all(
            """
            SELECT agent_name,
                   SUM(input_tokens) as input_tokens,
                   SUM(output_tokens) as output_tokens
            FROM token_usage
            GROUP BY agent_name
            """
        )

        return {
            row["agent_name"]: {
                "input_tokens": row["input_tokens"],
                "output_tokens": row["output_tokens"],
                "total_tokens": row["input_tokens"] + row["output_tokens"],
            }
            for row in rows
        }

    async def get_total_cost_by_agent(self) -> dict[str, float]:
        """Get total cost by agent.

        Returns:
            Dictionary of agent name to total cost in USD
        """
        rows = await self.db.fetch_all(
            """
            SELECT agent_name,
                   SUM(input_cost_usd + output_cost_usd) as total_cost
            FROM token_usage
            GROUP BY agent_name
            """
        )

        return {row["agent_name"]: row["total_cost"] for row in rows}

    async def get_total_cost_by_model(self) -> dict[str, float]:
        """Get total cost by model.

        Returns:
            Dictionary of model name to total cost in USD
        """
        rows = await self.db.fetch_all(
            """
            SELECT model_name,
                   SUM(input_cost_usd + output_cost_usd) as total_cost
            FROM token_usage
            GROUP BY model_name
            """
        )

        return {row["model_name"]: row["total_cost"] for row in rows}

    async def get_summary(self) -> dict:
        """Get overall usage summary.

        Returns:
            Summary statistics
        """
        row = await self.db.fetch_one(
            """
            SELECT
                COUNT(*) as total_requests,
                SUM(input_tokens) as total_input_tokens,
                SUM(output_tokens) as total_output_tokens,
                SUM(input_cost_usd) as total_input_cost,
                SUM(output_cost_usd) as total_output_cost,
                SUM(cached_tokens) as total_cached_tokens
            FROM token_usage
            """
        )

        if not row:
            return {
                "total_requests": 0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_tokens": 0,
                "total_input_cost_usd": 0.0,
                "total_output_cost_usd": 0.0,
                "total_cost_usd": 0.0,
                "total_cached_tokens": 0,
            }

        return {
            "total_requests": row["total_requests"] or 0,
            "total_input_tokens": row["total_input_tokens"] or 0,
            "total_output_tokens": row["total_output_tokens"] or 0,
            "total_tokens": (row["total_input_tokens"] or 0) + (row["total_output_tokens"] or 0),
            "total_input_cost_usd": row["total_input_cost"] or 0.0,
            "total_output_cost_usd": row["total_output_cost"] or 0.0,
            "total_cost_usd": (row["total_input_cost"] or 0.0) + (row["total_output_cost"] or 0.0),
            "total_cached_tokens": row["total_cached_tokens"] or 0,
        }

    # Model pricing methods

    async def get_model_pricing(self, model_name: str) -> ModelPricing | None:
        """Get pricing for a model.

        Args:
            model_name: Name of the model

        Returns:
            Model pricing or None if not found
        """
        row = await self.db.fetch_one(
            "SELECT * FROM model_pricing WHERE model_name = ?",
            (model_name,),
        )

        if not row:
            return None

        return ModelPricing.from_dict(dict(row))

    async def upsert_model_pricing(self, pricing: ModelPricing) -> ModelPricing:
        """Insert or update model pricing.

        Args:
            pricing: Model pricing to upsert

        Returns:
            The upserted model pricing
        """
        data = pricing.to_dict()

        await self.db.execute(
            """
            INSERT OR REPLACE INTO model_pricing
            (model_name, provider, input_cost_per_1k, output_cost_per_1k,
             cached_input_cost_per_1k, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                data["model_name"],
                data["provider"],
                data["input_cost_per_1k"],
                data["output_cost_per_1k"],
                data["cached_input_cost_per_1k"],
                data["updated_at"],
            ),
        )

        return pricing

    async def get_all_model_pricing(self) -> List[ModelPricing]:
        """Get all model pricing records.

        Returns:
            List of model pricing records
        """
        rows = await self.db.fetch_all(
            "SELECT * FROM model_pricing ORDER BY provider, model_name"
        )

        return [ModelPricing.from_dict(dict(row)) for row in rows]
