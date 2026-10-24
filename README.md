# 🛡️ AgentGuard

**Runtime safety and control layer for autonomous AI agents.**

AgentGuard sits between your AI agent and its tools, enforcing human-defined policies before any action executes — blocking dangerous calls, requiring approval for risky ones, and logging everything.

```
Agent  →  AgentGuard  →  Tool
          (policy check)
          ↓ ALLOW / BLOCK / REQUIRE_APPROVAL
```

## Why AgentGuard?

Autonomous agents are powerful — and dangerous. A single misconfigured prompt can cause an agent to:
- Read production credentials or `.env` files
- Delete critical data with `rm -rf`
- Exfiltrate customer PII via email
- Deploy untested code to production
- Modify its own guardrails

AgentGuard intercepts every tool call and enforces a human-readable YAML policy — in real time, before any damage is done.

## Quick Start

```bash
# Install
pip install -r requirements.txt

# Run the demo (simulates a rogue agent)
python demo/rogue_agent.py --auto-approve

# Watch it live in the dashboard
python dashboard/server.py
# Open http://localhost:8765
```

## How It Works

### 1. Define your policy (`policies/default.yaml`)

```yaml
allowed_tools:
  - read_file
  - write_file
  - run_command
  - call_api
  - send_email
  - search_web

blocked_resources:
  production_database:
    pattern: "(production_db|prod.*credential|db_password)"
    message: "Production databases are off-limits"
  env_secrets:
    pattern: "\\.env$|\\.env\\."
    message: "Secret/credential files cannot be read or written"

require_approval:
  bulk_delete:
    pattern: "rm\\s+-rf"
    message: "Bulk deletion requires human sign-off"
  deploy_to_prod:
    pattern: "kubectl.*--context=prod"
    message: "Production deployments require human approval"

custom_rules:
  no_data_exfiltration:
    type: "pattern_match"
    pattern: "(customer_data|PII|personal.*data)"
    tools: ["send_email", "call_api"]
    message: "Potential PII/customer data exfiltration detected"
  no_self_modification:
    type: "path_protection"
    pattern: "policies/"
    tools: ["write_file"]
    message: "Agent cannot modify its own guardrails"
```

### 2. Wrap your tools with AgentGuard

```python
from agentguard import AgentGuard

guard = AgentGuard(
    policy_path="policies/default.yaml",
    approval_handler=lambda result: input(f"Approve {result.tool}? [y/N]: ") == "y",
    audit_log_path="agentguard_audit.jsonl",
)

guard.register_tool("read_file", read_file)
guard.register_tool("run_command", run_command)
# ... register all your tools
```

### 3. Route all agent tool calls through the guard

```python
from agentguard import PolicyViolationError, ApprovalDeniedError

try:
    result = guard.call("run_command", {"command": "rm -rf /var/log/*"})
except PolicyViolationError as e:
    print(f"Blocked: {e}")   # → Blocked: Bulk deletion requires human sign-off
except ApprovalDeniedError as e:
    print(f"Denied: {e}")
```

### 4. Or use as a decorator

```python
@guard.tool("read_file")
def read_file(path: str) -> str:
    return Path(path).read_text()
```

## Policy Decision Types

| Decision | Meaning |
|----------|---------|
| `ALLOW` | Tool call passes all checks — executes normally |
| `BLOCK` | Policy violation — raises `PolicyViolationError`, tool never executes |
| `REQUIRE_APPROVAL` | Pauses for human review — raises `ApprovalDeniedError` if denied |

## Policy Checks (in order)

1. **Allowed tools** — Is this tool permitted at all?
2. **Blocked resources** — Do the args match any forbidden pattern?
3. **Spend limits** — Would this call exceed the budget?
4. **Approval rules** — Does this need a human in the loop?
5. **Custom rules** — Any additional business logic?

## Audit Log

Every call is logged to `agentguard_audit.jsonl`:

```json
{"timestamp": "2024-01-15T10:23:45", "tool": "run_command", "args": {"command": "rm -rf /var/log/*"}, "decision": "require_approval", "reason": "Bulk deletion requires human sign-off", "rule_name": "bulk_delete"}
```

## Dashboard

```bash
python dashboard/server.py
```

Real-time visualization of all agent activity — blocked attempts, approvals, and allowed calls — at `http://localhost:8765`. Works without a server too: open `dashboard/index.html` directly and click **▶ Run Demo**.

## Zero-Cost Stack

AgentGuard uses **zero paid services**:
- Pure Python stdlib (no frameworks)
- YAML policy files (no database)
- JSONL audit log (no cloud logging)
- Stdlib HTTP server for the dashboard
- No LLM required for the core enforcement layer

## Project Structure

```
agentguard/
├── agentguard/
│   ├── __init__.py       # Package exports
│   ├── policy.py         # Policy engine (YAML → decisions)
│   ├── interceptor.py    # AgentGuard class (main entrypoint)
│   └── audit_log.py      # Thread-safe JSONL audit log
├── policies/
│   └── default.yaml      # Default enterprise policy
├── demo/
│   └── rogue_agent.py    # Rogue agent simulation
├── dashboard/
│   ├── server.py         # Stdlib HTTP server
│   └── index.html        # Real-time dashboard UI
└── requirements.txt      # Only pyyaml
```

## License

MIT
