# tests/test_e2e_confirmation_flow.py
import os
import json
import asyncio
from unittest.mock import patch, MagicMock

# Set dummy API key to pass the Client initialization check
os.environ["GEMINI_API_KEY"] = "dummy-api-key-for-testing"

from google.adk.runners import InMemoryRunner
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.genai import types

from security.confirmation import post_adjustment_gated

# Define custom mock response stream
class MockResponseStream:
    def __init__(self, response):
        self.response = response
        self.used = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.used:
            self.used = True
            return self.response
        raise StopAsyncIteration

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


def test_e2e_confirmation_flow():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # 1. Create a test LlmAgent with the gated tool
    test_tool = FunctionTool(post_adjustment_gated)
    test_agent = LlmAgent(
        name="TestOrchestrator",
        model="gemini-2.5-flash",
        instruction="Use the post_adjustment_gated tool to post the adjustment.",
        tools=[test_tool]
    )

    # Mock responses for step 1 (propose tool call) and step 2 (final message)
    part_fc = types.Part(
        function_call=types.FunctionCall(
            name="post_adjustment_gated",
            id="adk-call-12345",
            args={
                "entry_txn_id": "TXN-123",
                "amount_cents": -100000,
                "reason": "Duplicate payment reversal"
            }
        )
    )
    response_1 = types.GenerateContentResponse(
        candidates=[types.Candidate(
            content=types.Content(role="model", parts=[part_fc]),
            finish_reason=types.FinishReason.STOP
        )]
    )

    part_text = types.Part(text="Successfully posted the duplicate payment reversal.")
    response_2 = types.GenerateContentResponse(
        candidates=[types.Candidate(
            content=types.Content(role="model", parts=[part_text]),
            finish_reason=types.FinishReason.STOP
        )]
    )

    call_count = 0

    async def mock_generate_content_stream(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MockResponseStream(response_1)
        else:
            return MockResponseStream(response_2)

    async def mock_generate_content(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return response_1
        else:
            return response_2

    # Patch the google-genai Client methods at module level
    with patch("google.genai.Client") as mock_client_cls, \
         patch("security.confirmation._mcp_post_adjustment") as mock_mcp_post, \
         patch("security.confirmation._write_audit") as mock_audit:

        # Set up mock MCP post adjustment tool result
        mock_mcp_post.return_value = {"txn_id": "ADJ-999", "status": "POSTED", "amount_cents": -100000}

        # Build mock client hierarchy
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        # Async client methods
        mock_client.aio.models.generate_content_stream = mock_generate_content_stream
        mock_client.aio.models.generate_content = mock_generate_content

        # Run the agent using InMemoryRunner
        runner = InMemoryRunner(agent=test_agent, app_name="reconcile")
        
        async def run_test():
            session = await runner.session_service.create_session(
                app_name="reconcile", user_id="demo_analyst"
            )
            
            # Start the agent run
            msg = types.Content(
                role="user",
                parts=[types.Part.from_text(text="Start the task")]
            )

            from eval.run_close import _run_until_pause

            # Step 1: Run until pause
            print("--- Running turn 1 (should pause for confirmation) ---")
            pending_pause = await _run_until_pause(runner, session.id, msg)

            assert pending_pause is not None, "Runner did not pause for confirmation!"
            fc_id, hint = pending_pause
            print(f"Captured confirmation request event. Hint: {hint}")
            
            # Verify the hint extracted by _run_until_pause matches expectations
            assert "APPROVAL REQUIRED" in hint
            assert "Transaction : TXN-123" in hint
            assert "Amount      : -100000 cents" in hint

            # Step 2: Resume turn with confirmation response
            print("\n--- Resuming turn with approval response ---")
            confirmed = True
            payload = {"approved": True, "approved_amount_cents": -100000}

            resume_msg = types.Content(
                role="user",
                parts=[types.Part(
                    function_response=types.FunctionResponse(
                        id=fc_id,
                        name="adk_request_confirmation",
                        response={"response": json.dumps({"confirmed": confirmed, "payload": payload})},
                    )
                )],
            )

            pending_pause_2 = await _run_until_pause(runner, session.id, resume_msg)
            assert pending_pause_2 is None, "Runner paused again unexpectedly!"
            has_completed = True

            assert has_completed, "The invocation did not complete successfully after resume."
            
            # Verify that the underlying tool was posted and audit was written
            mock_mcp_post.assert_called_once_with(
                entry_txn_id="TXN-123",
                amount_cents=-100000,
                reason="Duplicate payment reversal"
            )
            mock_audit.assert_called_once()
            print("\nE2E confirmation and resume flow verified successfully!")

        loop.run_until_complete(run_test())

if __name__ == "__main__":
    test_e2e_confirmation_flow()
