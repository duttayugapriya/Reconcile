# Reconcile Deployment Guide

## Session Service Configuration
ADK's human-in-the-loop tool-confirmation feature does not support `DatabaseSessionService` or `VertexAiSessionService` out of the box. 

When deploying Reconcile in production, configure the runner to use `InMemorySessionService` to ensure correct handling of the paused/resumed invocation states:

```python
from google.adk.runners import InMemoryRunner
# Use InMemoryRunner which defaults to InMemorySessionService
runner = InMemoryRunner(agent=root_agent, app_name="reconcile")
```
