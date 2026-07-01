"""IngestionAgent — pulls the three sources and normalizes them to state."""
from __future__ import annotations

from typing import Any
from google.adk.agents import LlmAgent

from agents.mcp_toolsets import ingestion_toolset
from security.guardrails import security_guardrail

GEMINI_MODEL = "gemini-2.5-flash"

def clean_normalized_data_callback(callback_context: Any) -> None:
    """Extract, clean, and format raw JSON output from IngestionAgent."""
    raw_data = callback_context.state.get("normalized_data")
    if not isinstance(raw_data, str):
        return

    cleaned = raw_data.strip()
    # Strip markdown code blocks / fences
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    import json
    try:
        # Attempt to parse the stripped string
        parsed = json.loads(cleaned)
        cleaned = json.dumps(parsed, indent=2)
    except Exception:
        # If parsing fails, attempt to locate the JSON boundaries
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(cleaned[start:end+1])
                cleaned = json.dumps(parsed, indent=2)
            except Exception:
                pass

    callback_context.state["normalized_data"] = cleaned


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

Output ONLY that JSON object. Do NOT wrap the JSON in markdown code blocks or
fences (do NOT use ```json or ```). Do not analyze or judge the data.
""",
    tools=[ingestion_toolset()],
    before_tool_callback=security_guardrail,
    after_agent_callback=clean_normalized_data_callback,
    output_key="normalized_data",  # downstream agents read {normalized_data}
)
