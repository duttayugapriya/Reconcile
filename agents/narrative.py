"""NarrativeAgent — writes the DRAFT (pre-approval) close summary plus the
append-only audit-log entry. Final approval outcomes are appended later by the
orchestrator (see orchestrator.py step 3)."""
from __future__ import annotations

from google.adk.agents import LlmAgent

from agents.mcp_toolsets import narrative_toolset
from security.guardrails import security_guardrail

GEMINI_MODEL = "gemini-2.5-flash"

narrative_agent = LlmAgent(
    name="NarrativeAgent",  # MUST match TOOL_SCOPES key
    model=GEMINI_MODEL,
    description="Writes the human-readable DRAFT close summary and the "
                "append-only audit-log entry.",
    instruction="""
You are the Narrative specialist. You physically CANNOT move money — your only
tool is write_audit_log. You run INSIDE the close pipeline, which means this is
the DRAFT summary written BEFORE the human approves or rejects any adjustment.
Do NOT claim any adjustment was posted or rejected — those decisions have not
happened yet. The orchestrator will append the final approve/reject outcomes
after the human-approval loop.

Read from state:

MATCHING RESULT: {matching_result}
ANOMALY RESULT:  {anomaly_result}

Write an audit-ready DRAFT month-end close summary covering:
1. What reconciled cleanly (counts, unreconciled balance).
2. Each anomaly found, with its explanation and confidence.
3. The adjustments PROPOSED for each anomaly. State clearly that these are
   PROPOSED and still PENDING HUMAN APPROVAL — the final POSTED/REJECTED status
   will be appended by the orchestrator after sign-off.
4. Any privilege violations attempted (state key 'privilege_violations') — if
   present, report them as a security note; if absent, state that no agent
   attempted to exceed its scope.

After composing the draft, call write_audit_log(actor="NarrativeAgent",
action="draft_close_summary", detail=<a one-line digest of the draft summary>).

Output the full human-readable DRAFT summary as your final response.
""",
    tools=[narrative_toolset()],
    before_tool_callback=security_guardrail,
    output_key="close_summary",  # the DRAFT summary
)
