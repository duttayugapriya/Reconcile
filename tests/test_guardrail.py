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

if __name__ == "__main__":
    test_narrative_agent_post_adjustment_denied()
    test_pii_masking()
    print("All guardrail tests passed successfully!")
