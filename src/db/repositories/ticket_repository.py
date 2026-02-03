"""Repository for ticket CRUD operations."""

from datetime import datetime
from typing import List

from ..connection import DatabaseConnection
from ..models import Ticket
from ...utils.enums import TicketStatus, MessageCategory
from ...utils.exceptions import TicketNotFoundError, DatabaseError
from ...utils.logger import get_logger

logger = get_logger(__name__)


class TicketRepository:
    """Repository for ticket database operations."""

    def __init__(self, db: DatabaseConnection):
        """Initialize the repository.

        Args:
            db: Database connection instance
        """
        self.db = db

    async def create(self, ticket: Ticket) -> Ticket:
        """Create a new ticket.

        Args:
            ticket: Ticket to create

        Returns:
            The created ticket
        """
        data = ticket.to_dict()

        try:
            await self.db.execute(
                """
                INSERT INTO tickets
                (id, customer_id, customer_message, category, status, priority,
                 agent_response, handler_agent, metadata, created_at, updated_at, resolved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["id"],
                    data["customer_id"],
                    data["customer_message"],
                    data["category"],
                    data["status"],
                    data["priority"],
                    data["agent_response"],
                    data["handler_agent"],
                    data["metadata"],
                    data["created_at"],
                    data["updated_at"],
                    data["resolved_at"],
                ),
            )

            logger.debug("ticket_created", ticket_id=ticket.id)
            return ticket

        except Exception as e:
            raise DatabaseError(f"Failed to create ticket: {e}", operation="create")

    async def get_by_id(self, ticket_id: str) -> Ticket:
        """Get a ticket by ID.

        Args:
            ticket_id: Ticket ID

        Returns:
            The ticket

        Raises:
            TicketNotFoundError: If ticket not found
        """
        row = await self.db.fetch_one(
            "SELECT * FROM tickets WHERE id = ?",
            (ticket_id,),
        )

        if not row:
            raise TicketNotFoundError(ticket_id)

        return Ticket.from_dict(dict(row))

    async def update(self, ticket: Ticket) -> Ticket:
        """Update an existing ticket.

        Args:
            ticket: Ticket with updated values

        Returns:
            The updated ticket
        """
        ticket.updated_at = datetime.utcnow()
        data = ticket.to_dict()

        try:
            await self.db.execute(
                """
                UPDATE tickets SET
                    customer_message = ?,
                    category = ?,
                    status = ?,
                    priority = ?,
                    agent_response = ?,
                    handler_agent = ?,
                    metadata = ?,
                    updated_at = ?,
                    resolved_at = ?
                WHERE id = ?
                """,
                (
                    data["customer_message"],
                    data["category"],
                    data["status"],
                    data["priority"],
                    data["agent_response"],
                    data["handler_agent"],
                    data["metadata"],
                    data["updated_at"],
                    data["resolved_at"],
                    data["id"],
                ),
            )

            logger.debug("ticket_updated", ticket_id=ticket.id)
            return ticket

        except Exception as e:
            raise DatabaseError(f"Failed to update ticket: {e}", operation="update")

    async def get_by_customer(self, customer_id: str) -> List[Ticket]:
        """Get all tickets for a customer.

        Args:
            customer_id: Customer ID

        Returns:
            List of tickets
        """
        rows = await self.db.fetch_all(
            "SELECT * FROM tickets WHERE customer_id = ? ORDER BY created_at DESC",
            (customer_id,),
        )

        return [Ticket.from_dict(dict(row)) for row in rows]

    async def get_by_status(self, status: TicketStatus) -> List[Ticket]:
        """Get all tickets with a given status.

        Args:
            status: Ticket status to filter by

        Returns:
            List of tickets
        """
        rows = await self.db.fetch_all(
            "SELECT * FROM tickets WHERE status = ? ORDER BY created_at DESC",
            (status.value,),
        )

        return [Ticket.from_dict(dict(row)) for row in rows]

    async def get_by_category(self, category: MessageCategory) -> List[Ticket]:
        """Get all tickets with a given category.

        Args:
            category: Message category to filter by

        Returns:
            List of tickets
        """
        rows = await self.db.fetch_all(
            "SELECT * FROM tickets WHERE category = ? ORDER BY created_at DESC",
            (category.value,),
        )

        return [Ticket.from_dict(dict(row)) for row in rows]

    async def get_recent(self, limit: int = 10) -> List[Ticket]:
        """Get recent tickets.

        Args:
            limit: Maximum number of tickets to return

        Returns:
            List of recent tickets
        """
        rows = await self.db.fetch_all(
            "SELECT * FROM tickets ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )

        return [Ticket.from_dict(dict(row)) for row in rows]

    async def resolve(self, ticket_id: str, response: str) -> Ticket:
        """Mark a ticket as resolved.

        Args:
            ticket_id: Ticket ID
            response: Agent response

        Returns:
            The updated ticket
        """
        ticket = await self.get_by_id(ticket_id)
        ticket.status = TicketStatus.RESOLVED
        ticket.agent_response = response
        ticket.resolved_at = datetime.utcnow()

        return await self.update(ticket)

    async def count_by_status(self) -> dict[str, int]:
        """Get count of tickets by status.

        Returns:
            Dictionary of status to count
        """
        rows = await self.db.fetch_all(
            "SELECT status, COUNT(*) as count FROM tickets GROUP BY status"
        )

        return {row["status"]: row["count"] for row in rows}

    async def count_by_category(self) -> dict[str, int]:
        """Get count of tickets by category.

        Returns:
            Dictionary of category to count
        """
        rows = await self.db.fetch_all(
            "SELECT category, COUNT(*) as count FROM tickets GROUP BY category"
        )

        return {row["category"]: row["count"] for row in rows}
