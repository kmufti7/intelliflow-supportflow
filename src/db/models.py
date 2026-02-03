"""Data models for the support flow system."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import json
import uuid

from ..utils.enums import MessageCategory, TicketStatus, TicketPriority, AuditAction


def generate_id() -> str:
    """Generate a unique ID."""
    return str(uuid.uuid4())


def now() -> datetime:
    """Get current UTC datetime."""
    return datetime.utcnow()


@dataclass
class Ticket:
    """Support ticket data model."""

    customer_id: str
    customer_message: str
    category: MessageCategory
    status: TicketStatus = TicketStatus.OPEN
    priority: TicketPriority = TicketPriority.MEDIUM
    agent_response: str | None = None
    handler_agent: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=generate_id)
    created_at: datetime = field(default_factory=now)
    updated_at: datetime = field(default_factory=now)
    resolved_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "id": self.id,
            "customer_id": self.customer_id,
            "customer_message": self.customer_message,
            "category": self.category.value,
            "status": self.status.value,
            "priority": self.priority.value,
            "agent_response": self.agent_response,
            "handler_agent": self.handler_agent,
            "metadata": json.dumps(self.metadata),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Ticket":
        """Create from database row."""
        return cls(
            id=data["id"],
            customer_id=data["customer_id"],
            customer_message=data["customer_message"],
            category=MessageCategory(data["category"]),
            status=TicketStatus(data["status"]),
            priority=TicketPriority(data["priority"]),
            agent_response=data["agent_response"],
            handler_agent=data["handler_agent"],
            metadata=json.loads(data["metadata"]) if data["metadata"] else {},
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            resolved_at=datetime.fromisoformat(data["resolved_at"])
            if data["resolved_at"]
            else None,
        )


@dataclass
class AuditLog:
    """Audit log entry for agent actions."""

    ticket_id: str
    agent_name: str
    action: AuditAction
    input_summary: str
    output_summary: str
    decision_reasoning: str | None = None
    confidence_score: float | None = None
    duration_ms: int = 0
    success: bool = True
    error_message: str | None = None
    id: str = field(default_factory=generate_id)
    created_at: datetime = field(default_factory=now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "id": self.id,
            "ticket_id": self.ticket_id,
            "agent_name": self.agent_name,
            "action": self.action.value,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "decision_reasoning": self.decision_reasoning,
            "confidence_score": self.confidence_score,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuditLog":
        """Create from database row."""
        return cls(
            id=data["id"],
            ticket_id=data["ticket_id"],
            agent_name=data["agent_name"],
            action=AuditAction(data["action"]),
            input_summary=data["input_summary"],
            output_summary=data["output_summary"],
            decision_reasoning=data["decision_reasoning"],
            confidence_score=data["confidence_score"],
            duration_ms=data["duration_ms"],
            success=bool(data["success"]),
            error_message=data["error_message"],
            created_at=datetime.fromisoformat(data["created_at"]),
        )


@dataclass
class TokenUsage:
    """Token usage record for LLM calls."""

    ticket_id: str
    agent_name: str
    model_name: str
    provider: str
    input_tokens: int
    output_tokens: int
    input_cost_usd: float = 0.0
    output_cost_usd: float = 0.0
    cached_tokens: int = 0
    id: str = field(default_factory=generate_id)
    created_at: datetime = field(default_factory=now)

    @property
    def total_tokens(self) -> int:
        """Get total tokens used."""
        return self.input_tokens + self.output_tokens

    @property
    def total_cost_usd(self) -> float:
        """Get total cost in USD."""
        return self.input_cost_usd + self.output_cost_usd

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "id": self.id,
            "ticket_id": self.ticket_id,
            "agent_name": self.agent_name,
            "model_name": self.model_name,
            "provider": self.provider,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "input_cost_usd": self.input_cost_usd,
            "output_cost_usd": self.output_cost_usd,
            "cached_tokens": self.cached_tokens,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TokenUsage":
        """Create from database row."""
        return cls(
            id=data["id"],
            ticket_id=data["ticket_id"],
            agent_name=data["agent_name"],
            model_name=data["model_name"],
            provider=data["provider"],
            input_tokens=data["input_tokens"],
            output_tokens=data["output_tokens"],
            input_cost_usd=data["input_cost_usd"],
            output_cost_usd=data["output_cost_usd"],
            cached_tokens=data["cached_tokens"],
            created_at=datetime.fromisoformat(data["created_at"]),
        )


@dataclass
class ModelPricing:
    """Pricing information for LLM models."""

    model_name: str
    provider: str
    input_cost_per_1k: float
    output_cost_per_1k: float
    cached_input_cost_per_1k: float = 0.0
    updated_at: datetime = field(default_factory=now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "model_name": self.model_name,
            "provider": self.provider,
            "input_cost_per_1k": self.input_cost_per_1k,
            "output_cost_per_1k": self.output_cost_per_1k,
            "cached_input_cost_per_1k": self.cached_input_cost_per_1k,
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelPricing":
        """Create from database row."""
        return cls(
            model_name=data["model_name"],
            provider=data["provider"],
            input_cost_per_1k=data["input_cost_per_1k"],
            output_cost_per_1k=data["output_cost_per_1k"],
            cached_input_cost_per_1k=data["cached_input_cost_per_1k"],
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )
