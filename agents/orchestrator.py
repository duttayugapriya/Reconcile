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
    run_close_pipeline()  ->  Ingest -> [Matching || Anomaly] -> Narrate
    then: for each proposed_adjustment -> post_adjustment(...) [PAUSES for human]
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
# orchestrator reads AFTER the pipeline tool returns.
close_pipeline = SequentialAgent(
    name="ClosePipeline",
    sub_agents=[ingestion_agent, reconcile_parallel, narrative_agent],
    description="Ingest -> reconcile (parallel) -> narrate.",
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
   parallel, and writes a draft narrative. After it returns, the results are in
   session state: 'matching_result', 'anomaly_result', 'normalized_data'.

2. Read 'anomaly_result'. It contains a 'proposed_adjustments' list. For EACH
   proposed adjustment, call:
       post_adjustment(entry_txn_id=..., amount_cents=..., reason=...)
   This tool will PAUSE and ask the human to approve or reject. Do not invent
   your own posting path; this gated tool is the ONLY way money can move.
   Call it once per proposed adjustment, surfacing each result.

3. After all adjustments are resolved, present the final close package:
   reconciliation status, anomalies found, adjustments approved vs rejected,
   and the audit-ready summary. State explicitly that no dollar moved without
   human sign-off.

If there are zero proposed adjustments, say so and present the summary.
""",
    tools=[close_pipeline_tool, post_adjustment_tool],
    before_tool_callback=security_guardrail,
)
