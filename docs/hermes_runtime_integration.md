# Hermes Runtime Integration Lockdown

Phase 15.8B connects the runtime context firewall to actual command execution.

## Mandatory rule

Hermes must use:

```python
from memoryx.runtime_context import HermesRuntimeContext
```

Do not pass raw terminal stdout/stderr directly back into a model prompt.

## Safe command execution

```python
runtime = HermesRuntimeContext("./memoryx_runtime.db")
runtime.begin_request("task-id", "request-id")
result = runtime.run_command(
    task_id="task-id",
    request_id="request-id",
    command="pytest -q",
)
prompt = runtime.assemble_prompt(task_id="task-id", request_id="request-id")
```

The result is prompt-safe:

* full stdout stored as artifact
* full stderr stored as artifact
* bounded summaries returned inline
* patch/diff stored artifact-only
* stale task requests rejected
