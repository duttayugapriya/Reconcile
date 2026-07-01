# tests/test_confirmation.py
from types import SimpleNamespace
from security.confirmation import post_adjustment_gated

class MockToolContext:
    def __init__(self, tool_confirmation=None):
        self.tool_confirmation = tool_confirmation
        self.requested_hint = None
        self.requested_payload = None

    def request_confirmation(self, hint, payload):
        self.requested_hint = hint
        self.requested_payload = payload

class MockConfirmation:
    def __init__(self, confirmed, payload):
        self.confirmed = confirmed
        self.payload = payload

def test_stage1_request_confirmation():
    # Test when no confirmation is present
    ctx = MockToolContext(tool_confirmation=None)
    result = post_adjustment_gated(
        entry_txn_id="TXN-123",
        amount_cents=-1240000,
        reason="Duplicate payment reversal",
        tool_context=ctx
    )
    
    assert result["status"] == "AWAITING_HUMAN_APPROVAL"
    assert result["proposed_amount_cents"] == -1240000
    assert ctx.requested_hint is not None
    assert "TXN-123" in ctx.requested_hint
    assert ctx.requested_payload == {"approved": False, "approved_amount_cents": None}

def test_stage2_rejection():
    # Test when confirmation is rejected (confirmed=False, approved=False)
    conf = MockConfirmation(confirmed=False, payload={"approved": False})
    ctx = MockToolContext(tool_confirmation=conf)
    
    result = post_adjustment_gated(
        entry_txn_id="TXN-123",
        amount_cents=-1240000,
        reason="Duplicate payment reversal",
        tool_context=ctx
    )
    
    assert result["status"] == "REJECTED"
    assert "rejected" in result["note"].lower()

def test_stage2_approval_default_amount_none():
    # Test when approved but approved_amount_cents is None (absent)
    conf = MockConfirmation(confirmed=True, payload={"approved": True, "approved_amount_cents": None})
    ctx = MockToolContext(tool_confirmation=conf)
    
    result = post_adjustment_gated(
        entry_txn_id="TXN-123",
        amount_cents=-1240000,
        reason="Duplicate payment reversal",
        tool_context=ctx
    )
    
    assert result["status"] == "posted"
    assert result["amount_cents"] == -1240000

def test_stage2_approval_default_amount_zero():
    # Test when approved but approved_amount_cents is 0 (the bug condition)
    # With our fix, this must also use the proposed amount_cents (-1240000) instead of 0
    conf = MockConfirmation(confirmed=True, payload={"approved": True, "approved_amount_cents": 0})
    ctx = MockToolContext(tool_confirmation=conf)
    
    result = post_adjustment_gated(
        entry_txn_id="TXN-123",
        amount_cents=-1240000,
        reason="Duplicate payment reversal",
        tool_context=ctx
    )
    
    assert result["status"] == "posted"
    assert result["amount_cents"] == -1240000

def test_stage2_approval_custom_amount():
    # Test when approved with a custom (reduced) amount
    # Proposed reversal: -$12,400. Approved reversal: -$10,000.
    conf = MockConfirmation(confirmed=True, payload={"approved": True, "approved_amount_cents": -1000000})
    ctx = MockToolContext(tool_confirmation=conf)
    
    result = post_adjustment_gated(
        entry_txn_id="TXN-123",
        amount_cents=-1240000,
        reason="Duplicate payment reversal",
        tool_context=ctx
    )
    
    assert result["status"] == "posted"
    # Reversal amount is capped at proposed magnitude so we cannot over-reverse.
    # approved_amount = max(-1000000, -1240000) = -1000000.
    assert result["amount_cents"] == -1000000

def test_decide_extracts_amount():
    from eval.run_close import _decide
    hint = (
        "APPROVAL REQUIRED — post_adjustment\n"
        "  Transaction : TXN-123\n"
        "  Amount      : -1240000 cents (reversal)\n"
        "  Reason      : Duplicate payment\n"
    )
    confirmed, payload = _decide(hint)
    assert confirmed is True
    assert payload == {"approved": True, "approved_amount_cents": -1240000}

    hint_no_amount = "A reversal occurred but no amount details are present."
    confirmed, payload = _decide(hint_no_amount)
    assert confirmed is True
    assert payload == {"approved": True}

if __name__ == "__main__":
    test_stage1_request_confirmation()
    test_stage2_rejection()
    test_stage2_approval_default_amount_none()
    test_stage2_approval_default_amount_zero()
    test_stage2_approval_custom_amount()
    test_decide_extracts_amount()
    print("All confirmation and approval tests passed successfully!")
