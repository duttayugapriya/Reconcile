"""
Reconcile — MCP client toolsets (per-agent, filtered)
=====================================================

DESIGN INTENT
-------------
Agents are MCP *clients*: they reach the seven server tools over stdio via
McpToolset. We build a SEPARATE toolset per agent with a `tool_filter` that
exposes ONLY the tools that agent is allowed to call (defense in depth: the
guardrail enforces scope at call time, and the filter prevents the model from
ever *seeing* a tool it may not use — a tool it can't see, it can't propose).

CRITICAL INVARIANT: `post_adjustment` is NEVER in any toolset's filter. The
only path to posting money is the gated FunctionTool on the CloseOrchestrator
(security/confirmation.py). Raw `_mcp_post_adjustment` stays off the agent graph.

API NOTE (verified vs current ADK docs):
    from google.adk.tools.mcp_tool import McpToolset
    from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
    from mcp import StdioServerParameters
"""

from __future__ import annotations

import sys
from pathlib import Path

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

# Repo root, so the stdio subprocess launches `python -m mcp_server.server`
# from the correct working directory regardless of where adk is invoked.
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _make_toolset(allowed: list[str]) -> McpToolset:
    """Build an McpToolset that launches our server over stdio and exposes
    ONLY `allowed` tool names. `post_adjustment` must never appear in `allowed`."""
    assert "post_adjustment" not in allowed, (
        "post_adjustment must never be exposed via McpToolset — it is gated "
        "behind the human-confirmation FunctionTool on the orchestrator only."
    )
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,            # same venv python
                args=["-m", "mcp_server.server"],  # our FastMCP stdio server
                cwd=str(_REPO_ROOT),
            ),
        ),
        tool_filter=allowed,
    )


# Per-agent toolsets. Names match the MCP @mcp.tool() function names, which in
# turn match the Tool enum values the guardrail checks against.
READ_TOOLS = ["get_ledger_entries", "fetch_bank_statement", "fetch_invoices"]


def ingestion_toolset() -> McpToolset:
    return _make_toolset(READ_TOOLS)


def matching_toolset() -> McpToolset:
    return _make_toolset(READ_TOOLS + ["lookup_vendor"])


def anomaly_toolset() -> McpToolset:
    # read + vendor lookup + the SAFE flag write. No post_adjustment.
    return _make_toolset(READ_TOOLS + ["lookup_vendor", "flag_transaction"])


def narrative_toolset() -> McpToolset:
    # append-only audit log ONLY.
    return _make_toolset(["write_audit_log"])
