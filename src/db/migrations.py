"""Database schema migrations."""

from .connection import DatabaseConnection
from ..utils.logger import get_logger

logger = get_logger(__name__)

# SQL statements for creating tables
CREATE_TICKETS_TABLE = """
CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    customer_message TEXT NOT NULL,
    category TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    priority INTEGER NOT NULL DEFAULT 3,
    agent_response TEXT,
    handler_agent TEXT,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_at TEXT
);
"""

CREATE_AUDIT_LOGS_TABLE = """
CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    ticket_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    action TEXT NOT NULL,
    input_summary TEXT NOT NULL,
    output_summary TEXT NOT NULL,
    decision_reasoning TEXT,
    confidence_score REAL,
    duration_ms INTEGER DEFAULT 0,
    success INTEGER DEFAULT 1,
    error_message TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (ticket_id) REFERENCES tickets(id)
);
"""

CREATE_TOKEN_USAGE_TABLE = """
CREATE TABLE IF NOT EXISTS token_usage (
    id TEXT PRIMARY KEY,
    ticket_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    model_name TEXT NOT NULL,
    provider TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    input_cost_usd REAL DEFAULT 0.0,
    output_cost_usd REAL DEFAULT 0.0,
    cached_tokens INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (ticket_id) REFERENCES tickets(id)
);
"""

CREATE_MODEL_PRICING_TABLE = """
CREATE TABLE IF NOT EXISTS model_pricing (
    model_name TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    input_cost_per_1k REAL NOT NULL,
    output_cost_per_1k REAL NOT NULL,
    cached_input_cost_per_1k REAL DEFAULT 0.0,
    updated_at TEXT NOT NULL
);
"""

# Indexes for common queries
CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_tickets_customer_id ON tickets(customer_id);",
    "CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);",
    "CREATE INDEX IF NOT EXISTS idx_tickets_category ON tickets(category);",
    "CREATE INDEX IF NOT EXISTS idx_tickets_created_at ON tickets(created_at);",
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_ticket_id ON audit_logs(ticket_id);",
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_agent_name ON audit_logs(agent_name);",
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);",
    "CREATE INDEX IF NOT EXISTS idx_token_usage_ticket_id ON token_usage(ticket_id);",
    "CREATE INDEX IF NOT EXISTS idx_token_usage_agent_name ON token_usage(agent_name);",
    "CREATE INDEX IF NOT EXISTS idx_token_usage_created_at ON token_usage(created_at);",
]

# Default model pricing data
DEFAULT_MODEL_PRICING = [
    # OpenAI models
    ("gpt-4o", "openai", 0.0025, 0.01, 0.00125),
    ("gpt-4o-mini", "openai", 0.00015, 0.0006, 0.000075),
    ("gpt-4-turbo", "openai", 0.01, 0.03, 0.005),
    ("gpt-3.5-turbo", "openai", 0.0005, 0.0015, 0.00025),
    # Anthropic models
    ("claude-3-opus-20240229", "anthropic", 0.015, 0.075, 0.0075),
    ("claude-3-sonnet-20240229", "anthropic", 0.003, 0.015, 0.0015),
    ("claude-3-haiku-20240307", "anthropic", 0.00025, 0.00125, 0.000125),
    ("claude-3-5-sonnet-20241022", "anthropic", 0.003, 0.015, 0.0015),
]


async def run_migrations(db: DatabaseConnection) -> None:
    """Run all database migrations.

    Args:
        db: Database connection instance
    """
    logger.info("running_migrations")

    # Create tables
    await db.execute(CREATE_TICKETS_TABLE)
    logger.debug("created_table", table="tickets")

    await db.execute(CREATE_AUDIT_LOGS_TABLE)
    logger.debug("created_table", table="audit_logs")

    await db.execute(CREATE_TOKEN_USAGE_TABLE)
    logger.debug("created_table", table="token_usage")

    await db.execute(CREATE_MODEL_PRICING_TABLE)
    logger.debug("created_table", table="model_pricing")

    # Create indexes
    for index_sql in CREATE_INDEXES:
        await db.execute(index_sql)

    logger.debug("created_indexes")

    # Insert default pricing data
    await _seed_model_pricing(db)

    logger.info("migrations_complete")


async def _seed_model_pricing(db: DatabaseConnection) -> None:
    """Seed the model pricing table with default data.

    Args:
        db: Database connection instance
    """
    from datetime import datetime

    now = datetime.utcnow().isoformat()

    for model_name, provider, input_cost, output_cost, cached_cost in DEFAULT_MODEL_PRICING:
        # Use INSERT OR REPLACE to handle existing entries
        await db.execute(
            """
            INSERT OR REPLACE INTO model_pricing
            (model_name, provider, input_cost_per_1k, output_cost_per_1k, cached_input_cost_per_1k, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (model_name, provider, input_cost, output_cost, cached_cost, now),
        )

    logger.debug("seeded_model_pricing", count=len(DEFAULT_MODEL_PRICING))
