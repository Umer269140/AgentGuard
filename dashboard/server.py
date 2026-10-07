"""
AgentGuard Dashboard Server
Serves a real-time dashboard of agent activity over HTTP.
Zero-cost: uses only Python stdlib (http.server + threading).
"""

import sys
import json
import threading
import time
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))
from agentguard.audit_log import AuditLog

AUDIT_LOG = Path("agentguard_audit.jsonl")
PORT = 8765


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress access logs

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/" or parsed.path == "/index.html":
            self._serve_html()
        elif parsed.path == "/api/events":
            self._serve_events()
        elif parsed.path == "/api/stats":
            self._serve_stats()
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_html(self):
        html = Path(__file__).parent / "index.html"
        content = html.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", len(content))
        self.end_headers()
        self.wfile.write(content)

    def _serve_events(self):
        audit = AuditLog(str(AUDIT_LOG))
        entries = audit.get_recent(100)
        data = json.dumps(entries).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _serve_stats(self):
        audit = AuditLog(str(AUDIT_LOG))
        stats = audit.get_stats()
        data = json.dumps(stats).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)


def run():
    server = HTTPServer(("0.0.0.0", PORT), DashboardHandler)
    print(f"\n  🛡️  AgentGuard Dashboard running at http://localhost:{PORT}")
    print(f"  Watching: {AUDIT_LOG.resolve()}")
    print(f"  Press Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Dashboard stopped.")


if __name__ == "__main__":
    run()
