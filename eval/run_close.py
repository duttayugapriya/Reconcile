"""
eval/run_close.py — drives an end-to-end close with human-in-the-loop approvals.

This is the on-camera "showdown" driver. It runs the CloseOrchestrator, watches
for ADK tool-confirmation requests (function call name == 'adk_request_confirmation'),
and responds with an approval or rejection per the demo policy:
    - APPROVE the duplicate-payment reversal.
    - REJECT the large miscategorization (mark for manual review).

Uses InMemoryRunner because the Tool Confirmation feature does NOT support
DatabaseSessionService / VertexAiSessionService (per ADK docs).

Run:  python -m eval.run_close
Prereq:  python data/generate.py   (creates data/reconcile.db)
"""
from __future__ import annotations

import asyncio

from google.adk.runners import InMemoryRunner
from google.genai import types

from agents.orchestrator import root_agent

APP_NAME = "reconcile"
USER_ID = "demo_analyst"
PERIOD = "2026-05"

# Demo approval policy: approve reversals (negative amounts), reject large
# positive reclassifications above the threshold. Tune to your dataset.
THRESHOLD_CENTS = 10_000_00


def _decide(payload_hint: str) -> tuple[bool, dict]:
    """Return (confirmed, payload) for a confirmation request.

    Heuristic for the unattended demo: approve if the hint describes a
    reversal; reject otherwise. In the live web UI a human clicks instead.
    """
    is_reversal = "reversal" in payload_hint.lower()
    if is_reversal:
        return True, {"approved": True, "approved_amount_cents": 0}
    return False, {"approved": False, "approved_amount_cents": 0}


async def main() -> None:
    runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID
    )

    msg = types.Content(
        role="user",
        parts=[types.Part.from_text(text=f"Close the period {PERIOD}.")],
    )

    # Run until the agent either finishes or pauses for a confirmation.
    pending = await _run_until_pause(runner, session.id, msg)

    # Resolve each confirmation request, resuming the invocation each time.
    while pending is not None:
        fc_id, hint = pending
        confirmed, payload = _decide(hint)
        print(f"\n[HUMAN] {'APPROVE' if confirmed else 'REJECT'} -> {hint[:80]}...")

        resume_msg = types.Content(
            role="user",
            parts=[types.Part(
                function_response=types.FunctionResponse(
                    id=fc_id,
                    name="adk_request_confirmation",
                    response={"confirmed": confirmed, "payload": payload},
                )
            )],
        )
        pending = await _run_until_pause(runner, session.id, resume_msg)

    print("\n[CLOSE COMPLETE]")


async def _run_until_pause(runner, session_id, message):
    """Stream events; return (function_call_id, hint) if a confirmation is
    requested, else None when the turn finishes normally."""
    async for event in runner.run_async(
        user_id=USER_ID, session_id=session_id, new_message=message
    ):
        if not event.content or not event.content.parts:
            continue
        for part in event.content.parts:
            fc = getattr(part, "function_call", None)
            if fc and fc.name == "adk_request_confirmation":
                hint = ""
                args = fc.args or {}
                # The hint is nested in the original confirmation request args.
                hint = str(args.get("hint") or args)
                return (fc.id, hint)
            if part.text:
                print(part.text, end="", flush=True)
    return None


if __name__ == "__main__":
    asyncio.run(main())
