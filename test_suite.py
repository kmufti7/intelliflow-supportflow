"""
Test suite for IntelliFlow SupportFlow.

Tests classifier labeling, database operations, query handler, and chaos mode.
Run with: python -m pytest test_suite.py -v
Or run directly: python test_suite.py
"""

import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.db.connection import DatabaseConnection
from src.db.migrations import run_migrations
from src.db.models import Ticket
from src.db.repositories.ticket_repository import TicketRepository
from src.utils.enums import MessageCategory, TicketStatus, TicketPriority
from src.utils.exceptions import ChaosError
from src.llm.client import LLMResponse
from src.agents.classifier_agent import ClassifierAgent, ClassificationResult
from src.agents.query_handler import QueryHandler, HandlerResponse
from src.agents.orchestrator import Orchestrator
from src.services.ticket_service import TicketService
from src.services.audit_service import AuditService
from src.llm.token_tracker import TokenTracker


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def test_db():
    """Create a test database in memory."""
    db = DatabaseConnection(":memory:")
    await db.initialize()
    await run_migrations(db)
    yield db
    await db.close()


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = MagicMock()
    client.complete = AsyncMock()
    return client


@pytest.fixture
def mock_token_tracker():
    """Create a mock token tracker."""
    tracker = MagicMock(spec=TokenTracker)
    tracker.track_usage = AsyncMock()
    tracker.get_ticket_cost = AsyncMock(return_value=0.001)
    tracker.get_ticket_usage = AsyncMock(return_value=[])
    return tracker


@pytest.fixture
def mock_audit_service():
    """Create a mock audit service."""
    service = MagicMock(spec=AuditService)
    service.log_action = AsyncMock()
    service.get_ticket_audit_trail = AsyncMock(return_value=[])

    # Create a context manager mock for track_action
    @dataclass
    class MockTracker:
        def set_output(self, output_summary: str):
            pass

    class MockContextManager:
        async def __aenter__(self):
            return MockTracker()
        async def __aexit__(self, *args):
            pass

    service.track_action = MagicMock(return_value=MockContextManager())
    return service


def create_llm_response(content: str) -> LLMResponse:
    """Helper to create an LLM response."""
    return LLMResponse(
        content=content,
        model="test-model",
        provider="test",
        input_tokens=100,
        output_tokens=50,
        cached_tokens=0,
    )


# ============================================================================
# Classifier Tests - POSITIVE (2 test cases)
# ============================================================================

class TestClassifierPositive:
    """Test classifier correctly labels POSITIVE feedback."""

    @pytest.mark.asyncio
    async def test_positive_thank_you_message(self, test_db, mock_llm_client, mock_token_tracker, mock_audit_service):
        """Test that a thank you message is classified as POSITIVE."""
        # Setup mock LLM to return positive classification
        mock_llm_client.complete.return_value = create_llm_response(
            json.dumps({
                "category": "positive",
                "confidence": 0.95,
                "reasoning": "Customer expressing gratitude"
            })
        )

        classifier = ClassifierAgent(
            db=test_db,
            llm_client=mock_llm_client,
            token_tracker=mock_token_tracker,
            audit_service=mock_audit_service,
        )

        result = await classifier.process(
            ticket_id="test-ticket-1",
            message="Thank you so much for your excellent service!"
        )

        assert isinstance(result, ClassificationResult)
        assert result.category == MessageCategory.POSITIVE
        assert result.confidence >= 0.9

    @pytest.mark.asyncio
    async def test_positive_compliment_message(self, test_db, mock_llm_client, mock_token_tracker, mock_audit_service):
        """Test that a compliment about staff is classified as POSITIVE."""
        mock_llm_client.complete.return_value = create_llm_response(
            json.dumps({
                "category": "positive",
                "confidence": 0.92,
                "reasoning": "Customer praising employee"
            })
        )

        classifier = ClassifierAgent(
            db=test_db,
            llm_client=mock_llm_client,
            token_tracker=mock_token_tracker,
            audit_service=mock_audit_service,
        )

        result = await classifier.process(
            ticket_id="test-ticket-2",
            message="Your representative Sarah was incredibly helpful and professional!"
        )

        assert result.category == MessageCategory.POSITIVE
        assert 0.0 <= result.confidence <= 1.0


# ============================================================================
# Classifier Tests - NEGATIVE (2 test cases)
# ============================================================================

class TestClassifierNegative:
    """Test classifier correctly labels NEGATIVE feedback."""

    @pytest.mark.asyncio
    async def test_negative_complaint_message(self, test_db, mock_llm_client, mock_token_tracker, mock_audit_service):
        """Test that a complaint is classified as NEGATIVE."""
        mock_llm_client.complete.return_value = create_llm_response(
            json.dumps({
                "category": "negative",
                "confidence": 0.88,
                "reasoning": "Customer expressing frustration about fees"
            })
        )

        classifier = ClassifierAgent(
            db=test_db,
            llm_client=mock_llm_client,
            token_tracker=mock_token_tracker,
            audit_service=mock_audit_service,
        )

        result = await classifier.process(
            ticket_id="test-ticket-3",
            message="I'm extremely frustrated with the hidden fees on my account!"
        )

        assert result.category == MessageCategory.NEGATIVE
        assert result.confidence > 0.5

    @pytest.mark.asyncio
    async def test_negative_service_issue(self, test_db, mock_llm_client, mock_token_tracker, mock_audit_service):
        """Test that a service complaint is classified as NEGATIVE."""
        mock_llm_client.complete.return_value = create_llm_response(
            json.dumps({
                "category": "negative",
                "confidence": 0.91,
                "reasoning": "Customer unhappy with service quality"
            })
        )

        classifier = ClassifierAgent(
            db=test_db,
            llm_client=mock_llm_client,
            token_tracker=mock_token_tracker,
            audit_service=mock_audit_service,
        )

        result = await classifier.process(
            ticket_id="test-ticket-4",
            message="This is unacceptable! I've been waiting 3 hours for support!"
        )

        assert result.category == MessageCategory.NEGATIVE
        assert isinstance(result.reasoning, str)
        assert len(result.reasoning) > 0


# ============================================================================
# Classifier Tests - QUERY (2 test cases)
# ============================================================================

class TestClassifierQuery:
    """Test classifier correctly labels QUERY messages."""

    @pytest.mark.asyncio
    async def test_query_hours_question(self, test_db, mock_llm_client, mock_token_tracker, mock_audit_service):
        """Test that an hours question is classified as QUERY."""
        mock_llm_client.complete.return_value = create_llm_response(
            json.dumps({
                "category": "query",
                "confidence": 0.97,
                "reasoning": "Customer asking for information"
            })
        )

        classifier = ClassifierAgent(
            db=test_db,
            llm_client=mock_llm_client,
            token_tracker=mock_token_tracker,
            audit_service=mock_audit_service,
        )

        result = await classifier.process(
            ticket_id="test-ticket-5",
            message="What are your branch hours on weekends?"
        )

        assert result.category == MessageCategory.QUERY
        assert result.confidence > 0.8

    @pytest.mark.asyncio
    async def test_query_account_info(self, test_db, mock_llm_client, mock_token_tracker, mock_audit_service):
        """Test that an account info request is classified as QUERY."""
        mock_llm_client.complete.return_value = create_llm_response(
            json.dumps({
                "category": "query",
                "confidence": 0.89,
                "reasoning": "Customer requesting account information"
            })
        )

        classifier = ClassifierAgent(
            db=test_db,
            llm_client=mock_llm_client,
            token_tracker=mock_token_tracker,
            audit_service=mock_audit_service,
        )

        result = await classifier.process(
            ticket_id="test-ticket-6",
            message="How do I check my account balance online?"
        )

        assert result.category == MessageCategory.QUERY
        assert isinstance(result, ClassificationResult)


# ============================================================================
# Database Tests - Ticket Creation
# ============================================================================

class TestDatabaseTicketCreation:
    """Test that feedback creates tickets in the database."""

    @pytest.mark.asyncio
    async def test_negative_feedback_creates_ticket(self, test_db):
        """Test that negative feedback creates a ticket in the database."""
        ticket_service = TicketService(test_db)

        # Create a ticket for negative feedback
        ticket = await ticket_service.create_ticket(
            customer_id="customer-123",
            customer_message="I'm very unhappy with the service!",
            category=MessageCategory.NEGATIVE,
            priority=TicketPriority.HIGH,
        )

        # Verify ticket was created
        assert ticket.id is not None
        assert ticket.customer_id == "customer-123"
        assert ticket.category == MessageCategory.NEGATIVE
        assert ticket.status == TicketStatus.OPEN
        assert ticket.priority == TicketPriority.HIGH

        # Verify we can retrieve it from the database
        retrieved = await ticket_service.get_ticket(ticket.id)
        assert retrieved.id == ticket.id
        assert retrieved.customer_message == "I'm very unhappy with the service!"
        assert retrieved.category == MessageCategory.NEGATIVE

    @pytest.mark.asyncio
    async def test_ticket_persists_in_database(self, test_db):
        """Test that created tickets persist and can be queried."""
        ticket_repo = TicketRepository(test_db)

        # Create ticket directly via repository
        ticket = Ticket(
            customer_id="customer-456",
            customer_message="Terrible experience with your bank!",
            category=MessageCategory.NEGATIVE,
            priority=TicketPriority.CRITICAL,
        )

        await ticket_repo.create(ticket)

        # Query by customer
        customer_tickets = await ticket_repo.get_by_customer("customer-456")
        assert len(customer_tickets) == 1
        assert customer_tickets[0].category == MessageCategory.NEGATIVE

        # Query by category
        negative_tickets = await ticket_repo.get_by_category(MessageCategory.NEGATIVE)
        assert len(negative_tickets) >= 1
        assert any(t.id == ticket.id for t in negative_tickets)


# ============================================================================
# Query Handler Tests - Database Retrieval
# ============================================================================

class TestQueryHandlerDatabaseRetrieval:
    """Test that query handler retrieves tickets from database."""

    @pytest.mark.asyncio
    async def test_query_handler_retrieves_ticket(self, test_db, mock_llm_client, mock_token_tracker, mock_audit_service):
        """Test that query handler retrieves the ticket from database."""
        # First create a ticket in the database
        ticket_repo = TicketRepository(test_db)
        ticket = Ticket(
            customer_id="customer-789",
            customer_message="What are your hours?",
            category=MessageCategory.QUERY,
        )
        await ticket_repo.create(ticket)

        # Setup mock LLM response
        mock_llm_client.complete.return_value = create_llm_response(
            "Our branch hours are Monday-Friday 9am-5pm."
        )

        # Create query handler and process
        handler = QueryHandler(
            db=test_db,
            llm_client=mock_llm_client,
            token_tracker=mock_token_tracker,
            audit_service=mock_audit_service,
        )

        result = await handler.process(
            ticket_id=ticket.id,
            message="What are your hours?"
        )

        # Verify handler returned a response
        assert isinstance(result, HandlerResponse)
        assert result.response is not None
        assert len(result.response) > 0
        assert result.priority in [TicketPriority.LOW, TicketPriority.MEDIUM]

    @pytest.mark.asyncio
    async def test_query_handler_uses_customer_history(self, test_db, mock_llm_client, mock_token_tracker, mock_audit_service):
        """Test that query handler includes customer history context."""
        ticket_repo = TicketRepository(test_db)

        # Create previous ticket for the same customer
        old_ticket = Ticket(
            customer_id="customer-history-test",
            customer_message="Previous question about fees",
            category=MessageCategory.QUERY,
            status=TicketStatus.RESOLVED,
        )
        await ticket_repo.create(old_ticket)

        # Create current ticket
        current_ticket = Ticket(
            customer_id="customer-history-test",
            customer_message="New question about transfers",
            category=MessageCategory.QUERY,
        )
        await ticket_repo.create(current_ticket)

        # Setup mock - capture what's sent to LLM
        captured_messages = []
        async def capture_complete(**kwargs):
            captured_messages.append(kwargs.get("user_message", ""))
            return create_llm_response("Here's info about transfers.")

        mock_llm_client.complete = capture_complete

        handler = QueryHandler(
            db=test_db,
            llm_client=mock_llm_client,
            token_tracker=mock_token_tracker,
            audit_service=mock_audit_service,
        )

        await handler.process(
            ticket_id=current_ticket.id,
            message="New question about transfers"
        )

        # Verify history context was included
        assert len(captured_messages) == 1
        sent_message = captured_messages[0]
        assert "Previous interactions" in sent_message


# ============================================================================
# Chaos Mode Tests
# ============================================================================

class TestChaosMode:
    """Test that chaos mode triggers errors when enabled."""

    @pytest.mark.asyncio
    async def test_chaos_mode_triggers_errors(self, test_db, mock_llm_client):
        """Test that chaos mode can trigger ChaosError."""
        # We'll test the _maybe_trigger_chaos method directly
        orchestrator = Orchestrator(
            db=test_db,
            llm_client=mock_llm_client,
        )

        # Run many times with chaos mode enabled
        # With 30% probability, we should see at least one error in 50 attempts
        errors_triggered = 0
        for _ in range(50):
            try:
                orchestrator._maybe_trigger_chaos("TestComponent", chaos_mode=True)
            except ChaosError as e:
                errors_triggered += 1
                assert "CHAOS" in str(e)
                assert e.component == "TestComponent"

        # Statistical check: should trigger at least a few times out of 50
        assert errors_triggered > 0, "Chaos mode should trigger at least once in 50 attempts"
        assert errors_triggered < 50, "Chaos mode should not trigger every time"

    @pytest.mark.asyncio
    async def test_chaos_mode_disabled_no_errors(self, test_db, mock_llm_client):
        """Test that no errors occur when chaos mode is disabled."""
        orchestrator = Orchestrator(
            db=test_db,
            llm_client=mock_llm_client,
        )

        # Run many times with chaos mode disabled
        for _ in range(100):
            # Should never raise when chaos_mode=False
            orchestrator._maybe_trigger_chaos("TestComponent", chaos_mode=False)

        # If we get here without exception, test passed

    @pytest.mark.asyncio
    async def test_chaos_error_has_correct_attributes(self):
        """Test that ChaosError has the correct attributes."""
        error = ChaosError("Classifier", "Simulated timeout")

        assert error.component == "Classifier"
        assert "CHAOS" in str(error)
        assert "Classifier" in str(error)
        assert "Simulated timeout" in str(error)


# ============================================================================
# Test Runner
# ============================================================================

def run_all_tests():
    """Run all tests and print a summary, writing results to test_results.txt for CI."""
    from datetime import datetime
    from io import StringIO

    print("=" * 70)
    print("IntelliFlow SupportFlow Test Suite")
    print("=" * 70)
    print()

    # Capture output for test_results.txt
    output_capture = StringIO()

    # Run pytest programmatically
    exit_code = pytest.main([
        __file__,
        "-v",
        "--tb=short",
    ])

    # Build test results summary
    status = "PASS" if exit_code == 0 else "FAIL"
    summary = f"""Test Results Summary
{'=' * 50}
Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Status: {status}
Exit Code: {exit_code}

{'=' * 50}

Test Categories:
- Classifier POSITIVE: 2 tests
- Classifier NEGATIVE: 2 tests
- Classifier QUERY: 2 tests
- Database Ticket Creation: 2 tests
- Query Handler DB Retrieval: 2 tests
- Chaos Mode: 3 tests

Total: 13 tests

{'=' * 50}
"""

    # Write results to file for CI artifact upload
    results_path = Path(__file__).parent / "test_results.txt"
    with open(results_path, "w") as f:
        f.write(summary)

    print()
    print("=" * 70)
    if exit_code == 0:
        print("ALL TESTS PASSED")
    else:
        print(f"TESTS COMPLETED WITH EXIT CODE: {exit_code}")
    print("=" * 70)
    print(f"\nResults written to: {results_path}")

    return exit_code


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
