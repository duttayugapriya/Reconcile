"""
CloseOrchestrator — root agent.

Owns the ONLY money-moving tool (post_adjustment_tool, the human-gated
FunctionTool). Drives the Sequential pipeline:
    Ingest -> [Matching || Anomaly] -> Narrate
then surfaces each proposed adjustment for human approval via the gated tool.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent, SequentialAgent

from agents.ingestion import ingestion_agent
from agents.reconcile_parallel import reconcile_parallel
from agents.narrative import narrative_agent
from security.guardrails import security_guardrail
from security.confirmation import post_adjustment_tool

GEMINI_MODEL = "gemini-2.5-flash"

# The deterministic close pipeline. Runs as the orchestrator's first move.
close_pipeline = SequentialAgent(
    name="ClosePipeline",
    sub_agents=[ingestion_agent, reconcile_parallel, narrative_agent],
    description="Ingest -> reconcile (parallel) -> narrate.",
)

root_agent = LlmAgent(
    name="CloseOrchestrator",  # MUST match TOOL_SCOPES key (empty MCP scope)
    model=GEMINI_MODEL,
    description="Plans the close, runs the pipeline, and gates every "
                "money-moving adjustment behind human approval.",
    instruction="""
You orchestrate an autonomous month-end financial close. You NEVER read raw
data or move money directly except through the human-gated post_adjustment
tool.

When asked to close a period (e.g. "close 2026-05"):
1. Store the period and run the close pipeline (it ingests, reconciles in
   parallel, and writes a draft narrative).
2. Read the anomaly result's 'proposed_adjustments'. For EACH proposed
   adjustment, call post_adjustment(entry_txn_id, amount_cents, reason). This
   tool will PAUSE and ask the human to approve or reject. Surface its result.
   Never bypass it; never invent your own posting path.
3. Record each outcome (POSTED / REJECTED) in state under 'adjustment_outcomes'
   so the narrative can reflect human decisions.
4. Present the final close package: reconciliation status, anomalies found,
   adjustments approved vs rejected, and the audit-ready summary.

Be explicit that no dollar moved without human sign-off.
""",
    sub_agents=[close_pipeline],
    tools=[post_adjustment_tool],  # the ONLY money-moving tool, gated
    before_tool_callback=security_guardrail,
)
