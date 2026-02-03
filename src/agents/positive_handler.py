"""Positive feedback handler agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .base_agent import BaseAgent
from ..llm.prompts import POSITIVE_HANDLER_SYSTEM_PROMPT
from ..services.policy_service import Policy
from ..utils.enums import AuditAction, TicketPriority


@dataclass
class HandlerResponse:
    """Response from a handler agent."""

    response: str
    priority: TicketPriority
    requires_escalation: bool = False
    escalation_reason: str | None = None
    cited_policies: List[Policy] = field(default_factory=list)


class PositiveHandler(BaseAgent):
    """Agent that handles positive customer feedback."""

    @property
    def name(self) -> str:
        """Get the agent name."""
        return "positive_handler"

    @property
    def system_prompt(self) -> str:
        """Get the system prompt."""
        return POSITIVE_HANDLER_SYSTEM_PROMPT

    async def process(self, ticket_id: str, message: str) -> HandlerResponse:
        """Generate a response to positive feedback.

        Args:
            ticket_id: Associated ticket ID
            message: Customer message

        Returns:
            HandlerResponse with the generated response
        """
        self.logger.info(
            "handling_positive_feedback",
            ticket_id=ticket_id,
        )

        response = await self.call_llm(
            ticket_id=ticket_id,
            user_message=message,
            action=AuditAction.RESPOND,
            max_tokens=512,
            temperature=0.7,
        )

        self.logger.info(
            "positive_response_generated",
            ticket_id=ticket_id,
            response_length=len(response.content),
        )

        return HandlerResponse(
            response=response.content,
            priority=TicketPriority.MINIMAL,  # Priority 5 for positive feedback
            requires_escalation=False,
        )
