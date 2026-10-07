"""
AgentGuard Audit Log
Append-only JSONL log of every tool call decision.
"""

import json
import threading
from pathlib import Path
from datetime import datetime


class AuditLog:
    """
    Thread-safe append-only audit log in JSONL format.
    Every tool call — allowed, blocked, or approval-requested — is recorded.
    """

    def __init__(self, path: str):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._entries: list[dict] = []
        # Load existing entries if file exists
        if self.path.exists():
            with open(self.path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            self._entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass

    def write(self, entry: dict):
        entry.setdefault("timestamp", datetime.utcnow().isoformat())
        with self._lock:
            self._entries.append(entry)
            with open(self.path, "a") as f:
                f.write(json.dumps(entry) + "\n")

    def get_all(self) -> list[dict]:
        with self._lock:
            return list(self._entries)

    def get_recent(self, n: int = 50) -> list[dict]:
        with self._lock:
            return list(self._entries[-n:])

    def get_stats(self) -> dict:
        entries = self.get_all()
        stats = {"total": len(entries), "allow": 0, "block": 0,
                 "require_approval": 0, "approval_granted": 0, "approval_denied": 0}
        for e in entries:
            d = e.get("decision", "")
            if d in stats:
                stats[d] += 1
        return stats

    def clear(self):
        with self._lock:
            self._entries = []
            if self.path.exists():
                self.path.unlink()
