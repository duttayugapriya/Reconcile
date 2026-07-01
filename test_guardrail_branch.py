from security.guardrails import security_guardrail, _ORCHESTRATOR_OWNED
from types import SimpleNamespace

# Check if the tool name is in the orchestrator-owned list
from security.confirmation import post_adjustment_tool
print(f"Tool name: {post_adjustment_tool.name}")
print(f"Is it in _ORCHESTRATOR_OWNED? {post_adjustment_tool.name in _ORCHESTRATOR_OWNED}")

# Simulate a call
class FakeState(dict):
    pass

class FakeTool:
    def __init__(self, name):
        self.name = name

ctx = SimpleNamespace(agent_name="CloseOrchestrator", state=FakeState(), tool_confirmation=None)
result = security_guardrail(
    tool=FakeTool(post_adjustment_tool.name),
    args={"entry_txn_id": "GL-099", "amount_cents": 1240000, "reason": "Duplicate payment"},
    tool_context=ctx
)
print(f"Guardrail result: {result}")  # Should be None (allowed) or _denied()