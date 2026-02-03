"""Business logic for ticket management."""

from __future__ import annotations

from typing import List

from ..db.connection import DatabaseConnection
from ..db.models import Ticket
from ..db.repositories.ticket_repository import TicketRepository
from ..utils.enums import MessageCategory, TicketStatus, TicketPriority
from ..utils.logger import get_logger

logger = get_logger(__name__)


class TicketService:
    """Service for managing support tickets."""

    def __init__(self, db: DatabaseConnection):
        """Initialize the ticket service.

        Args:
            db: Database connection
        """
        self.ticket_repo = TicketRepository(db)

    async def create_ticket(
        self,
        customer_id: str,
        customer_message: str,
        category: MessageCategory,
        priority: TicketPriority = TicketPriority.MEDIUM,
        metadata: dict | None = None,
    ) -> Ticket:
        """Create a new support ticket.

        Args:
            customer_id: Customer identifier
            customer_message: The customer's message
            category: Message category
            priority: Ticket priority
            metadata: Optional metadata

        Returns:
            The created ticket
        """
        ticket = Ticket(
            customer_id=customer_id,
            customer_message=customer_message,
            category=category,
            priority=priority,
            metadata=metadata or {},
        )

        await self.ticket_repo.create(ticket)

        logger.info(
            "ticket_created",
            ticket_id=ticket.id,
            customer_id=customer_id,
            category=category.value,
            priority=priority.value,
        )

        return ticket

    async def get_ticket(self, ticket_id: str) -> Ticket:
        """Get a ticket by ID.

        Args:
            ticket_id: Ticket ID

        Returns:
            The ticket
        """
        return await self.ticket_repo.get_by_id(ticket_id)

    async def update_ticket(self, ticket: Ticket) -> Ticket:
        """Update a ticket.

        Args:
            ticket: Ticket with updated values

        Returns:
            The updated ticket
        """
        updated = await self.ticket_repo.update(ticket)

        logger.info(
            "ticket_updated",
            ticket_id=ticket.id,
            status=ticket.status.value,
        )

        return updated

    async def set_response(
        self,
        ticket_id: str,
        response: str,
        handler_agent: str,
    ) -> Ticket:
        """Set the agent response on a ticket.

        Args:
            ticket_id: Ticket ID
            response: Agent response
            handler_agent: Name of the handler agent

        Returns:
            The updated ticket
        """
        ticket = await self.ticket_repo.get_by_id(ticket_id)
        ticket.agent_response = response
        ticket.handler_agent = handler_agent
        ticket.status = TicketStatus.IN_PROGRESS

        return await self.ticket_repo.update(ticket)

    async def resolve_ticket(
        self,
        ticket_id: str,
        response: str | None = None,
    ) -> Ticket:
        """Mark a ticket as resolved.

        Args:
            ticket_id: Ticket ID
            response: Optional final response

        Returns:
            The resolved ticket
        """
        if response:
            ticket = await self.ticket_repo.resolve(ticket_id, response)
        else:
            ticket = await self.ticket_repo.get_by_id(ticket_id)
            ticket.status = TicketStatus.RESOLVED
            ticket = await self.ticket_repo.update(ticket)

        logger.info("ticket_resolved", ticket_id=ticket_id)

        return ticket

    async def escalate_ticket(self, ticket_id: str, reason: str) -> Ticket:
        """Escalate a ticket.

        Args:
            ticket_id: Ticket ID
            reason: Escalation reason

        Returns:
            The escalated ticket
        """
        ticket = await self.ticket_repo.get_by_id(ticket_id)
        ticket.status = TicketStatus.ESCALATED
        ticket.metadata["escalation_reason"] = reason

        updated = await self.ticket_repo.update(ticket)

        logger.info(
            "ticket_escalated",
            ticket_id=ticket_id,
            reason=reason,
        )

        return updated

    async def get_customer_tickets(self, customer_id: str) -> List[Ticket]:
        """Get all tickets for a customer.

        Args:
            customer_id: Customer ID

        Returns:
            List of tickets
        """
        return await self.ticket_repo.get_by_customer(customer_id)

    async def get_tickets_by_status(self, status: TicketStatus) -> List[Ticket]:
        """Get tickets by status.

        Args:
            status: Ticket status

        Returns:
            List of tickets
        """
        return await self.ticket_repo.get_by_status(status)

    async def get_tickets_by_category(self, category: MessageCategory) -> List[Ticket]:
        """Get tickets by category.

        Args:
            category: Message category

        Returns:
            List of tickets
        """
        return await self.ticket_repo.get_by_category(category)

    async def get_recent_tickets(self, limit: int = 10) -> List[Ticket]:
        """Get recent tickets.

        Args:
            limit: Maximum number of tickets

        Returns:
            List of recent tickets
        """
        return await self.ticket_repo.get_recent(limit)

    async def get_statistics(self) -> dict:
        """Get ticket statistics.

        Returns:
            Dictionary with statistics
        """
        by_status = await self.ticket_repo.count_by_status()
        by_category = await self.ticket_repo.count_by_category()

        total = sum(by_status.values())

        return {
            "total_tickets": total,
            "by_status": by_status,
            "by_category": by_category,
        }
