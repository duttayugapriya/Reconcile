"""
Reconcile — Tool Privilege Map (SINGLE SOURCE OF TRUTH)
=======================================================

DESIGN INTENT
-------------
Separation of privilege is a core security claim of this project, so the
"who may call what" rule must live in exactly ONE place. Both the MCP server
and the ADK `before_tool_callback` guardrail import from here. If these rules
were duplicated, they could drift — and a drift in a privilege table is a
security hole. One table, one truth.

The map is intentionally *allow-list* (default-deny): an agent may only call a
tool if that tool is explicitly listed for its role. Anything not listed is
blocked and logged by the guardrail.
"""

from __future__ import annotations
from enum import Enum


class Tool(str, Enum):
    """Canonical tool names. Using an enum (not bare strings) means a typo in
    an agent's allowed-set fails loudly at import, not silently at runtime."""
    GET_LEDGER_ENTRIES = "get_ledger_entries"
    FETCH_BANK_STATEMENT = "fetch_bank_statement"
    FETCH_INVOICES = "fetch_invoices"
    LOOKUP_VENDOR = "lookup_vendor"
    FLAG_TRANSACTION = "flag_transaction"
    POST_ADJUSTMENT = "post_adjustment"   # GATED — human confirmation required
    WRITE_AUDIT_LOG = "write_audit_log"


# Read-only tools shared by every agent that reads data.
_READ_TOOLS = {
    Tool.GET_LEDGER_ENTRIES,
    Tool.FETCH_BANK_STATEMENT,
    Tool.FETCH_INVOICES,
}

# Per-agent allow-lists. Keys MUST match the `name=` you give each ADK agent.
TOOL_SCOPES: dict[str, set[Tool]] = {
    # The orchestrator never touches state and never reads raw data directly;
    # it delegates. Empty set = it may call no MCP tools itself.
    "CloseOrchestrator": set(),

    # Ingestion pulls the three sources and normalizes them.
    "IngestionAgent": set(_READ_TOOLS),

    # Matching does 3-way matching and resolves vendor variants.
    "MatchingAgent": _READ_TOOLS | {Tool.LOOKUP_VENDOR},

    # Anomaly may read, resolve vendors, and FLAG (a safe write). It may
    # *propose* post_adjustment, but the guardrail forces that through the
    # human gate — proposing is not the same as having the privilege to post.
    "AnomalyAgent": _READ_TOOLS | {Tool.LOOKUP_VENDOR, Tool.FLAG_TRANSACTION},

    # Narrative may ONLY append to the audit log. It physically cannot move
    # money — this is the separation-of-privilege proof point in the demo.
    "NarrativeAgent": {Tool.WRITE_AUDIT_LOG},
}

# Tools that require human confirmation regardless of caller. The guardrail
# cross-checks this set so the gate can never be bypassed by a mis-scoped agent.
GATED_TOOLS: set[Tool] = {Tool.POST_ADJUSTMENT}

# Any single adjustment at/above this many cents is force-routed to human
# confirmation even if upstream logic believed it was safe. $10,000.00.
AMOUNT_CONFIRMATION_THRESHOLD_CENTS = 10_000_00


def is_allowed(agent_name: str, tool: Tool) -> bool:
    """Return True iff `agent_name` is permitted to call `tool`. Default-deny:
    an unknown agent name returns False (fail closed)."""
    return tool in TOOL_SCOPES.get(agent_name, set())
