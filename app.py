"""Streamlit app for IntelliFlow SupportFlow."""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

from src.config import get_settings
from src.db.connection import get_database, close_database
from src.db.migrations import run_migrations
from src.llm.client import get_llm_client
from src.agents.orchestrator import Orchestrator


# Page configuration
st.set_page_config(
    page_title="IntelliFlow OS: SupportFlow",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for styling
st.markdown("""
<style>
    .main-title {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1E3A5F;
        margin-bottom: 0;
    }
    .subtitle {
        font-size: 1.1rem;
        color: #666;
        margin-top: 0;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .metric-value {
        font-size: 1.8rem;
        font-weight: 700;
    }
    .metric-label {
        font-size: 0.85rem;
        opacity: 0.9;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 1rem;
    }
    .user-message {
        background-color: #E3F2FD;
        border-left: 4px solid #2196F3;
    }
    .agent-message {
        background-color: #F5F5F5;
        border-left: 4px solid #4CAF50;
    }
    .classification-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 15px;
        font-size: 0.8rem;
        font-weight: 600;
        margin-right: 0.5rem;
    }
    .positive-badge {
        background-color: #C8E6C9;
        color: #2E7D32;
    }
    .negative-badge {
        background-color: #FFCDD2;
        color: #C62828;
    }
    .query-badge {
        background-color: #BBDEFB;
        color: #1565C0;
    }
    .governance-log {
        background-color: #1E1E1E;
        color: #D4D4D4;
        padding: 1rem;
        border-radius: 10px;
        font-family: 'Consolas', 'Monaco', monospace;
        font-size: 0.85rem;
        max-height: 600px;
        overflow-y: auto;
    }
    .log-entry {
        padding: 0.5rem 0;
        border-bottom: 1px solid #333;
    }
    .log-timestamp {
        color: #888;
    }
    .log-success {
        color: #4EC9B0;
    }
    .log-fail {
        color: #F14C4C;
    }
    .log-component {
        color: #DCDCAA;
    }
    .log-action {
        color: #9CDCFE;
    }
    .stButton > button {
        width: 100%;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        padding: 0.75rem 1.5rem;
        font-weight: 600;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #5a6fd6 0%, #6a4190 100%);
    }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """Initialize session state variables."""
    if "initialized" not in st.session_state:
        st.session_state.initialized = False
    if "orchestrator" not in st.session_state:
        st.session_state.orchestrator = None
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "governance_logs" not in st.session_state:
        st.session_state.governance_logs = []
    if "total_tokens" not in st.session_state:
        st.session_state.total_tokens = 0
    if "session_cost" not in st.session_state:
        st.session_state.session_cost = 0.0
    if "tickets_created" not in st.session_state:
        st.session_state.tickets_created = 0
    if "customer_id" not in st.session_state:
        st.session_state.customer_id = f"STREAMLIT_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    if "chaos_mode" not in st.session_state:
        st.session_state.chaos_mode = False


async def initialize_system():
    """Initialize the orchestrator and database."""
    load_dotenv()
    settings = get_settings()

    db = await get_database(settings.database_path)
    await run_migrations(db)

    llm_client = get_llm_client(settings)
    orchestrator = Orchestrator(db=db, llm_client=llm_client)

    return orchestrator


def add_governance_log(component: str, action: str, success: bool, details: str = ""):
    """Add an entry to the governance log."""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    st.session_state.governance_logs.insert(0, {
        "timestamp": timestamp,
        "component": component,
        "action": action,
        "success": success,
        "details": details,
    })
    # Keep only last 100 entries
    st.session_state.governance_logs = st.session_state.governance_logs[:100]


async def process_message(message: str):
    """Process a customer message through the orchestrator."""
    orchestrator = st.session_state.orchestrator
    chaos_mode = st.session_state.chaos_mode

    add_governance_log(
        "Orchestrator",
        "Received message",
        True,
        f"Length: {len(message)}" + (" [CHAOS MODE]" if chaos_mode else "")
    )

    try:
        # Process the message
        add_governance_log("Classifier", "Classifying message", True)

        result = await orchestrator.process_message(
            customer_id=st.session_state.customer_id,
            message=message,
            chaos_mode=chaos_mode,
        )

        # Log classification
        add_governance_log(
            "Classifier",
            f"Classified as {result.classification.category.value}",
            True,
            f"Confidence: {result.classification.confidence:.2f}"
        )

        # Log routing
        add_governance_log(
            "Router",
            f"Routed to {result.handler_used}",
            True,
            f"Priority: {result.ticket.priority.value}"
        )

        # Log response generation
        add_governance_log(
            result.handler_used,
            "Generated response",
            True,
            f"Length: {len(result.response)}"
        )

        # Log policy citations if any
        if result.cited_policies:
            policy_ids = ", ".join(p.id for p in result.cited_policies)
            add_governance_log(
                "PolicyService",
                f"Cited {len(result.cited_policies)} policies",
                True,
                policy_ids
            )

        # Get ticket details for cost
        details = await orchestrator.get_ticket_details(result.ticket.id)

        # Update session metrics
        st.session_state.tickets_created += 1
        st.session_state.session_cost += details["total_cost_usd"]

        # Calculate tokens from usage records
        for usage in details["token_usage"]:
            st.session_state.total_tokens += usage["input_tokens"] + usage["output_tokens"]

        # Log ticket creation
        add_governance_log(
            "Database",
            "Ticket created",
            True,
            f"ID: {result.ticket.id[:8]}..."
        )

        # Add to chat history
        st.session_state.chat_history.append({
            "role": "user",
            "content": message,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        })

        # Format cited policies for storage
        cited_policies = [
            {"id": p.id, "title": p.title, "content": p.content}
            for p in result.cited_policies
        ] if result.cited_policies else []

        st.session_state.chat_history.append({
            "role": "agent",
            "content": result.response,
            "category": result.classification.category.value,
            "confidence": result.classification.confidence,
            "handler": result.handler_used,
            "ticket_id": result.ticket.id,
            "cost": details["total_cost_usd"],
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "cited_policies": cited_policies,
        })

        if result.requires_escalation:
            add_governance_log(
                "Escalation",
                "Ticket escalated",
                True,
                result.escalation_reason or ""
            )

        return True

    except Exception as e:
        add_governance_log("System", f"Error: {str(e)[:50]}", False)
        st.error(f"Error processing message: {e}")
        return False


def render_chat_message(msg):
    """Render a single chat message."""
    if msg["role"] == "user":
        st.markdown(f"""
        <div class="chat-message user-message">
            <strong>Customer</strong> <span style="color: #888; font-size: 0.8rem;">({msg['timestamp']})</span>
            <p style="margin: 0.5rem 0 0 0;">{msg['content']}</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        category = msg.get("category", "query")
        badge_class = f"{category}-badge"

        st.markdown(f"""
        <div class="chat-message agent-message">
            <div style="margin-bottom: 0.5rem;">
                <span class="classification-badge {badge_class}">{category.upper()}</span>
                <span style="color: #888; font-size: 0.8rem;">
                    Confidence: {msg.get('confidence', 0):.0%} |
                    Handler: {msg.get('handler', 'unknown')} |
                    Cost: ${msg.get('cost', 0):.6f}
                </span>
            </div>
            <p style="margin: 0;">{msg['content']}</p>
        </div>
        """, unsafe_allow_html=True)

        # Render policy section using native Streamlit formatting
        cited_policies = msg.get("cited_policies", [])
        if cited_policies:
            with st.container():
                st.markdown(f"**Policy Referenced ({len(cited_policies)})**")
                for policy in cited_policies:
                    st.markdown(f"- **{policy['id']}**: {policy['title']}")


def render_governance_log():
    """Render the governance log panel."""
    if not st.session_state.governance_logs:
        st.info("No activity yet. Send a message to begin.")
        return

    # Build plain text log entries
    log_lines = []
    for entry in st.session_state.governance_logs:
        status = "OK" if entry["success"] else "ERROR"
        details = f' - {entry["details"]}' if entry["details"] else ""
        line = f'{entry["timestamp"]} [{status:5}] [{entry["component"]}] {entry["action"]}{details}'
        log_lines.append(line)

    # Display as code block for monospace formatting
    log_text = "\n".join(log_lines)
    st.code(log_text, language=None)


def main():
    """Main Streamlit app."""
    init_session_state()

    # Initialize system if needed
    if not st.session_state.initialized:
        with st.spinner("Initializing IntelliFlow SupportFlow..."):
            try:
                st.session_state.orchestrator = asyncio.run(initialize_system())
                st.session_state.initialized = True
                add_governance_log("System", "Initialized successfully", True)
            except Exception as e:
                st.error(f"Failed to initialize: {e}")
                st.stop()

    # Sidebar settings
    with st.sidebar:
        st.markdown("### Settings")
        st.session_state.chaos_mode = st.toggle(
            "Chaos Mode",
            value=st.session_state.chaos_mode,
            help="Enable random failures to test system resilience"
        )
        if st.session_state.chaos_mode:
            st.warning("Chaos Mode is ON - random failures may occur!")

    # Header
    st.markdown('<h1 class="main-title">IntelliFlow OS: SupportFlow Module</h1>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Governed Multi-Agent Workflow for Banking Support</p>', unsafe_allow_html=True)

    # Metrics bar
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{st.session_state.total_tokens:,}</div>
            <div class="metric-label">Total Tokens</div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">${st.session_state.session_cost:.6f}</div>
            <div class="metric-label">Session Cost</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{st.session_state.tickets_created}</div>
            <div class="metric-label">Tickets Created</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Main content - two columns
    left_col, right_col = st.columns([6, 4])

    # Left column - Chat interface
    with left_col:
        st.markdown("### Chat Interface")

        # Chat history container
        chat_container = st.container()

        with chat_container:
            if st.session_state.chat_history:
                for msg in st.session_state.chat_history:
                    render_chat_message(msg)
            else:
                st.markdown("""
                <div style="text-align: center; color: #888; padding: 2rem; background: #f9f9f9; border-radius: 10px;">
                    <p style="font-size: 1.1rem;">Welcome to IntelliFlow SupportFlow</p>
                    <p>Enter a customer message below to begin. Try messages like:</p>
                    <ul style="text-align: left; display: inline-block;">
                        <li>"Thank you for the excellent service!"</li>
                        <li>"I'm frustrated with the fees on my account!"</li>
                        <li>"What are your branch hours?"</li>
                    </ul>
                </div>
                """, unsafe_allow_html=True)

        # Input area
        st.markdown("<br>", unsafe_allow_html=True)

        with st.form(key="message_form", clear_on_submit=True):
            user_input = st.text_area(
                "Customer Message",
                placeholder="Enter customer message here...",
                height=100,
                label_visibility="collapsed",
            )

            submit_button = st.form_submit_button("Send Message")

            if submit_button and user_input.strip():
                with st.spinner("Processing message..."):
                    asyncio.run(process_message(user_input.strip()))
                st.rerun()

    # Right column - Governance Log
    with right_col:
        st.markdown("### Governance Log")
        render_governance_log()

        # Refresh button
        if st.button("Clear Logs", key="clear_logs"):
            st.session_state.governance_logs = []
            add_governance_log("System", "Logs cleared", True)
            st.rerun()


if __name__ == "__main__":
    main()
