"""Negative feedback/complaint handler agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .base_agent import BaseAgent
from ..llm.prompts import NEGATIVE_HANDLER_SYSTEM_PROMPT
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


class NegativeHandler(BaseAgent):
    """Agent that handles customer complaints and negative feedback."""

    # Keywords that indicate escalation may be needed
    ESCALATION_KEYWORDS = [
        "fraud",
        "unauthorized",
        "stolen",
        "lawsuit",
        "lawyer",
        "attorney",
        "legal",
        "sue",
        "compensation",
        "report",
        "authorities",
        "police",
        "security breach",
        "identity theft",
    ]

    @property
    def name(self) -> str:
        """Get the agent name."""
        return "negative_handler"

    @property
    def system_prompt(self) -> str:
        """Get the system prompt."""
        return NEGATIVE_HANDLER_SYSTEM_PROMPT

    async def process(self, ticket_id: str, message: str) -> HandlerResponse:
        """Generate a response to complaints/negative feedback.

        Args:
            ticket_id: Associated ticket ID
            message: Customer message

        Returns:
            HandlerResponse with the generated response
        """
        self.logger.info(
            "handling_complaint",
            ticket_id=ticket_id,
        )

        # Check for escalation triggers
        escalation_needed, escalation_reason = self._check_escalation(message)

        # Determine priority based on message content
        priority = self._determine_priority(message, escalation_needed)

        # Search for relevant policies
        policy_service = get_policy_service()
        relevant_policies = policy_service.search_policies(message)

        # Build enhanced message with policy context
        policy_context = policy_service.format_policies_for_prompt(relevant_policies)
        if policy_context:
            enhanced_message = f"{message}\n\n{policy_context}"
        else:
            enhanced_message = message

        response = await self.call_llm(
            ticket_id=ticket_id,
            user_message=enhanced_message,
            action=AuditAction.RESPOND,
            max_tokens=768,  # Slightly more tokens for empathetic responses
            temperature=0.6,  # Slightly lower for more consistent tone
        )

        self.logger.info(
            "complaint_response_generated",
            ticket_id=ticket_id,
            response_length=len(response.content),
            priority=priority.value,
            escalation_needed=escalation_needed,
            policies_cited=len(relevant_policies),
        )

        return HandlerResponse(
            response=response.content,
            priority=priority,
            requires_escalation=escalation_needed,
            escalation_reason=escalation_reason,
            cited_policies=relevant_policies,
        )

    def _check_escalation(self, message: str) -> tuple[bool, str | None]:
        """Check if the message requires escalation.

        Args:
            message: Customer message

        Returns:
            Tuple of (needs_escalation, reason)
        """
        message_lower = message.lower()

        for keyword in self.ESCALATION_KEYWORDS:
            if keyword in message_lower:
                return True, f"Message contains escalation trigger: '{keyword}'"

        return False, None

    def _determine_priority(self, message: str, escalation_needed: bool) -> TicketPriority:
        """Determine the priority based on message content.

        Args:
            message: Customer message
            escalation_needed: Whether escalation is needed

        Returns:
            Appropriate TicketPriority
        """
        if escalation_needed:
            return TicketPriority.CRITICAL  # Priority 1

        message_lower = message.lower()

        # High priority indicators
        high_priority_keywords = [
            "urgent",
            "immediately",
            "asap",
            "emergency",
            "cannot access",
            "locked out",
            "missing money",
            "large amount",
        ]

        for keyword in high_priority_keywords:
            if keyword in message_lower:
                return TicketPriority.HIGH  # Priority 2

        # Default to high-medium priority for complaints
        return TicketPriority.HIGH  # Priority 2 for most complaints
