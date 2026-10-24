"""
AgentGuard Interceptor
The core enforcement layer — sits between the agent and every tool it calls.
Every tool call passes through here before execution.
"""

import time
import json
import logging
from typing import Callable, Any, Optional
from datetime import datetime
from .policy import PolicyEngine, PolicyResult, Decision
from .audit_log import AuditLog

logger = logging.getLogger("agentguard")


class AgentGuard:
    """
    Drop-in enforcement wrapper for any AI agent's tool calls.

    Usage:
        guard = AgentGuard("policies/default.yaml")

        # Wrap a tool before the agent calls it
        result = guard.call("write_file", {"path": "/etc/passwd", "content": "..."})
        # ^ This will be BLOCKED before it runs

    AgentGuard intercepts, evaluates policy, then either:
      - Executes the tool (ALLOW)
      - Blocks it and raises an exception (BLOCK)
      - Pauses and asks for human approval (REQUIRE_APPROVAL)
    """

    def __init__(
        self,
        policy_path: str,
        approval_handler: Optional[Callable] = None,
        audit_log_path: str = "agentguard_audit.jsonl",
        silent: bool = False,
    ):
        self.engine = PolicyEngine(policy_path)
        self.audit = AuditLog(audit_log_path)
        self._approval_handler = approval_handler or self._default_approval_handler
        self._tools: dict[str, Callable] = {}
        self._silent = silent
        self._stats = {
            "total_calls": 0,
            "allowed": 0,
            "blocked": 0,
            "approvals_requested": 0,
            "approvals_granted": 0,
            "approvals_denied": 0,
        }

    # ------------------------------------------------------------------
    # Tool registration
    # ------------------------------------------------------------------

    def register_tool(self, name: str, fn: Callable):
        """Register a callable tool that the agent can use."""
        self._tools[name] = fn

    def tool(self, name: str):
        """Decorator to register a tool."""
        def decorator(fn: Callable):
            self.register_tool(name, fn)
            return fn
        return decorator

    # ------------------------------------------------------------------
    # Main interception entrypoint
    # ------------------------------------------------------------------

    def call(self, tool: str, args: dict = None) -> Any:
        """
        The agent calls this instead of calling a tool directly.
        AgentGuard evaluates policy, then decides what to do.
        """
        args = args or {}
        self._stats["total_calls"] += 1
        timestamp = datetime.utcnow().isoformat()

        # --- Evaluate policy ---
        result: PolicyResult = self.engine.evaluate(tool, args)

        # --- Log the decision ---
        log_entry = {
            "timestamp": timestamp,
            "tool": tool,
            "args": args,
            "decision": result.decision.value,
            "reason": result.reason,
            "rule": result.rule_name,
        }
        self.audit.write(log_entry)

        if not self._silent:
            self._print_decision(result)

        # --- Act on the decision ---
        if result.decision == Decision.BLOCK:
            self._stats["blocked"] += 1
            raise PolicyViolationError(result)

        if result.decision == Decision.REQUIRE_APPROVAL:
            self._stats["approvals_requested"] += 1
            approved = self._approval_handler(result)
            if not approved:
                self._stats["approvals_denied"] += 1
                log_entry["decision"] = "approval_denied"
                self.audit.write(log_entry)
                raise ApprovalDeniedError(result)
            self._stats["approvals_granted"] += 1
            log_entry["decision"] = "approval_granted"
            self.audit.write(log_entry)

        # --- Execute the tool ---
        if tool not in self._tools:
            raise ToolNotRegisteredError(f"Tool '{tool}' is not registered with AgentGuard")

        self._stats["allowed"] += 1
        self.engine.record_spend(tool)

        try:
            output = self._tools[tool](**args)
            return output
        except Exception as e:
            logger.error(f"Tool '{tool}' raised an exception: {e}")
            raise

    # ------------------------------------------------------------------
    # Approval handler
    # ------------------------------------------------------------------

    def _default_approval_handler(self, result: PolicyResult) -> bool:
        """
        Default: interactive CLI approval prompt.
        In production, replace this with a Slack/email/webhook flow.
        """
        print(f"\n{'='*60}")
        print(f"  ⚠️  HUMAN APPROVAL REQUIRED")
        print(f"{'='*60}")
        print(f"  Tool:   {result.tool}")
        print(f"  Args:   {json.dumps(result.args, indent=2)}")
        print(f"  Reason: {result.reason}")
        print(f"{'='*60}")
        answer = input("  Approve? [y/N]: ").strip().lower()
        return answer == "y"

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        return {
            **self._stats,
            "spend": self.engine.get_spend_summary(),
        }

    def _print_decision(self, result: PolicyResult):
        icons = {
            Decision.ALLOW: "✅",
            Decision.BLOCK: "🚫",
            Decision.REQUIRE_APPROVAL: "⚠️ ",
        }
        icon = icons[result.decision]
        print(f"  {icon} [{result.decision.value.upper()}] {result.tool}() — {result.reason}")


# ------------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------------

class PolicyViolationError(Exception):
    def __init__(self, result: PolicyResult):
        self.result = result
        super().__init__(
            f"[AgentGuard] BLOCKED: {result.tool}() — {result.reason} (rule: {result.rule_name})"
        )


class ApprovalDeniedError(Exception):
    def __init__(self, result: PolicyResult):
        self.result = result
        super().__init__(
            f"[AgentGuard] DENIED: {result.tool}() — approval was not granted"
        )


class ToolNotRegisteredError(Exception):
    pass
