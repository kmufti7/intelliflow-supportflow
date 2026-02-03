"""Abstract base class for all agents."""

from abc import ABC, abstractmethod
from typing import Any

from ..db.connection import DatabaseConnection
from ..llm.client import LLMClient, LLMResponse
from ..llm.token_tracker import TokenTracker
from ..services.audit_service import AuditService
from ..utils.enums import AuditAction
from ..utils.logger import get_logger


class BaseAgent(ABC):
    """Abstract base class for all agents in the support flow system."""

    def __init__(
        self,
        db: DatabaseConnection,
        llm_client: LLMClient,
        token_tracker: TokenTracker,
        audit_service: AuditService,
    ):
        """Initialize the agent.

        Args:
            db: Database connection
            llm_client: LLM client for API calls
            token_tracker: Token usage tracker
            audit_service: Audit logging service
        """
        self.db = db
        self.llm_client = llm_client
        self.token_tracker = token_tracker
        self.audit_service = audit_service
        self.logger = get_logger(self.__class__.__name__)

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the agent name."""
        pass

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Get the system prompt for this agent."""
        pass

    @abstractmethod
    async def process(self, ticket_id: str, message: str) -> Any:
        """Process a message.

        Args:
            ticket_id: Associated ticket ID
            message: Message to process

        Returns:
            Processing result (type depends on agent)
        """
        pass

    async def call_llm(
        self,
        ticket_id: str,
        user_message: str,
        action: AuditAction,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Call the LLM with tracking and auditing.

        Args:
            ticket_id: Associated ticket ID
            user_message: Message to send to LLM
            action: Audit action type
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature

        Returns:
            LLM response
        """
        async with self.audit_service.track_action(
            ticket_id=ticket_id,
            agent_name=self.name,
            action=action,
            input_summary=self._truncate(user_message, 200),
        ) as tracker:
            # Call LLM
            response = await self.llm_client.complete(
                system_prompt=self.system_prompt,
                user_message=user_message,
                max_tokens=max_tokens,
                temperature=temperature,
            )

            # Track token usage
            await self.token_tracker.track_usage(
                ticket_id=ticket_id,
                agent_name=self.name,
                response=response,
            )

            # Update tracker
            tracker.set_output(
                output_summary=self._truncate(response.content, 200),
            )

            self.logger.debug(
                "llm_call_complete",
                ticket_id=ticket_id,
                action=action.value,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
            )

            return response

    def _truncate(self, text: str, max_length: int) -> str:
        """Truncate text to max length.

        Args:
            text: Text to truncate
            max_length: Maximum length

        Returns:
            Truncated text
        """
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."
