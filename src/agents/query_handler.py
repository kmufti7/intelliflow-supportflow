"""Query handler agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .base_agent import BaseAgent
from ..db.repositories.ticket_repository import TicketRepository
from ..db.models import Ticket
from ..llm.prompts import QUERY_HANDLER_SYSTEM_PROMPT
from ..services.policy_service import Policy, get_policy_service
from ..utils.enums import AuditAction, TicketPriority


@dataclass
class HandlerResponse:
    """Response from a handler agent."""

    response: str
    priority: TicketPriority
    requires_escalation: bool = False
    escalation_reason: str | None = None
    cited_policies: List[Policy] = field(default_factory=list)


class QueryHandler(BaseAgent):
    """Agent that handles customer queries and questions."""

    def __init__(self, *args, **kwargs):
        """Initialize the query handler."""
        super().__init__(*args, **kwargs)
        self.ticket_repo = TicketRepository(self.db)

    @property
    def name(self) -> str:
        """Get the agent name."""
        return "query_handler"

    @property
    def system_prompt(self) -> str:
        """Get the system prompt."""
        return QUERY_HANDLER_SYSTEM_PROMPT

    async def _get_customer_context(self, ticket: Ticket) -> str:
        """Build context from customer's ticket history.

        Args:
            ticket: Current ticket

        Returns:
            Formatted context string for the LLM
        """
        # Get previous tickets for this customer
        previous_tickets: List[Ticket] = await self.ticket_repo.get_by_customer(
            ticket.customer_id
        )

        # Filter out current ticket and limit to recent history
        history = [t for t in previous_tickets if t.id != ticket.id][:5]

        if not history:
            return ""

        context_lines = ["[Previous interactions with this customer:]"]
        for prev_ticket in history:
            category = prev_ticket.category.value if prev_ticket.category else "unknown"
            status = prev_ticket.status.value if prev_ticket.status else "unknown"
            context_lines.append(
                f"- [{category.upper()}] {prev_ticket.customer_message[:100]}..."
                f" (Status: {status})"
            )

        return "\n".join(context_lines)

    async def process(self, ticket_id: str, message: str) -> HandlerResponse:
        """Generate a response to a customer query.

        Args:
            ticket_id: Associated ticket ID
            message: Customer message

        Returns:
            HandlerResponse with the generated response
        """
        self.logger.info(
            "handling_query",
            ticket_id=ticket_id,
        )

        # Look up the ticket from the database
        ticket = await self.ticket_repo.get_by_id(ticket_id)

        self.logger.debug(
            "ticket_retrieved",
            ticket_id=ticket_id,
            customer_id=ticket.customer_id,
            category=ticket.category.value if ticket.category else None,
        )

        # Determine priority based on query type
        priority = self._determine_priority(message)

        # Build context from customer history
        customer_context = await self._get_customer_context(ticket)

        # Search for relevant policies
        policy_service = get_policy_service()
        relevant_policies = policy_service.search_policies(message)
        policy_context = policy_service.format_policies_for_prompt(relevant_policies)

        # Build enhanced message with context
        context_parts = []
        if customer_context:
            context_parts.append(customer_context)
            self.logger.info(
                "using_customer_context",
                ticket_id=ticket_id,
                context_length=len(customer_context),
            )
        if policy_context:
            context_parts.append(policy_context)

        if context_parts:
            enhanced_message = "\n\n".join(context_parts) + f"\n\n[Current query:]\n{message}"
        else:
            enhanced_message = message

        response = await self.call_llm(
            ticket_id=ticket_id,
            user_message=enhanced_message,
            action=AuditAction.RESPOND,
            max_tokens=512,
            temperature=0.7,
        )

        self.logger.info(
            "query_response_generated",
            ticket_id=ticket_id,
            response_length=len(response.content),
            priority=priority.value,
            policies_cited=len(relevant_policies),
        )

        return HandlerResponse(
            response=response.content,
            priority=priority,
            requires_escalation=False,
            cited_policies=relevant_policies,
        )

    def _determine_priority(self, message: str) -> TicketPriority:
        """Determine the priority based on query content.

        Args:
            message: Customer message

        Returns:
            Appropriate TicketPriority
        """
        message_lower = message.lower()

        # Higher priority queries
        higher_priority_keywords = [
            "how do i transfer",
            "wire transfer",
            "international",
            "investment",
            "mortgage",
            "loan application",
            "account opening",
        ]

        for keyword in higher_priority_keywords:
            if keyword in message_lower:
                return TicketPriority.MEDIUM  # Priority 3

        # Default to low priority for simple informational queries
        return TicketPriority.LOW  # Priority 4
