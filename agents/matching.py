"""MatchingAgent — 3-way match (ledger <-> bank <-> invoice) + vendor resolve."""
from __future__ import annotations

from google.adk.agents import LlmAgent

from agents.mcp_toolsets import matching_toolset
from security.guardrails import security_guardrail

GEMINI_MODEL = "gemini-2.5-flash"

matching_agent = LlmAgent(
    name="MatchingAgent",  # MUST match TOOL_SCOPES key
    model=GEMINI_MODEL,
    description="Performs 3-way matching and computes the unreconciled balance.",
    instruction="""
You are the Matching specialist. The normalized data is in state:

{normalized_data}

Perform a 3-way match using invoice_ref as the linking key and amount_cents
for amount equality (amounts are EXACT integer cents — match exactly):

1. Group records by invoice_ref across ledger, bank, and invoices.
2. A reference is FULLY MATCHED when it has exactly one invoice, one ledger,
   and one bank record of equal amount_cents.
3. Flag references with extra/missing legs as UNMATCHED (e.g. two ledger+bank
   legs for one invoice => candidate duplicate; leave the duplicate judgement
   to the Anomaly specialist but note the count mismatch here).
4. When a vendor_name differs across legs of the same invoice_ref, call
   lookup_vendor(name) to resolve the variant to its master vendor_id and
   report the confidence.
5. Compute the total unreconciled amount_cents.

Output ONLY a JSON object:
{
  "matched_refs": [...],
  "unmatched_refs": [{"invoice_ref": "...", "issue": "...", "amount_cents": N}],
  "vendor_resolutions": [{"variant": "...", "resolved_vendor_id": "...",
                          "confidence": 0.0}],
  "unreconciled_total_cents": N
}
""",
    tools=[matching_toolset()],
    before_tool_callback=security_guardrail,
    output_key="matching_result",
)
