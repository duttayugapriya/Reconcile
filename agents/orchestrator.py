"""
CloseOrchestrator — root agent.

Owns the ONLY money-moving tool (post_adjustment_tool, the human-gated
FunctionTool). It runs the close pipeline AS A TOOL (AgentTool) so that control
ALWAYS returns to the orchestrator after the pipeline finishes. This is the key
ADK pattern choice: with `sub_agents=`, an LlmAgent transfers control away and
does not reliably resume to loop over proposed adjustments; with AgentTool, the
pipeline is a callable step and the orchestrator keeps the conversational turn,
so it can then drive each proposed adjustment through the human-approval gate.

Flow:
    run_close_pipeline()  ->  Ingest -> [Matching || Anomaly] -> Narrate (DRAFT)
    then: for each proposed_adjustment -> post_adjustment(...) [PAUSES for human]
    then: orchestrator composes the FINAL close package with POSTED/REJECTED.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.tools.agent_tool import AgentTool

from agents.ingestion import ingestion_agent
from agents.reconcile_parallel import reconcile_parallel
from agents.narrative import narrative_agent
from security.guardrails import security_guardrail
from security.confirmation import post_adjustment_tool

GEMINI_MODEL = "gemini-2.5-flash"

# The deterministic close pipeline: ingest -> reconcile (parallel) -> narrate.
# Sub-agents here write their output_keys to session state, which the
# orchestrator reads AFTER the pipeline tool returns. The NarrativeAgent here
# produces only the DRAFT (pre-approval) summary.
close_pipeline = SequentialAgent(
    name="ClosePipeline",
    sub_agents=[ingestion_agent, reconcile_parallel, narrative_agent],
    description="Ingest -> reconcile (parallel) -> narrate (draft).",
)

# Wrap the pipeline as a tool so control returns to the orchestrator.
close_pipeline_tool = AgentTool(agent=close_pipeline)

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

1. Call the ClosePipeline tool with the period. It ingests, reconciles in
   parallel, and writes a DRAFT narrative. After it returns, the results are in
   session state: 'matching_result', 'anomaly_result', 'normalized_data', and
   the draft summary under 'close_summary'.

2. Read 'anomaly_result'. It contains a 'proposed_adjustments' list. Process
   the adjustments STRICTLY ONE AT A TIME. For ONE proposed adjustment, call:
       post_adjustment(entry_txn_id=..., amount_cents=..., reason=...)
   This tool will PAUSE and ask the human to approve or reject. WAIT for its
   result before calling it again for the NEXT proposed adjustment. Do not
   batch multiple adjustments into one turn, and do not invent your own posting
   path; this gated tool is the ONLY way money can move. Track each tool
   result so you know whether it was POSTED (approved) or REJECTED.

3. After ALL adjustments are resolved, COMPOSE THE FINAL CLOSE PACKAGE
   YOURSELF, incorporating each adjustment's POSTED/REJECTED status from the
   tool results above. Start from the draft summary in 'close_summary' and
   augment it with: reconciliation status, anomalies found, each adjustment's
   final approve/reject decision and dollar amount, and the audit note. State
   explicitly that no dollar moved without human sign-off, and that the figures
   reflect the human's actual approve/reject decisions (not the draft).

If there are zero proposed adjustments, say so and present the draft summary
unchanged as the final package.
""",
    tools=[close_pipeline_tool, post_adjustment_tool],
    before_tool_callback=security_guardrail,
)
