# tests/test_guardrail.py
from types import SimpleNamespace
from security.guardrails import security_guardrail, mask_pii

class FakeState(dict):
    pass

class FakeTool:
    def __init__(self, name):
        self.name = name

def test_narrative_agent_post_adjustment_denied():
    ctx = SimpleNamespace(
        agent_name="NarrativeAgent",
        state=FakeState(),
        tool_confirmation=None
    )
    out = security_guardrail(
        tool=FakeTool("post_adjustment"),
        args={"amount_cents": 5000},
        tool_context=ctx
    )
    assert out is not None
    assert out.get("status") == "DENIED"
    assert "NarrativeAgent" in out.get("reason")

def test_pii_masking():
    masked = mask_pii({"account_number": "12345678", "memo": "ACH 987654321"})
    assert masked.get("account_number") == "***REDACTED***"
    assert masked.get("memo") == "ACH ***REDACTED***"

def test_flag_transaction_actor_injection():
    # Test that calling flag_transaction dynamically injects the calling agent's name as 'actor'.
    ctx = SimpleNamespace(
        agent_name="AnomalyAgent",
        state=FakeState(),
        tool_confirmation=None
    )
    args = {"txn_id": "TXN-001", "reason": "Potential mismatch"}
    out = security_guardrail(
        tool=FakeTool("flag_transaction"),
        args=args,
        tool_context=ctx
    )
    # The guardrail should allow the call (returns None)
    assert out is None
    # The guardrail should have mutated 'args' to include 'actor' set to agent_name
    assert args.get("actor") == "AnomalyAgent"

if __name__ == "__main__":
    test_narrative_agent_post_adjustment_denied()
    test_pii_masking()
    test_flag_transaction_actor_injection()
    print("All guardrail tests passed successfully!")
