"""Business logic for audit logging."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, List

from ..db.connection import DatabaseConnection
from ..db.models import AuditLog
from ..db.repositories.audit_repository import AuditRepository
from ..utils.enums import AuditAction
from ..utils.logger import get_logger

logger = get_logger(__name__)


class AuditService:
    """Service for managing audit logs."""

    def __init__(self, db: DatabaseConnection):
        """Initialize the audit service.

        Args:
            db: Database connection
        """
        self.audit_repo = AuditRepository(db)

    async def log_action(
        self,
        ticket_id: str,
        agent_name: str,
        action: AuditAction,
        input_summary: str,
        output_summary: str,
        decision_reasoning: str | None = None,
        confidence_score: float | None = None,
        duration_ms: int = 0,
        success: bool = True,
        error_message: str | None = None,
    ) -> AuditLog:
        """Log an agent action.

        Args:
            ticket_id: Associated ticket ID
            agent_name: Name of the agent
            action: Action performed
            input_summary: Summary of the input
            output_summary: Summary of the output
            decision_reasoning: Optional reasoning for decisions
            confidence_score: Optional confidence score (0-1)
            duration_ms: Duration in milliseconds
            success: Whether the action succeeded
            error_message: Error message if failed

        Returns:
            The created audit log
        """
        audit_log = AuditLog(
            ticket_id=ticket_id,
            agent_name=agent_name,
            action=action,
            input_summary=input_summary,
            output_summary=output_summary,
            decision_reasoning=decision_reasoning,
            confidence_score=confidence_score,
            duration_ms=duration_ms,
            success=success,
            error_message=error_message,
        )

        await self.audit_repo.create(audit_log)

        log_fn = logger.info if success else logger.warning
        log_fn(
            "audit_logged",
            ticket_id=ticket_id,
            agent_name=agent_name,
            action=action.value,
            success=success,
            duration_ms=duration_ms,
        )

        return audit_log

    @asynccontextmanager
    async def track_action(
        self,
        ticket_id: str,
        agent_name: str,
        action: AuditAction,
        input_summary: str,
    ) -> AsyncIterator["ActionTracker"]:
        """Context manager for tracking an action with timing.

        Args:
            ticket_id: Associated ticket ID
            agent_name: Name of the agent
            action: Action being performed
            input_summary: Summary of the input

        Yields:
            ActionTracker instance to collect results
        """
        tracker = ActionTracker(
            ticket_id=ticket_id,
            agent_name=agent_name,
            action=action,
            input_summary=input_summary,
        )

        try:
            yield tracker
        except Exception as e:
            tracker.set_error(str(e))
            raise
        finally:
            await self.log_action(
                ticket_id=tracker.ticket_id,
                agent_name=tracker.agent_name,
                action=tracker.action,
                input_summary=tracker.input_summary,
                output_summary=tracker.output_summary or "",
                decision_reasoning=tracker.decision_reasoning,
                confidence_score=tracker.confidence_score,
                duration_ms=tracker.get_duration_ms(),
                success=tracker.success,
                error_message=tracker.error_message,
            )

    async def get_ticket_audit_trail(self, ticket_id: str) -> List[AuditLog]:
        """Get the complete audit trail for a ticket.

        Args:
            ticket_id: Ticket ID

        Returns:
            List of audit logs in chronological order
        """
        return await self.audit_repo.get_by_ticket(ticket_id)

    async def get_agent_logs(
        self,
        agent_name: str,
        limit: int = 100,
    ) -> List[AuditLog]:
        """Get logs for a specific agent.

        Args:
            agent_name: Name of the agent
            limit: Maximum number of logs

        Returns:
            List of audit logs
        """
        return await self.audit_repo.get_by_agent(agent_name, limit)

    async def get_failures(self, limit: int = 100) -> List[AuditLog]:
        """Get failed actions.

        Args:
            limit: Maximum number of logs

        Returns:
            List of failed audit logs
        """
        return await self.audit_repo.get_failures(limit)

    async def get_statistics(self) -> dict:
        """Get audit statistics.

        Returns:
            Dictionary with statistics
        """
        by_agent = await self.audit_repo.count_by_agent()
        by_action = await self.audit_repo.count_by_action()
        avg_duration = await self.audit_repo.get_average_duration_by_agent()

        return {
            "by_agent": by_agent,
            "by_action": by_action,
            "average_duration_by_agent": avg_duration,
        }


class ActionTracker:
    """Helper class for tracking action results."""

    def __init__(
        self,
        ticket_id: str,
        agent_name: str,
        action: AuditAction,
        input_summary: str,
    ):
        """Initialize the tracker.

        Args:
            ticket_id: Ticket ID
            agent_name: Agent name
            action: Action being tracked
            input_summary: Input summary
        """
        self.ticket_id = ticket_id
        self.agent_name = agent_name
        self.action = action
        self.input_summary = input_summary
        self.output_summary: str | None = None
        self.decision_reasoning: str | None = None
        self.confidence_score: float | None = None
        self.success: bool = True
        self.error_message: str | None = None
        self._start_time = time.perf_counter()

    def set_output(
        self,
        output_summary: str,
        reasoning: str | None = None,
        confidence: float | None = None,
    ) -> None:
        """Set the output details.

        Args:
            output_summary: Summary of the output
            reasoning: Optional decision reasoning
            confidence: Optional confidence score
        """
        self.output_summary = output_summary
        self.decision_reasoning = reasoning
        self.confidence_score = confidence

    def set_error(self, error: str) -> None:
        """Mark the action as failed.

        Args:
            error: Error message
        """
        self.success = False
        self.error_message = error
        self.output_summary = f"Error: {error}"

    def get_duration_ms(self) -> int:
        """Get the duration since start.

        Returns:
            Duration in milliseconds
        """
        return int((time.perf_counter() - self._start_time) * 1000)
