"""ParallelAgent wrapping Matching + Anomaly (independent specialist work)."""
from __future__ import annotations

from google.adk.agents import ParallelAgent

from agents.matching import matching_agent
from agents.anomaly import anomaly_agent

# NOTE: ADK ParallelAgent runs sub-agents in independent branches with no
# automatic state sharing DURING the run, but each writes its own output_key
# to session state, which the NarrativeAgent and orchestrator read AFTER the
# parallel block completes. Both sub-agents read {normalized_data}, which is
# already in state from the prior sequential IngestionAgent step, so the
# parallelism is safe (read-only shared input, disjoint output keys).
reconcile_parallel = ParallelAgent(
    name="ReconcileParallel",
    sub_agents=[matching_agent, anomaly_agent],
    description="Runs 3-way matching and anomaly detection concurrently.",
)
