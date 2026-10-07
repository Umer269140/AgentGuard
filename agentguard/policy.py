"""
AgentGuard Policy Engine
Loads and enforces externally defined policies for AI agents.
"""

import yaml
import json
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum


class Decision(Enum):
    ALLOW = "allow"
    BLOCK = "block"
    REQUIRE_APPROVAL = "require_approval"


@dataclass
class PolicyResult:
    decision: Decision
    reason: str
    rule_name: str = ""
    tool: str = ""
    args: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "decision": self.decision.value,
            "reason": self.reason,
            "rule_name": self.rule_name,
            "tool": self.tool,
            "args": self.args,
        }


class PolicyEngine:
    """
    Loads a policy YAML and evaluates every tool call against it.
    Zero-cost: pure Python, no external services needed.
    """

    def __init__(self, policy_path: str):
        self.policy_path = Path(policy_path)
        self.policy = self._load(policy_path)
        self._spend_tracker: dict[str, float] = {}

    def _load(self, path: str) -> dict:
        with open(path) as f:
            return yaml.safe_load(f)

    def reload(self):
        self.policy = self._load(self.policy_path)

    # ------------------------------------------------------------------
    # Main entrypoint
    # ------------------------------------------------------------------

    def evaluate(self, tool: str, args: dict) -> PolicyResult:
        """
        Evaluate a tool call against the loaded policy.
        Returns a PolicyResult with ALLOW / BLOCK / REQUIRE_APPROVAL.
        """
        # 1. Check if tool is in the allowed tools list
        result = self._check_allowed_tools(tool, args)
        if result.decision != Decision.ALLOW:
            return result

        # 2. Check blocked resources (path patterns, domains, etc.)
        result = self._check_blocked_resources(tool, args)
        if result.decision != Decision.ALLOW:
            return result

        # 3. Check spending limits
        result = self._check_spend_limits(tool, args)
        if result.decision != Decision.ALLOW:
            return result

        # 4. Check approval requirements
        result = self._check_approval_rules(tool, args)
        if result.decision != Decision.ALLOW:
            return result

        # 5. Check custom rules
        result = self._check_custom_rules(tool, args)
        if result.decision != Decision.ALLOW:
            return result

        return PolicyResult(
            decision=Decision.ALLOW,
            reason="All policy checks passed",
            tool=tool,
            args=args,
        )

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_allowed_tools(self, tool: str, args: dict) -> PolicyResult:
        allowed = self.policy.get("allowed_tools")
        if allowed is None:
            # No restriction defined — allow all
            return PolicyResult(Decision.ALLOW, "No tool restriction", tool=tool, args=args)

        if "*" in allowed:
            return PolicyResult(Decision.ALLOW, "All tools allowed", tool=tool, args=args)

        if tool not in allowed:
            return PolicyResult(
                Decision.BLOCK,
                f"Tool '{tool}' is not in the allowed tools list",
                rule_name="allowed_tools",
                tool=tool,
                args=args,
            )

        return PolicyResult(Decision.ALLOW, "Tool is allowed", tool=tool, args=args)

    def _check_blocked_resources(self, tool: str, args: dict) -> PolicyResult:
        blocked = self.policy.get("blocked_resources", [])
        args_str = json.dumps(args)

        for rule in blocked:
            pattern = rule.get("pattern", "")
            applies_to = rule.get("tools", ["*"])

            if applies_to != ["*"] and tool not in applies_to:
                continue

            if re.search(pattern, args_str, re.IGNORECASE):
                return PolicyResult(
                    Decision.BLOCK,
                    f"Blocked resource pattern matched: {rule.get('description', pattern)}",
                    rule_name=rule.get("name", "blocked_resource"),
                    tool=tool,
                    args=args,
                )

        return PolicyResult(Decision.ALLOW, "No blocked resources matched", tool=tool, args=args)

    def _check_spend_limits(self, tool: str, args: dict) -> PolicyResult:
        limits = self.policy.get("spend_limits", {})
        if not limits:
            return PolicyResult(Decision.ALLOW, "No spend limits defined", tool=tool, args=args)

        cost_per_call = self.policy.get("tool_costs", {}).get(tool, 0)
        if cost_per_call == 0:
            return PolicyResult(Decision.ALLOW, "Tool has no cost", tool=tool, args=args)

        # Track per-tool spend
        current = self._spend_tracker.get(tool, 0.0)
        tool_limit = limits.get("per_tool", {}).get(tool)
        if tool_limit and (current + cost_per_call) > tool_limit:
            return PolicyResult(
                Decision.BLOCK,
                f"Spend limit exceeded for '{tool}': ${current:.4f} used, limit ${tool_limit}",
                rule_name="spend_limit_per_tool",
                tool=tool,
                args=args,
            )

        # Track total spend
        total = sum(self._spend_tracker.values())
        total_limit = limits.get("total")
        if total_limit and (total + cost_per_call) > total_limit:
            return PolicyResult(
                Decision.BLOCK,
                f"Total spend limit exceeded: ${total:.4f} used, limit ${total_limit}",
                rule_name="spend_limit_total",
                tool=tool,
                args=args,
            )

        return PolicyResult(Decision.ALLOW, "Within spend limits", tool=tool, args=args)

    def record_spend(self, tool: str):
        """Call this after a tool runs successfully to track spend."""
        cost = self.policy.get("tool_costs", {}).get(tool, 0)
        self._spend_tracker[tool] = self._spend_tracker.get(tool, 0.0) + cost

    def _check_approval_rules(self, tool: str, args: dict) -> PolicyResult:
        rules = self.policy.get("require_approval", [])
        args_str = json.dumps(args)

        for rule in rules:
            applies_to = rule.get("tools", ["*"])
            if applies_to != ["*"] and tool not in applies_to:
                continue

            pattern = rule.get("pattern")
            if pattern and not re.search(pattern, args_str, re.IGNORECASE):
                continue

            return PolicyResult(
                Decision.REQUIRE_APPROVAL,
                f"Human approval required: {rule.get('reason', 'policy rule')}",
                rule_name=rule.get("name", "approval_rule"),
                tool=tool,
                args=args,
            )

        return PolicyResult(Decision.ALLOW, "No approval required", tool=tool, args=args)

    def _check_custom_rules(self, tool: str, args: dict) -> PolicyResult:
        rules = self.policy.get("custom_rules", [])

        for rule in rules:
            applies_to = rule.get("tools", ["*"])
            if applies_to != ["*"] and tool not in applies_to:
                continue

            conditions = rule.get("conditions", [])
            args_str = json.dumps(args)

            for condition in conditions:
                if re.search(condition["pattern"], args_str, re.IGNORECASE):
                    action = rule.get("action", "block")
                    decision = Decision.BLOCK if action == "block" else Decision.REQUIRE_APPROVAL
                    return PolicyResult(
                        decision=decision,
                        reason=condition.get("reason", f"Custom rule matched: {rule.get('name')}"),
                        rule_name=rule.get("name", "custom_rule"),
                        tool=tool,
                        args=args,
                    )

        return PolicyResult(Decision.ALLOW, "No custom rules matched", tool=tool, args=args)

    def get_spend_summary(self) -> dict:
        return {
            "per_tool": dict(self._spend_tracker),
            "total": sum(self._spend_tracker.values()),
        }
