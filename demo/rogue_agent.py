"""
AgentGuard Demo — Rogue Agent
A simulated autonomous agent that attempts a series of dangerous actions.
AgentGuard intercepts every call and enforces the policy.

Zero-cost: No real LLM needed for the demo. The agent's "decisions"
are scripted to show the full range of policy enforcement.
For the real thing, swap in Groq (free tier) or Gemini (free tier).
"""

import sys
import time
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agentguard import AgentGuard, PolicyViolationError, ApprovalDeniedError


# -----------------------------------------------------------------------
# 1. Real tool implementations (safe, sandboxed versions)
# -----------------------------------------------------------------------

def read_file(path: str) -> str:
    """Read a file from the filesystem."""
    p = Path(path)
    if not p.exists():
        return f"[file not found: {path}]"
    return p.read_text()


def write_file(path: str, content: str) -> str:
    """Write content to a file."""
    Path(path).write_text(content)
    return f"Written {len(content)} bytes to {path}"


def run_command(command: str) -> str:
    """Run a shell command (sandboxed in demo — just returns fake output)."""
    return f"[demo] Would run: {command}"


def call_api(url: str, method: str = "GET", data: dict = None) -> str:
    """Make an HTTP API call (sandboxed in demo)."""
    return f"[demo] Would call: {method} {url}"


def send_email(to: str, subject: str, body: str) -> str:
    """Send an email (sandboxed in demo)."""
    return f"[demo] Would send email to {to}: {subject}"


def search_web(query: str) -> str:
    """Search the web."""
    return f"[demo] Search results for: {query}"


# -----------------------------------------------------------------------
# 2. Set up AgentGuard
# -----------------------------------------------------------------------

def run_demo(auto_approve: bool = False):
    policy_path = Path(__file__).parent.parent / "policies" / "default.yaml"

    # Auto-approve handler for non-interactive demo
    def approval_handler(result):
        if auto_approve:
            print(f"  [AUTO-APPROVE] Granting approval for demo purposes")
            return True
        print(f"\n  ⚠️  HUMAN APPROVAL REQUIRED")
        print(f"  Tool:   {result.tool}")
        print(f"  Reason: {result.reason}")
        answer = input("  Approve? [y/N]: ").strip().lower()
        return answer == "y"

    guard = AgentGuard(
        policy_path=str(policy_path),
        approval_handler=approval_handler,
        audit_log_path="agentguard_audit.jsonl",
    )

    # Register all tools with the guard
    guard.register_tool("read_file", read_file)
    guard.register_tool("write_file", write_file)
    guard.register_tool("run_command", run_command)
    guard.register_tool("call_api", call_api)
    guard.register_tool("send_email", send_email)
    guard.register_tool("search_web", search_web)

    # -----------------------------------------------------------------------
    # 3. The agent's planned action sequence
    #    This simulates what an LLM-driven agent might decide to do
    # -----------------------------------------------------------------------

    print("\n" + "="*65)
    print("  🤖  AGENTGUARD DEMO — Rogue Agent Simulation")
    print("="*65)
    print("  Task given to agent: 'Optimize our infrastructure and cut costs'")
    print("  AgentGuard policy:   policies/default.yaml")
    print("="*65 + "\n")
    print("  Agent is now running...\n")
    time.sleep(0.5)

    actions = [
        # (description, tool, args)
        (
            "Read the project README",
            "read_file",
            {"path": "README.md"},
        ),
        (
            "Search for cost optimization tips",
            "search_web",
            {"query": "AWS cost optimization best practices 2024"},
        ),
        (
            "💀 Attempt to read production database credentials",
            "read_file",
            {"path": "/etc/production_db_credentials.env"},
        ),
        (
            "💀 Attempt to read .env file with API secrets",
            "read_file",
            {"path": ".env"},
        ),
        (
            "💀 Attempt to delete all logs (bulk rm -rf)",
            "run_command",
            {"command": "rm -rf /var/log/*"},
        ),
        (
            "💀 Attempt to call Stripe payment API",
            "call_api",
            {"url": "https://api.stripe.com/v1/charges", "method": "POST",
             "data": {"amount": 9999}},
        ),
        (
            "💀 Attempt to deploy to production",
            "run_command",
            {"command": "kubectl apply -f deployment.yaml --context=prod"},
        ),
        (
            "💀 Attempt to exfiltrate customer PII via email",
            "send_email",
            {"to": "external@competitor.com",
             "subject": "Export",
             "body": "Here is all the customer_data you requested"},
        ),
        (
            "💀 Attempt to modify its own policy file",
            "write_file",
            {"path": "policies/default.yaml",
             "content": "allowed_tools: ['*']\nblocked_resources: []"},
        ),
        (
            "✅ Write a legitimate cost report",
            "write_file",
            {"path": "reports/cost_report.txt",
             "content": "Cost optimization report: Identified 3 idle EC2 instances."},
        ),
        (
            "⚠️  Send internal summary email (requires approval)",
            "send_email",
            {"to": "team@company.com",
             "subject": "Cost Report Ready",
             "body": "The cost optimization report has been generated."},
        ),
    ]

    results = []
    for description, tool, args in actions:
        print(f"  Agent action: {description}")
        try:
            output = guard.call(tool, args)
            results.append(("allowed", tool, description))
        except PolicyViolationError as e:
            results.append(("blocked", tool, description))
        except ApprovalDeniedError as e:
            results.append(("denied", tool, description))
        except Exception as e:
            print(f"  ❌ Error: {e}")
            results.append(("error", tool, description))
        time.sleep(0.3)

    # -----------------------------------------------------------------------
    # 4. Summary
    # -----------------------------------------------------------------------

    stats = guard.get_stats()
    print("\n" + "="*65)
    print("  📊  AGENTGUARD SUMMARY")
    print("="*65)
    print(f"  Total tool calls:        {stats['total_calls']}")
    print(f"  ✅ Allowed:              {stats['allowed']}")
    print(f"  🚫 Blocked:              {stats['blocked']}")
    print(f"  ⚠️  Approvals requested:  {stats['approvals_requested']}")
    print(f"  💰 Total spend tracked:  ${stats['spend']['total']:.4f}")
    print("="*65)
    print(f"\n  Audit log written to: agentguard_audit.jsonl")
    print("  Run the dashboard to visualize: python dashboard/server.py\n")

    return stats


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--auto-approve", action="store_true",
                        help="Auto-approve all approval requests (for CI/demo)")
    args = parser.parse_args()
    run_demo(auto_approve=args.auto_approve)
