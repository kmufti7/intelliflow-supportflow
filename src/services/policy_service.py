"""Policy service for loading and searching banking policies."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Policy:
    """A banking policy rule."""

    id: str
    title: str
    content: str
    category: str

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "category": self.category,
        }

    def format_citation(self) -> str:
        """Format the policy for citation in responses."""
        return f"Per {self.id}: {self.content}"

    def short_citation(self) -> str:
        """Format a short citation reference."""
        return f"[{self.id}: {self.title}]"


class PolicyService:
    """Service for loading and searching banking policies."""

    # Keywords mapped to policy IDs for quick lookup
    KEYWORD_MAPPINGS = {
        # Card-related
        "card replacement": ["POLICY-001"],
        "new card": ["POLICY-001"],
        "replace card": ["POLICY-001"],
        "lost card": ["POLICY-002"],
        "stolen card": ["POLICY-002"],
        "card stolen": ["POLICY-002"],
        "dispute": ["POLICY-003"],
        "disputed charge": ["POLICY-003"],
        "unauthorized charge": ["POLICY-003"],
        "chargeback": ["POLICY-003"],
        "atm limit": ["POLICY-004"],
        "withdrawal limit": ["POLICY-004"],
        "transaction limit": ["POLICY-004"],
        "spending limit": ["POLICY-004"],
        # Account-related
        "maintenance fee": ["POLICY-005", "POLICY-006"],
        "monthly fee": ["POLICY-005", "POLICY-006"],
        "waive fee": ["POLICY-006"],
        "fee waiver": ["POLICY-006"],
        "overdraft": ["POLICY-007"],
        "nsf": ["POLICY-007"],
        "insufficient funds": ["POLICY-007"],
        "close account": ["POLICY-008"],
        "account closure": ["POLICY-008"],
        # Transfer-related
        "wire transfer": ["POLICY-009"],
        "wire": ["POLICY-009"],
        "international transfer": ["POLICY-009"],
        "ach": ["POLICY-010"],
        "transfer time": ["POLICY-010"],
        "bill pay": ["POLICY-011"],
        "late payment": ["POLICY-011"],
        # Interest-related
        "interest rate": ["POLICY-012"],
        "savings rate": ["POLICY-012"],
        "cd": ["POLICY-013"],
        "certificate of deposit": ["POLICY-013"],
        "early withdrawal": ["POLICY-013"],
        # Security-related
        "fraud": ["POLICY-014", "POLICY-002"],
        "fraudulent": ["POLICY-014"],
        "unauthorized": ["POLICY-014", "POLICY-002", "POLICY-003"],
        "locked out": ["POLICY-015"],
        "account locked": ["POLICY-015"],
        "login": ["POLICY-015"],
        "two factor": ["POLICY-016"],
        "2fa": ["POLICY-016"],
        "verification": ["POLICY-016"],
        # Service-related
        "complaint": ["POLICY-017"],
        "response time": ["POLICY-017"],
        "branch hours": ["POLICY-018"],
        "hours": ["POLICY-018"],
        "statement": ["POLICY-019"],
        "bank statement": ["POLICY-019"],
        "power of attorney": ["POLICY-020"],
        "poa": ["POLICY-020"],
    }

    def __init__(self, policy_file: Optional[Path] = None):
        """Initialize the policy service.

        Args:
            policy_file: Path to the policy markdown file. If None, uses default.
        """
        if policy_file is None:
            # Default path relative to project root
            policy_file = Path(__file__).parent.parent.parent / "data" / "policy_kb.md"

        self.policy_file = policy_file
        self.policies: dict[str, Policy] = {}
        self._load_policies()

    def _load_policies(self) -> None:
        """Load policies from the markdown file."""
        if not self.policy_file.exists():
            logger.warning("policy_file_not_found", path=str(self.policy_file))
            return

        content = self.policy_file.read_text(encoding="utf-8")

        # Parse markdown to extract policies
        # Pattern matches: ### POLICY-XXX: Title\nContent
        pattern = r"### (POLICY-\d+): (.+?)\n(.+?)(?=\n###|\n---|\Z)"
        matches = re.findall(pattern, content, re.DOTALL)

        current_category = "General"
        category_pattern = r"## (.+?)\n"
        categories = re.findall(category_pattern, content)

        # Build category mapping based on position
        category_positions = [(m.start(), m.group(1)) for m in re.finditer(category_pattern, content)]

        for policy_id, title, body in matches:
            # Find which category this policy belongs to
            policy_pos = content.find(f"### {policy_id}")
            for pos, cat in reversed(category_positions):
                if pos < policy_pos:
                    current_category = cat
                    break

            policy = Policy(
                id=policy_id,
                title=title.strip(),
                content=body.strip(),
                category=current_category,
            )
            self.policies[policy_id] = policy

        logger.info("policies_loaded", count=len(self.policies))

    def get_policy(self, policy_id: str) -> Optional[Policy]:
        """Get a specific policy by ID.

        Args:
            policy_id: The policy ID (e.g., "POLICY-001")

        Returns:
            The Policy if found, None otherwise
        """
        return self.policies.get(policy_id)

    def search_policies(self, message: str, max_results: int = 3) -> List[Policy]:
        """Search for relevant policies based on message content.

        Uses keyword matching to find policies relevant to the customer message.

        Args:
            message: Customer message to analyze
            max_results: Maximum number of policies to return

        Returns:
            List of relevant Policy objects
        """
        message_lower = message.lower()
        found_policy_ids: set[str] = set()

        # Check keyword mappings
        for keyword, policy_ids in self.KEYWORD_MAPPINGS.items():
            if keyword in message_lower:
                found_policy_ids.update(policy_ids)

        # Also do content-based search
        for policy_id, policy in self.policies.items():
            # Check if key terms from policy appear in message
            policy_terms = policy.content.lower()
            message_words = set(message_lower.split())

            # Look for significant term overlaps
            if any(word in policy_terms for word in message_words if len(word) > 4):
                if policy_id not in found_policy_ids:
                    # Score by relevance - check title match
                    title_words = set(policy.title.lower().split())
                    if message_words & title_words:
                        found_policy_ids.add(policy_id)

        # Convert to Policy objects and sort by ID
        policies = [
            self.policies[pid]
            for pid in sorted(found_policy_ids)
            if pid in self.policies
        ]

        logger.debug(
            "policies_searched",
            message_length=len(message),
            policies_found=len(policies),
        )

        return policies[:max_results]

    def get_all_policies(self) -> List[Policy]:
        """Get all loaded policies.

        Returns:
            List of all Policy objects
        """
        return list(self.policies.values())

    def format_policies_for_prompt(self, policies: List[Policy]) -> str:
        """Format policies for inclusion in LLM prompt.

        Args:
            policies: List of policies to format

        Returns:
            Formatted string for prompt injection
        """
        if not policies:
            return ""

        lines = ["[Relevant Bank Policies - cite these in your response:]"]
        for policy in policies:
            lines.append(f"\n{policy.id} ({policy.title}):")
            lines.append(policy.content)

        return "\n".join(lines)


# Global instance for easy access
_policy_service: Optional[PolicyService] = None


def get_policy_service() -> PolicyService:
    """Get or create the global PolicyService instance.

    Returns:
        PolicyService instance
    """
    global _policy_service
    if _policy_service is None:
        _policy_service = PolicyService()
    return _policy_service
