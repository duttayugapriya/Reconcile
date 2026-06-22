"""NarrativeAgent — writes the audit-ready close summary. Append-log only."""
from __future__ import annotations

from google.adk.agents import LlmAgent

from agents.mcp_toolsets import narrative_toolset
from security.guardrails import security_guardrail

GEMINI_MODEL = "gemini-2.5-flash"

narrative_agent = LlmAgent(
    name="NarrativeAgent",  # MUST match TOOL_SCOPES key
    model=GEMINI_MODEL,
    description="Writes the human-readable, audit-ready close summary.",
    instruction="""
You are the Narrative specialist. You physically CANNOT move money — your only
tool is write_audit_log. Read from state:

MATCHING RESULT: {matching_result}
ANOMALY RESULT:  {anomaly_result}

Write an audit-ready month-end close summary covering:
1. What reconciled cleanly (counts, unreconciled balance).
2. Each anomaly found, with its explanation and confidence.
3. Which adjustments were approved vs rejected by the human (this information,
   if present, is in state under 'adjustment_outcomes'; if absent, say the
   approval step has not run yet).
4. Any privilege violations attempted (state key 'privilege_violations') — if
   present, report them as a security note; if absent, state that no agent
   attempted to exceed its scope.

After composing the summary, call write_audit_log(actor="NarrativeAgent",
action="close_summary", detail=<a one-line digest of the summary>).

Output the full human-readable summary as your final response.
""",
    tools=[narrative_toolset()],
    before_tool_callback=security_guardrail,
    output_key="close_summary",
)
