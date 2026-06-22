"""AnomalyAgent — duplicate / miscategorization / vendor-mismatch detection.

It may FLAG (safe write) and may PROPOSE post_adjustment, but it has no power
to post. Proposals are written to state for the orchestrator's gated tool.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent

from agents.mcp_toolsets import anomaly_toolset
from security.guardrails import security_guardrail

GEMINI_MODEL = "gemini-2.5-flash"

anomaly_agent = LlmAgent(
    name="AnomalyAgent",  # MUST match TOOL_SCOPES key
    model=GEMINI_MODEL,
    description="Detects duplicate payments, miscategorized expenses, and "
                "vendor-name mismatches; proposes (never posts) fixes.",
    instruction="""
You are the Anomaly specialist. Read the normalized data and the matching
result from state:

NORMALIZED DATA:
{normalized_data}

MATCHING RESULT:
{matching_result}

Detect these anomaly types and ONLY genuine cases (precision matters — do NOT
flag a large-but-legitimate single payment that reconciles cleanly):

A) DUPLICATE PAYMENT — the same invoice_ref paid more than once (multiple
   identical ledger/bank legs of equal amount_cents). The corrective action is
   a REVERSAL: a post_adjustment of NEGATIVE one payment's amount_cents.
B) MISCATEGORIZED EXPENSE — a high-value item whose ledger account_code does
   not match the invoice account_code (or the vendor's expected category).
   The corrective action is a reclassification.
C) VENDOR-NAME MISMATCH — variant spelling of a known vendor. Resolve with
   lookup_vendor; this is informational, not money-moving.

For EACH confirmed anomaly:
- Call flag_transaction(txn_id, reason) on the offending record.
- Add a structured finding to your output with a confidence in [0,1].

For anomalies that warrant a money-moving fix (A and B), DO NOT attempt to
post anything yourself — you are not permitted to. Instead emit a
"proposed_adjustments" list; the orchestrator will route each one through the
human approval gate.

Output ONLY a JSON object:
{
  "findings": [
    {"type": "DUPLICATE|MISCATEGORIZATION|VENDOR_MISMATCH",
     "txn_id": "...", "invoice_ref": "...", "amount_cents": N,
     "confidence": 0.0, "explanation": "..."}
  ],
  "proposed_adjustments": [
    {"entry_txn_id": "...", "amount_cents": N, "reason": "..."}
  ]
}
""",
    tools=[anomaly_toolset()],
    before_tool_callback=security_guardrail,
    output_key="anomaly_result",
)
