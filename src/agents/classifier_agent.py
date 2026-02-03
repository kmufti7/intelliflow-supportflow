"""Message classifier agent."""

import json
from dataclasses import dataclass

from .base_agent import BaseAgent
from ..llm.prompts import CLASSIFIER_SYSTEM_PROMPT
from ..utils.enums import MessageCategory, AuditAction
from ..utils.exceptions import ClassificationError


@dataclass
class ClassificationResult:
    """Result of message classification."""

    category: MessageCategory
    confidence: float
    reasoning: str


class ClassifierAgent(BaseAgent):
    """Agent that classifies customer messages into categories."""

    @property
    def name(self) -> str:
        """Get the agent name."""
        return "classifier"

    @property
    def system_prompt(self) -> str:
        """Get the system prompt."""
        return CLASSIFIER_SYSTEM_PROMPT

    async def process(self, ticket_id: str, message: str) -> ClassificationResult:
        """Classify a customer message.

        Args:
            ticket_id: Associated ticket ID
            message: Customer message to classify

        Returns:
            ClassificationResult with category, confidence, and reasoning

        Raises:
            ClassificationError: If classification fails
        """
        self.logger.info(
            "classifying_message",
            ticket_id=ticket_id,
            message_length=len(message),
        )

        response = await self.call_llm(
            ticket_id=ticket_id,
            user_message=message,
            action=AuditAction.CLASSIFY,
            max_tokens=256,
            temperature=0.3,  # Lower temperature for more consistent classification
        )

        result = self._parse_response(response.content)

        # Update the audit log with classification details
        await self.audit_service.log_action(
            ticket_id=ticket_id,
            agent_name=self.name,
            action=AuditAction.CLASSIFY,
            input_summary=self._truncate(message, 200),
            output_summary=f"category={result.category.value}",
            decision_reasoning=result.reasoning,
            confidence_score=result.confidence,
            success=True,
        )

        self.logger.info(
            "message_classified",
            ticket_id=ticket_id,
            category=result.category.value,
            confidence=result.confidence,
        )

        return result

    def _parse_response(self, content: str) -> ClassificationResult:
        """Parse the LLM response into a ClassificationResult.

        Args:
            content: Raw LLM response

        Returns:
            Parsed ClassificationResult

        Raises:
            ClassificationError: If parsing fails
        """
        try:
            # Clean the response (remove markdown code blocks if present)
            cleaned = content.strip()
            if cleaned.startswith("```"):
                # Remove code block markers
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1]) if len(lines) > 2 else cleaned

            data = json.loads(cleaned)

            # Validate and extract category
            category_str = data.get("category", "").lower()
            try:
                category = MessageCategory(category_str)
            except ValueError:
                raise ClassificationError(
                    f"Invalid category: {category_str}",
                    details={"raw_response": content},
                )

            # Extract confidence (default to 0.5 if not provided)
            confidence = float(data.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))  # Clamp to 0-1

            # Extract reasoning
            reasoning = data.get("reasoning", "No reasoning provided")

            return ClassificationResult(
                category=category,
                confidence=confidence,
                reasoning=reasoning,
            )

        except json.JSONDecodeError as e:
            self.logger.error(
                "classification_parse_error",
                error=str(e),
                content=content,
            )
            raise ClassificationError(
                f"Failed to parse classification response: {e}",
                details={"raw_response": content},
            )
        except Exception as e:
            self.logger.error(
                "classification_error",
                error=str(e),
            )
            raise ClassificationError(
                f"Classification failed: {e}",
                details={"raw_response": content},
            )
