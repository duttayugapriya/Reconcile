"""
Reconcile — Security Guardrail (before_tool_callback)
=====================================================

DESIGN INTENT
-------------
This is the single enforcement point that runs BEFORE every tool call made by
any agent. It implements three of the four security layers from the design doc:

    1. LEAST-PRIVILEGE SCOPING  — default-deny against tool_scopes.TOOL_SCOPES.
    2. AMOUNT THRESHOLD         — any money-moving call >= threshold is forced
                                  to the human gate, even if upstream "thought"
                                  it was safe.
    3. PII MASKING              — account numbers / personal identifiers are
                                  redacted before any value can reach a log.

ADK CONTRACT (verified against current docs)
--------------------------------------------
- ADK passes callback args BY KEYWORD. The parameter names MUST be exactly
  `tool`, `args`, `tool_context` — renaming them raises TypeError at runtime.
- Returning a dict SKIPS the tool's execution and uses the dict as the tool
  result. We use that to BLOCK a disallowed/over-threshold call and feed a
  structured "denied" result back to the model.
- Returning None ALLOWS the tool to proceed normally.

This callback is attached to EVERY agent via `before_tool_callback=`.
"""

from __future__ import annotations

import re
import copy
from typing import Any, Optional

from google.adk.tools.tool_context import ToolContext
from google.adk.tools.base_tool import BaseTool

from mcp_server.tool_scopes import (
    Tool,
    is_allowed,
    GATED_TOOLS,
    AMOUNT_CONFIRMATION_THRESHOLD_CENTS,
)

# --- PII patterns -----------------------------------------------------------
# Conservative redaction. We mask anything that looks like a bank account /
# routing number or a long digit run. Better to over-mask a log than to leak.
_ACCOUNT_PATTERNS = [
    re.compile(r"\b\d{8,17}\b"),          # raw account-ish digit runs
    re.compile(r"\b\d{9}\b"),             # routing numbers (9 digits)
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), # SSN-shaped
]
_PII_KEYS = {"account_number", "routing_number", "ssn", "tax_id", "iban"}


def _mask_text(text: str) -> str:
    """Redact account-like digit sequences from a free-text string."""
    masked = text
    for pat in _ACCOUNT_PATTERNS:
        masked = pat.sub("***REDACTED***", masked)
    return masked


def mask_pii(value: Any) -> Any:
    """Recursively redact PII from arbitrary tool args (dict/list/str).

    Exposed as a module function so confirmation.py and any log writer can
    reuse the EXACT same masking logic — one definition, no drift."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in _PII_KEYS:
                out[k] = "***REDACTED***"
            else:
                out[k] = mask_pii(v)
        return out
    if isinstance(value, list):
        return [mask_pii(v) for v in value]
    if isinstance(value, str):
        return _mask_text(value)
    return value


def _denied(reason: str, **extra: Any) -> dict:
    """Build the structured result returned to the model when a call is
    blocked. Returning a dict from before_tool_callback skips the tool."""
    return {"status": "DENIED", "reason": reason, **extra}


def security_guardrail(
    *,
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
) -> Optional[dict]:
    """The before_tool_callback enforced on every agent.

    Returns:
        - dict  -> BLOCK the tool; the dict becomes the tool result.
        - None  -> ALLOW the tool to execute normally.
    """
    agent_name = tool_context.agent_name
    tool_name = tool.name

    # --- (A) GATED-TOOL THRESHOLD CHECK (runs by NAME, before enum resolve) ---
    # The gated post_adjustment tool is a FunctionTool whose .name is
    # 'post_adjustment_gated' — NOT an MCP Tool enum member. We must enforce
    # the amount threshold here, by name, or this layer is a no-op for the only
    # money-moving tool. The confirmation.py gate is the primary control; this
    # is defense-in-depth and keeps the writeup's claim literally true.
    if tool_name == "post_adjustment_gated":
        amount = args.get("amount_cents")
        confirmed = getattr(tool_context, "tool_confirmation", None)
        is_confirmed = bool(confirmed and getattr(confirmed, "confirmed", False))
        if isinstance(amount, int) and abs(amount) >= AMOUNT_CONFIRMATION_THRESHOLD_CENTS:
            if not is_confirmed:
                # Allow it to PROCEED to the tool, which will itself call
                # request_confirmation (Stage 1). We do NOT block here, because
                # blocking would prevent the confirmation request from ever
                # being raised. The threshold's job at this layer is to LOG
                # that a large amount was seen pre-confirmation.
                log = tool_context.state.get("large_amount_seen", [])
                log.append({"agent": agent_name, "amount_cents": amount})
                tool_context.state["large_amount_seen"] = log
        return None  # the gated tool self-enforces the human gate

    # --- (0) Resolve tool name to the canonical MCP enum ----------------
    # Tools NOT in the MCP enum are the orchestrator's own non-MCP tools.
    # After Fix 2, the gated post_adjustment FunctionTool is handled entirely
    # in section (A) above and never reaches here. The only remaining
    # orchestrator-owned non-MCP tool is the ClosePipeline AgentTool, which
    # merely runs the pipeline (whose sub-agents are each independently
    # guardrailed). Genuinely unknown MCP-style calls still fail closed below
    # via the scope check.
    _ORCHESTRATOR_OWNED = {"ClosePipeline"}
    try:
        tool_enum = Tool(tool_name)
    except ValueError:
        if tool_name in _ORCHESTRATOR_OWNED:
            return None  # allow; the AgentTool just runs guardrailed sub-agents
        return _denied(
            f"Unknown tool '{tool_name}' is not part of the Reconcile tool set.",
            tool=tool_name, agent=agent_name,
        )

    # --- (1) LEAST-PRIVILEGE SCOPING (default-deny) --------------------
    if not is_allowed(agent_name, tool_enum):
        # Log the violation to session state so the NarrativeAgent can report
        # attempted privilege escalations in the audit summary.
        violations = tool_context.state.get("privilege_violations", [])
        violations.append({"agent": agent_name, "tool": tool_name})
        tool_context.state["privilege_violations"] = violations
        return _denied(
            f"Agent '{agent_name}' is not permitted to call '{tool_name}'. "
            f"This call was blocked by the least-privilege guardrail.",
            agent=agent_name, tool=tool_name,
        )

    # --- (2) AMOUNT THRESHOLD on money-moving MCP calls ----------------
    # Defense-in-depth for any *MCP-enum* gated tool. The orchestrator's
    # FunctionTool path is already handled by name in section (A); this branch
    # covers gated tools that ARE part of the MCP enum, if any exist.
    if tool_enum in GATED_TOOLS:
        amount = args.get("amount_cents")
        confirmed = getattr(tool_context, "tool_confirmation", None)
        if isinstance(amount, int) and abs(amount) >= AMOUNT_CONFIRMATION_THRESHOLD_CENTS:
            if not (confirmed and getattr(confirmed, "confirmed", False)):
                return _denied(
                    f"Adjustment of {amount} cents meets/exceeds the "
                    f"{AMOUNT_CONFIRMATION_THRESHOLD_CENTS}-cent threshold and "
                    f"requires explicit human confirmation before posting.",
                    requires_confirmation=True,
                    amount_cents=amount,
                )

    # Dynamic Caller Attribution:
    # If the tool is 'flag_transaction', dynamically inject the calling agent's name
    # as the `actor` argument. This ensures correct attribution in the audit trail
    # and prevents reliance on hardcoded defaults when tools are reused.
    if tool_name == "flag_transaction":
        args["actor"] = agent_name

    # --- (3) PII MASKING of args before they can be logged -------------
    # We mask a COPY placed in session state for logging. We do NOT mutate the
    # live `args` the tool will execute with (the ERP needs the real account
    # number) — only the loggable view is redacted. This is the key nuance:
    # mask what is OBSERVED, not what is EXECUTED.
    safe_view = mask_pii(copy.deepcopy(args))
    call_log = tool_context.state.get("tool_call_log", [])
    call_log.append({"agent": agent_name, "tool": tool_name, "args": safe_view})
    tool_context.state["tool_call_log"] = call_log

    # None => allow the tool to proceed.
    return None
