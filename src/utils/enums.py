"""Enumerations for the support flow system."""

from enum import Enum


class MessageCategory(str, Enum):
    """Categories for customer messages."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    QUERY = "query"


class TicketStatus(str, Enum):
    """Status values for support tickets."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"
    ESCALATED = "escalated"


class TicketPriority(int, Enum):
    """Priority levels for support tickets (1=highest, 5=lowest)."""

    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4
    MINIMAL = 5


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class AuditAction(str, Enum):
    """Actions that can be audited."""

    CLASSIFY = "classify"
    ROUTE = "route"
    RESPOND = "respond"
    ESCALATE = "escalate"
    CREATE_TICKET = "create_ticket"
    UPDATE_TICKET = "update_ticket"
