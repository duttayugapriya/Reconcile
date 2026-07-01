# scratch_agents_test.py (don't commit)
from agents.orchestrator import root_agent
print(root_agent.name, [a.name for a in root_agent.sub_agents])
print("orchestrator tools:", [t.name for t in root_agent.tools])
# Expect: CloseOrchestrator ['ClosePipeline']
#         orchestrator tools includes 'post_adjustment_gated' but NOT raw MCP post_adjustment
