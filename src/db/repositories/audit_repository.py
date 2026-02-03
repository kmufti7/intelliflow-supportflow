"""Repository for audit log CRUD operations."""

from typing import List

from ..connection import DatabaseConnection
from ..models import AuditLog
from ...utils.enums import AuditAction
from ...utils.exceptions import DatabaseError
from ...utils.logger import get_logger

logger = get_logger(__name__)


class AuditRepository:
    """Repository for audit log database operations."""

    def __init__(self, db: DatabaseConnection):
        """Initialize the repository.

        Args:
            db: Database connection instance
        """
        self.db = db

    async def create(self, audit_log: AuditLog) -> AuditLog:
        """Create a new audit log entry.

        Args:
            audit_log: Audit log to create

        Returns:
            The created audit log
        """
        data = audit_log.to_dict()

        try:
            await self.db.execute(
                """
                INSERT INTO audit_logs
                (id, ticket_id, agent_name, action, input_summary, output_summary,
                 decision_reasoning, confidence_score, duration_ms, success, error_message, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["id"],
                    data["ticket_id"],
                    data["agent_name"],
                    data["action"],
                    data["input_summary"],
                    data["output_summary"],
                    data["decision_reasoning"],
                    data["confidence_score"],
                    data["duration_ms"],
                    data["success"],
                    data["error_message"],
                    data["created_at"],
                ),
            )

            logger.debug(
                "audit_log_created",
                audit_id=audit_log.id,
                ticket_id=audit_log.ticket_id,
                action=audit_log.action.value,
            )
            return audit_log

        except Exception as e:
            raise DatabaseError(f"Failed to create audit log: {e}", operation="create")

    async def get_by_ticket(self, ticket_id: str) -> List[AuditLog]:
        """Get all audit logs for a ticket.

        Args:
            ticket_id: Ticket ID

        Returns:
            List of audit logs
        """
        rows = await self.db.fetch_all(
            "SELECT * FROM audit_logs WHERE ticket_id = ? ORDER BY created_at ASC",
            (ticket_id,),
        )

        return [AuditLog.from_dict(dict(row)) for row in rows]

    async def get_by_agent(self, agent_name: str, limit: int = 100) -> List[AuditLog]:
        """Get audit logs for a specific agent.

        Args:
            agent_name: Name of the agent
            limit: Maximum number of logs to return

        Returns:
            List of audit logs
        """
        rows = await self.db.fetch_all(
            """
            SELECT * FROM audit_logs
            WHERE agent_name = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (agent_name, limit),
        )

        return [AuditLog.from_dict(dict(row)) for row in rows]

    async def get_by_action(self, action: AuditAction, limit: int = 100) -> List[AuditLog]:
        """Get audit logs for a specific action type.

        Args:
            action: Action type
            limit: Maximum number of logs to return

        Returns:
            List of audit logs
        """
        rows = await self.db.fetch_all(
            """
            SELECT * FROM audit_logs
            WHERE action = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (action.value, limit),
        )

        return [AuditLog.from_dict(dict(row)) for row in rows]

    async def get_failures(self, limit: int = 100) -> List[AuditLog]:
        """Get failed audit logs.

        Args:
            limit: Maximum number of logs to return

        Returns:
            List of failed audit logs
        """
        rows = await self.db.fetch_all(
            """
            SELECT * FROM audit_logs
            WHERE success = 0
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )

        return [AuditLog.from_dict(dict(row)) for row in rows]

    async def get_recent(self, limit: int = 50) -> List[AuditLog]:
        """Get recent audit logs.

        Args:
            limit: Maximum number of logs to return

        Returns:
            List of recent audit logs
        """
        rows = await self.db.fetch_all(
            "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )

        return [AuditLog.from_dict(dict(row)) for row in rows]

    async def count_by_agent(self) -> dict[str, int]:
        """Get count of audit logs by agent.

        Returns:
            Dictionary of agent name to count
        """
        rows = await self.db.fetch_all(
            "SELECT agent_name, COUNT(*) as count FROM audit_logs GROUP BY agent_name"
        )

        return {row["agent_name"]: row["count"] for row in rows}

    async def count_by_action(self) -> dict[str, int]:
        """Get count of audit logs by action.

        Returns:
            Dictionary of action to count
        """
        rows = await self.db.fetch_all(
            "SELECT action, COUNT(*) as count FROM audit_logs GROUP BY action"
        )

        return {row["action"]: row["count"] for row in rows}

    async def get_average_duration_by_agent(self) -> dict[str, float]:
        """Get average duration by agent.

        Returns:
            Dictionary of agent name to average duration in ms
        """
        rows = await self.db.fetch_all(
            """
            SELECT agent_name, AVG(duration_ms) as avg_duration
            FROM audit_logs
            WHERE success = 1
            GROUP BY agent_name
            """
        )

        return {row["agent_name"]: row["avg_duration"] for row in rows}
