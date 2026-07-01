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

    # Test hyphenated and spaced account numbers
    masked_hyphen = mask_pii("account 1234-5678-9012 here")
    assert "1234-5678-9012" not in masked_hyphen
    assert "***REDACTED***" in masked_hyphen

    masked_space = mask_pii("account 1234 5678 9012 here")
    assert "1234 5678 9012" not in masked_space
    assert "***REDACTED***" in masked_space

    # Test that dates and normal numbers are NOT masked
    date_str = "date is 2026-07-01 and code is 123-45"
    masked_date = mask_pii(date_str)
    assert masked_date == date_str

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

def test_write_audit_pii_masking():
    from unittest.mock import patch, MagicMock
    from mcp_server.server import _write_audit
    
    with patch("mcp_server.server._con") as mock_con_factory:
        mock_con = MagicMock()
        mock_con_factory.return_value = mock_con
        
        # Test audit detail with JSON PII
        detail_json = '{"account_number": "12345678-9900", "reason": "Test"}'
        _write_audit("NarrativeAgent", "write_log", detail_json)
        
        # Check that mock_con.execute was called and detail parameter was masked
        args, kwargs = mock_con.execute.call_args
        assert len(args) == 2
        # args[1] is the tuple of values: (ts, actor, action, detail)
        persisted_detail = args[1][3]
        import json
        parsed = json.loads(persisted_detail)
        assert parsed["account_number"] == "***REDACTED***"

        # Test audit detail with plain text hyphenated card/account
        detail_text = "Reversed the payment for card 1234-5678-9012."
        _write_audit("NarrativeAgent", "write_log", detail_text)
        
        args, kwargs = mock_con.execute.call_args
        persisted_detail_text = args[1][3]
        assert "1234-5678-9012" not in persisted_detail_text
        assert "card ***REDACTED***" in persisted_detail_text

if __name__ == "__main__":
    test_narrative_agent_post_adjustment_denied()
    test_pii_masking()
    test_flag_transaction_actor_injection()
    test_write_audit_pii_masking()
    print("All guardrail tests passed successfully!")
