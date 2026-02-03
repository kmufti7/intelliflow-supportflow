"""Custom exceptions for the support flow system."""

from typing import Dict, Optional


class SupportFlowError(Exception):
    """Base exception for all support flow errors."""

    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ClassificationError(SupportFlowError):
    """Raised when message classification fails."""

    pass


class LLMError(SupportFlowError):
    """Raised when LLM API calls fail."""

    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        details: Optional[Dict] = None,
    ):
        super().__init__(message, details)
        self.provider = provider
        self.model = model


class DatabaseError(SupportFlowError):
    """Raised when database operations fail."""

    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        details: Optional[Dict] = None,
    ):
        super().__init__(message, details)
        self.operation = operation


class ConfigurationError(SupportFlowError):
    """Raised when configuration is invalid."""

    pass


class AgentError(SupportFlowError):
    """Raised when an agent encounters an error."""

    def __init__(
        self,
        message: str,
        agent_name: Optional[str] = None,
        details: Optional[Dict] = None,
    ):
        super().__init__(message, details)
        self.agent_name = agent_name


class TicketNotFoundError(SupportFlowError):
    """Raised when a ticket is not found."""

    def __init__(self, ticket_id: str):
        super().__init__(f"Ticket not found: {ticket_id}")
        self.ticket_id = ticket_id


class ChaosError(SupportFlowError):
    """Raised when chaos mode triggers a simulated failure."""

    def __init__(self, component: str, message: str = "Chaos mode triggered failure"):
        super().__init__(f"[CHAOS] {component}: {message}")
        self.component = component
