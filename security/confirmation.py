"""
Reconcile — Human-in-the-Loop Confirmation Gate
===============================================

DESIGN INTENT
-------------
`post_adjustment` is the ONLY money-moving tool. It must never execute without
explicit human sign-off. We implement this with ADK's native *advanced*
tool-confirmation flow (verified against ADK Python >= 1.14.0):

    Stage 1 (request): no confirmation present yet -> call
        tool_context.request_confirmation(hint=..., payload=...) and return an
        intermediate "awaiting approval" status. ADK pauses the invocation and
        surfaces the request to the human (ADK web dialog, CLI, or REST /run_sse).

    Stage 2 (resume): the human's response arrives in
        tool_context.tool_confirmation. If confirmed -> post via the MCP
        primitive and write the audit record. If rejected -> post nothing and
        record the rejection (the $40k "mark for manual review" demo beat).

This tool is registered on the CloseOrchestrator ONLY, wrapped as a FunctionTool
with require_confirmation logic handled INSIDE the function (advanced pattern),
so the gate is part of the tool's own contract and cannot be bypassed.

NOTE ON SESSIONS: ADK's confirmation feature does NOT support
DatabaseSessionService or VertexAiSessionService. Run Reconcile with
InMemorySessionService (reflect this in deploy/README_deploy.md).
"""

from __future__ import annotations

from typing import Any

from google.adk.tools.tool_context import ToolContext
from google.adk.tools import FunctionTool

from mcp_server.tool_scopes import AMOUNT_CONFIRMATION_THRESHOLD_CENTS
from security.guardrails import mask_pii

# We call the MCP primitive directly here. In the wired-up system this can be
# the MCPToolset-exposed tool; importing the primitive keeps the HITL logic
# unit-testable without a running MCP subprocess.
from mcp_server.server import post_adjustment as _mcp_post_adjustment
from mcp_server.server import _write_audit


def post_adjustment_gated(
    entry_txn_id: str,
    amount_cents: int,
    reason: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Propose and (only on human approval) POST a correcting adjustment.

    Args:
        entry_txn_id: the transaction the adjustment corrects.
        amount_cents: signed integer cents (negative reverses a payment).
        reason: human-readable justification shown to the approver.

    Returns a status dict describing the outcome (awaiting / posted / rejected).
    """
    confirmation = tool_context.tool_confirmation

    # --- STAGE 1: no decision yet -> request human confirmation --------
    if not confirmation:
        # Build a clear, auditable hint. Mask in case the reason carries PII.
        over_threshold = abs(amount_cents) >= AMOUNT_CONFIRMATION_THRESHOLD_CENTS
        hint = (
            f"APPROVAL REQUIRED — post_adjustment\n"
            f"  Transaction : {entry_txn_id}\n"
            f"  Amount      : {amount_cents} cents "
            f"({'reversal' if amount_cents < 0 else 'increase'})\n"
            f"  Reason      : {mask_pii(reason)}\n"
            f"  {'[Exceeds auto-threshold] ' if over_threshold else ''}"
            f"Approve to post this correcting entry, or reject to mark the "
            f"item for manual review. No money moves without your approval."
        )
        tool_context.request_confirmation(
            hint=hint,
            # payload defines the structured response we expect back. Defaults
            # represent the "rejected / nothing approved" safe state.
            payload={"approved": False, "approved_amount_cents": None},
        )
        # Intermediate status — the model sees this only after the turn resumes.
        return {
            "status": "AWAITING_HUMAN_APPROVAL",
            "entry_txn_id": entry_txn_id,
            "proposed_amount_cents": amount_cents,
        }

    # --- STAGE 2: a human decision is present --------------------------
    import json

    # Extract confirmed and payload in a robust, version-agnostic way.
    raw_confirmed = False
    raw_payload = {}

    if isinstance(confirmation, dict):
        raw_confirmed = confirmation.get("confirmed", False)
        raw_payload = confirmation.get("payload") or {}
    elif confirmation is not None:
        raw_confirmed = getattr(confirmation, "confirmed", False)
        raw_payload = getattr(confirmation, "payload", None) or {}

        # Fallback in case ADK wraps or exposes it via a .response attribute
        if not raw_confirmed and hasattr(confirmation, "response"):
            resp = getattr(confirmation, "response")
            if isinstance(resp, dict):
                raw_confirmed = resp.get("confirmed", False)
                if not raw_payload:
                    raw_payload = resp.get("payload") or {}
            elif isinstance(resp, str):
                try:
                    parsed_resp = json.loads(resp)
                    if isinstance(parsed_resp, dict):
                        raw_confirmed = parsed_resp.get("confirmed", False)
                        if not raw_payload:
                            raw_payload = parsed_resp.get("payload") or {}
                except Exception:
                    pass

    # The user confirms either via the top-level flag or the nested payload approved key
    approved = bool(raw_confirmed) or bool(raw_payload.get("approved", False))
    payload = raw_payload

    if not approved:
        # Rejection path — the $40k "mark for manual review" demo beat.
        _write_audit(
            actor="HUMAN",
            action="reject_adjustment",
            detail=f"{entry_txn_id}: rejected; flagged for manual review.",
        )
        return {
            "status": "REJECTED",
            "entry_txn_id": entry_txn_id,
            "note": "Adjustment rejected by human; marked for manual review.",
        }

    # Approval path — honor an optionally human-edited amount, capped to the
    # originally proposed magnitude so approval can only reduce, never inflate.
    raw = payload.get("approved_amount_cents")
    approved_amount = amount_cents if raw in (None, 0) else raw
    if amount_cents < 0:
        approved_amount = max(approved_amount, amount_cents)   # don't over-reverse
    else:
        approved_amount = min(approved_amount, amount_cents)

    result = _mcp_post_adjustment(
        entry_txn_id=entry_txn_id,
        amount_cents=int(approved_amount),
        reason=reason,
    )
    _write_audit(
        actor="HUMAN",
        action="approve_adjustment",
        detail=f"{entry_txn_id}: approved {approved_amount} cents.",
    )
    return {"status": "POSTED", **result}


# The wrapped tool the CloseOrchestrator is given. The confirmation logic lives
# inside the function (advanced pattern), so we do NOT also set
# require_confirmation here — that would double-gate. One gate, owned by the tool.
post_adjustment_tool = FunctionTool(post_adjustment_gated)
