---
name: reconcile-conventions
description: >
  Security and architecture invariants for the Reconcile autonomous month-end
  close system. Antigravity MUST follow these when generating or editing any
  agent, MCP tool, or guardrail code in this repository.
---

# Reconcile — Engineering & Safety Invariants

These rules are non-negotiable. They encode the project's security thesis so
that the AI building the system cannot violate the system's own guarantees.

## 1. Money is integer cents, always
Never represent monetary amounts as floats. All amounts are `amount_cents`
(int). Comparisons must be exact. Any new field carrying money ends in
`_cents`.

## 2. Separation of privilege is sacred
The privilege map in `mcp_server/tool_scopes.py` is the ONLY source of truth
for which agent may call which tool. Never hardcode tool permissions anywhere
else. When adding a tool to an agent, edit `TOOL_SCOPES` and nothing else.

- `CloseOrchestrator` calls NO state-changing tools. It delegates and gates.
- `IngestionAgent` / `MatchingAgent` are read-only (Matching also: lookup_vendor).
- `AnomalyAgent` may `flag_transaction` (safe) and may PROPOSE adjustments.
- `NarrativeAgent` may ONLY `write_audit_log`. It must never reach money tools.

## 3. `post_adjustment` is gated — no exceptions
`post_adjustment` must always pass through ADK's tool-confirmation flow before
executing. Never wire it to an agent directly. Never add a code path that
auto-approves it. Any adjustment ≥ AMOUNT_CONFIRMATION_THRESHOLD_CENTS is force
-confirmed regardless of upstream logic.

## 4. The guardrail is mandatory on every agent
Every agent is constructed with `before_tool_callback=security_guardrail`.
The guardrail enforces: default-deny privilege scoping, the amount threshold,
and PII masking of account numbers / personal identifiers before any log write.

## 5. Audit log is append-only
Never generate update or delete operations against `audit_log`. The close must
remain fully reconstructable.

## 6. Determinism
The dataset uses a fixed SEED. Do not introduce nondeterministic behavior
(unseeded random, wall-clock-dependent logic) into data generation or matching.

## 7. Comments are design documentation
Tool and agent code must carry docstrings explaining design intent and
behavior, not just what the line does.
