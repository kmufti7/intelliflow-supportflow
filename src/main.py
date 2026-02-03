"""Main entry point for IntelliFlow SupportFlow."""

import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

from .config import get_settings
from .db.connection import get_database, close_database
from .db.migrations import run_migrations
from .llm.client import get_llm_client, close_llm_client
from .agents.orchestrator import Orchestrator
from .utils.logger import setup_logging, get_logger


async def initialize() -> Orchestrator:
    """Initialize all components.

    Returns:
        Configured Orchestrator instance
    """
    # Load environment variables
    load_dotenv()

    # Get settings
    settings = get_settings()

    # Setup logging
    setup_logging(level=settings.log_level, log_format=settings.log_format)

    logger = get_logger("main")
    logger.info(
        "initializing",
        app_name=settings.app_name,
        provider=settings.llm_provider.value,
        model=settings.active_model,
    )

    # Validate configuration
    settings.validate_api_keys()

    # Initialize database
    db = await get_database(settings.database_path)

    # Run migrations
    await run_migrations(db)

    # Initialize LLM client
    llm_client = get_llm_client(settings)

    # Create orchestrator
    orchestrator = Orchestrator(db=db, llm_client=llm_client)

    logger.info("initialization_complete")

    return orchestrator


async def cleanup() -> None:
    """Cleanup resources."""
    logger = get_logger("main")
    logger.info("cleaning_up")

    await close_llm_client()
    await close_database()

    logger.info("cleanup_complete")


async def run_demo() -> None:
    """Run a demonstration of the support flow system."""
    orchestrator = await initialize()
    logger = get_logger("demo")

    print("\n" + "=" * 60)
    print("IntelliFlow SupportFlow Demo")
    print("=" * 60 + "\n")

    # Test messages for each category
    test_messages = [
        {
            "customer_id": "CUST001",
            "message": "Thank you for the excellent service! Your mobile app is amazing and made my banking so much easier.",
            "expected_category": "positive",
        },
        {
            "customer_id": "CUST002",
            "message": "I'm very frustrated with the unexpected fees on my account! I was charged $35 for something I don't understand.",
            "expected_category": "negative",
        },
        {
            "customer_id": "CUST003",
            "message": "What are your branch hours? I need to visit to open a new savings account.",
            "expected_category": "query",
        },
    ]

    results = []

    for test in test_messages:
        print(f"\n{'-' * 50}")
        print(f"Customer: {test['customer_id']}")
        print(f"Message: {test['message']}")
        print(f"Expected Category: {test['expected_category']}")
        print("-" * 50)

        try:
            result = await orchestrator.process_message(
                customer_id=test["customer_id"],
                message=test["message"],
            )

            print(f"\nClassification:")
            print(f"  Category: {result.classification.category.value}")
            print(f"  Confidence: {result.classification.confidence:.2f}")
            print(f"  Reasoning: {result.classification.reasoning}")

            print(f"\nHandler: {result.handler_used}")
            print(f"Priority: {result.ticket.priority.value}")
            print(f"Status: {result.ticket.status.value}")

            if result.requires_escalation:
                print(f"[!]  ESCALATION REQUIRED: {result.escalation_reason}")

            print(f"\nResponse:")
            print(f"  {result.response}")

            print(f"\nTicket ID: {result.ticket.id}")

            # Get ticket details including costs
            details = await orchestrator.get_ticket_details(result.ticket.id)
            print(f"Total Cost: ${details['total_cost_usd']:.6f}")

            results.append({
                "customer_id": test["customer_id"],
                "ticket_id": result.ticket.id,
                "category": result.classification.category.value,
                "expected": test["expected_category"],
                "match": result.classification.category.value == test["expected_category"],
                "cost_usd": details["total_cost_usd"],
            })

        except Exception as e:
            logger.error("demo_error", error=str(e), customer_id=test["customer_id"])
            print(f"\n[X] Error processing message: {e}")

    # Print summary
    print("\n" + "=" * 60)
    print("Demo Summary")
    print("=" * 60)

    total_cost = sum(r["cost_usd"] for r in results)
    matches = sum(1 for r in results if r["match"])

    print(f"\nMessages processed: {len(results)}")
    print(f"Classification accuracy: {matches}/{len(results)}")
    print(f"Total cost: ${total_cost:.6f}")

    # Get overall statistics
    stats = await orchestrator.get_statistics()
    print("\nSystem Statistics:")
    print(f"  Total tickets: {stats['tickets']['total_tickets']}")
    print(f"  By category: {json.dumps(stats['tickets']['by_category'], indent=4)}")
    print(f"  Total tokens used: {stats['usage']['total_tokens']}")
    print(f"  Total API cost: ${stats['usage']['total_cost_usd']:.6f}")

    print("\nCost by agent:")
    for agent, cost in stats["cost_by_agent"].items():
        print(f"  {agent}: ${cost:.6f}")

    await cleanup()

    print("\n" + "=" * 60)
    print("Demo Complete!")
    print("=" * 60 + "\n")


async def interactive_mode() -> None:
    """Run in interactive mode."""
    orchestrator = await initialize()

    print("\n" + "=" * 60)
    print("IntelliFlow SupportFlow - Interactive Mode")
    print("=" * 60)
    print("\nType your message and press Enter. Type 'quit' to exit.")
    print("Type 'stats' to see system statistics.\n")

    customer_id = "INTERACTIVE_USER"

    try:
        while True:
            message = input("\nYou: ").strip()

            if not message:
                continue

            if message.lower() == "quit":
                break

            if message.lower() == "stats":
                stats = await orchestrator.get_statistics()
                print("\nSystem Statistics:")
                print(json.dumps(stats, indent=2, default=str))
                continue

            try:
                result = await orchestrator.process_message(
                    customer_id=customer_id,
                    message=message,
                )

                print(f"\n[{result.classification.category.value.upper()}] ", end="")
                print(f"(confidence: {result.classification.confidence:.2f})")
                print(f"\nAgent: {result.response}")

                if result.requires_escalation:
                    print(f"\n[!]  This issue has been escalated: {result.escalation_reason}")

                # Get cost
                details = await orchestrator.get_ticket_details(result.ticket.id)
                print(f"\n[Cost: ${details['total_cost_usd']:.6f}]")

            except Exception as e:
                print(f"\n[X] Error: {e}")

    finally:
        await cleanup()


def main() -> None:
    """Main entry point."""
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        asyncio.run(interactive_mode())
    else:
        asyncio.run(run_demo())


if __name__ == "__main__":
    main()
