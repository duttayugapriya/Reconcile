# scratch_test.py  (don't commit; just a sanity check)
from types import SimpleNamespace
from security.guardrails import security_guardrail, mask_pii

class FakeState(dict):
    pass

class FakeTool:  # mimics BaseTool.name
    def __init__(self, name): self.name = name

ctx = SimpleNamespace(agent_name="NarrativeAgent",
                      state=FakeState(),
                      tool_confirmation=None)

# NarrativeAgent calling post_adjustment must be DENIED:
out = security_guardrail(tool=FakeTool("post_adjustment"),
                         args={"amount_cents": 5000}, tool_context=ctx)
print(out)   # -> {'status': 'DENIED', ...} and a privilege_violations entry

# PII masking sanity check:
print(mask_pii({"account_number": "12345678", "memo": "ACH 987654321"}))
# -> {'account_number': '***REDACTED***', 'memo': 'ACH ***REDACTED***'}
