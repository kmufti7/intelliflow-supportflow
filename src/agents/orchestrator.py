"""Main orchestrator that coordinates all agents."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, List

from ..db.connection import DatabaseConnection
from ..db.models import Ticket
from ..llm.client import LLMClient
from ..llm.token_tracker import TokenTracker
from ..services.ticket_service import TicketService
from ..services.audit_service import AuditService
from ..services.policy_service import Policy
from ..utils.enums import MessageCategory, AuditAction, TicketStatus
from ..utils.exceptions import ChaosError
from ..utils.logger import get_logger

from .classifier_agent import ClassifierAgent, ClassificationResult
from .positive_handler import PositiveHandler
from .negative_handler import NegativeHandler
from .query_handler import QueryHandler

logger = get_logger(__name__)


@dataclass
class ProcessingResult:
    """Result of processing a customer message."""

    ticket: Ticket
    classification: ClassificationResult
    response: str
    handler_used: str
    requires_escalation: bool = False
    escalation_reason: str | None = None
    cited_policies: List[Policy] = field(default_factory=list)


class Orchestrator:
    """Main orchestrator that coordinates the agent workflow."""

    def __init__(
        self,
        db: DatabaseConnection,
        llm_client: LLMClient,
    ):
        """Initialize the orchestrator.

        Args:
            db: Database connection
            llm_client: LLM client
        """
        self.db = db
        self.llm_client = llm_client
        self.token_tracker = TokenTracker(db)
        self.audit_service = AuditService(db)
        self.ticket_service = TicketService(db)

        # Initialize agents
        self.classifier = ClassifierAgent(
            db=db,
            llm_client=llm_client,
            token_tracker=self.token_tracker,
            audit_service=self.audit_service,
        )

        self.handlers: dict[MessageCategory, Any] = {
            MessageCategory.POSITIVE: PositiveHandler(
                db=db,
                llm_client=llm_client,
                token_tracker=self.token_tracker,
                audit_service=self.audit_service,
            ),
            MessageCategory.NEGATIVE: NegativeHandler(
                db=db,
                llm_client=llm_client,
                token_tracker=self.token_tracker,
                audit_service=self.audit_service,
            ),
            MessageCategory.QUERY: QueryHandler(
                db=db,
                llm_client=llm_client,
                token_tracker=self.token_tracker,
                audit_service=self.audit_service,
            ),
        }

        logger.info("orchestrator_initialized")

    def _maybe_trigger_chaos(self, component: str, chaos_mode: bool) -> None:
        """Possibly trigger a chaos failure.

        Args:
            component: Name of the component that might fail
            chaos_mode: Whether chaos mode is enabled

        Raises:
            ChaosError: If chaos mode triggers a failure (30% chance)
        """
        if chaos_mode and random.random() < 0.3:
            failure_messages = [
                "Simulated network timeout",
                "Service temporarily unavailable",
                "Database connection dropped",
                "Rate limit exceeded",
                "Internal processing error",
            ]
            raise ChaosError(component, random.choice(failure_messages))

    async def process_message(
        self,
        customer_id: str,
        message: str,
        chaos_mode: bool = False,
    ) -> ProcessingResult:
        """Process a customer message through the complete workflow.

        Args:
            customer_id: Customer identifier
            message: Customer message
            chaos_mode: If True, randomly inject failures for testing

        Returns:
            ProcessingResult with ticket and response details
        """
        logger.info(
            "processing_message",
            customer_id=customer_id,
            message_length=len(message),
            chaos_mode=chaos_mode,
        )

        # Step 1: Create initial ticket
        ticket = await self.ticket_service.create_ticket(
            customer_id=customer_id,
            customer_message=message,
            category=MessageCategory.QUERY,  # Temporary, will be updated
        )

        try:
            # Chaos check: ticket creation
            self._maybe_trigger_chaos("TicketService", chaos_mode)

            # Step 2: Classify the message
            self._maybe_trigger_chaos("Classifier", chaos_mode)
            classification = await self.classifier.process(
                ticket_id=ticket.id,
                message=message,
            )

            # Update ticket with classification
            ticket.category = classification.category
            ticket.metadata["classification_confidence"] = classification.confidence
            ticket.metadata["classification_reasoning"] = classification.reasoning
            await self.ticket_service.update_ticket(ticket)

            # Step 3: Route to appropriate handler
            self._maybe_trigger_chaos("Router", chaos_mode)
            handler = self.handlers[classification.category]

            # Log routing decision
            await self.audit_service.log_action(
                ticket_id=ticket.id,
                agent_name="orchestrator",
                action=AuditAction.ROUTE,
                input_summary=f"category={classification.category.value}",
                output_summary=f"handler={handler.name}",
                decision_reasoning=f"Routing to {handler.name} based on classification",
                confidence_score=classification.confidence,
                success=True,
            )

            # Step 4: Generate response
            self._maybe_trigger_chaos(handler.name, chaos_mode)
            handler_response = await handler.process(
                ticket_id=ticket.id,
                message=message,
            )

            # Step 5: Update ticket with response
            ticket.agent_response = handler_response.response
            ticket.handler_agent = handler.name
            ticket.priority = handler_response.priority
            ticket.status = TicketStatus.RESOLVED

            if handler_response.requires_escalation:
                ticket.status = TicketStatus.ESCALATED
                ticket.metadata["escalation_reason"] = handler_response.escalation_reason

            self._maybe_trigger_chaos("Database", chaos_mode)
            await self.ticket_service.update_ticket(ticket)

            # Get final token usage cost
            total_cost = await self.token_tracker.get_ticket_cost(ticket.id)
            ticket.metadata["total_cost_usd"] = total_cost

            logger.info(
                "message_processed",
                ticket_id=ticket.id,
                customer_id=customer_id,
                category=classification.category.value,
                handler=handler.name,
                priority=handler_response.priority.value,
                escalated=handler_response.requires_escalation,
                total_cost_usd=total_cost,
            )

            return ProcessingResult(
                ticket=ticket,
                classification=classification,
                response=handler_response.response,
                handler_used=handler.name,
                requires_escalation=handler_response.requires_escalation,
                escalation_reason=handler_response.escalation_reason,
                cited_policies=handler_response.cited_policies,
            )

        except ChaosError:
            # Re-raise chaos errors without additional logging
            raise

        except Exception as e:
            logger.error(
                "message_processing_failed",
                ticket_id=ticket.id,
                error=str(e),
            )

            # Log the failure
            await self.audit_service.log_action(
                ticket_id=ticket.id,
                agent_name="orchestrator",
                action=AuditAction.RESPOND,
                input_summary=f"Processing message for ticket {ticket.id}",
                output_summary="Processing failed",
                success=False,
                error_message=str(e),
            )

            raise

    async def get_ticket_details(self, ticket_id: str) -> dict:
        """Get full details for a ticket including audit trail and costs.

        Args:
            ticket_id: Ticket ID

        Returns:
            Dictionary with ticket details
        """
        ticket = await self.ticket_service.get_ticket(ticket_id)
        audit_trail = await self.audit_service.get_ticket_audit_trail(ticket_id)
        usage_records = await self.token_tracker.get_ticket_usage(ticket_id)
        total_cost = await self.token_tracker.get_ticket_cost(ticket_id)

        return {
            "ticket": ticket.to_dict(),
            "audit_trail": [log.to_dict() for log in audit_trail],
            "token_usage": [usage.to_dict() for usage in usage_records],
            "total_cost_usd": total_cost,
        }

    async def get_statistics(self) -> dict:
        """Get overall system statistics.

        Returns:
            Dictionary with statistics
        """
        ticket_stats = await self.ticket_service.get_statistics()
        audit_stats = await self.audit_service.get_statistics()
        usage_summary = await self.token_tracker.get_summary()
        cost_by_agent = await self.token_tracker.get_cost_by_agent()

        return {
            "tickets": ticket_stats,
            "audit": audit_stats,
            "usage": usage_summary,
            "cost_by_agent": cost_by_agent,
        }
