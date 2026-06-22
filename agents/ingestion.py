"""IngestionAgent — pulls the three sources and normalizes them to state."""
from __future__ import annotations

from google.adk.agents import LlmAgent

from agents.mcp_toolsets import ingestion_toolset
from security.guardrails import security_guardrail

GEMINI_MODEL = "gemini-2.5-flash"

ingestion_agent = LlmAgent(
    name="IngestionAgent",  # MUST match TOOL_SCOPES key
    model=GEMINI_MODEL,
    description="Pulls ledger, bank, and invoice records for the period and "
                "normalizes them into a canonical set.",
    instruction="""
You are the Ingestion specialist for a month-end financial close.

The fiscal period to close is provided in state under key 'period'
(e.g. "2026-05"). If it is missing, use "2026-05".

Steps:
1. Call get_ledger_entries(period), fetch_bank_statement(period),
   fetch_invoices(period).
2. Produce a SINGLE normalized JSON object with three arrays: "ledger",
   "bank", "invoices". For every record keep: txn_id, source, txn_date,
   vendor_id, vendor_name, amount_cents (INTEGER cents — never convert to
   dollars/floats), account_code, memo, invoice_ref.
3. Report the count of records in each source.

Output ONLY that JSON object. Do not analyze or judge the data — later
agents do that.
""",
    tools=[ingestion_toolset()],
    before_tool_callback=security_guardrail,
    output_key="normalized_data",  # downstream agents read {normalized_data}
)
