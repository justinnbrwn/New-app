"""Safe public HashMargin preview. No miner connections, credentials, accounts or payments."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
from urllib.parse import urlsplit

DASHBOARD = Path(__file__).resolve().parent / "hashmargin-dashboard.html"
PUBLIC_DOCS = {"privacy": "PRIVACY.md", "terms": "TERMS.md"}

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/healthz":
            self.respond(200, json.dumps({"status": "ok", "service": "hashmargin-staging", "mode": "preview-only"}).encode(), "application/json")
        elif path in ("/", "/dashboard"):
            try:
                html = DASHBOARD.read_bytes()
            except OSError:
                self.respond(503, b"Dashboard unavailable", "text/plain; charset=utf-8")
                return
            self.respond(200, html, "text/html; charset=utf-8")
        elif path in ("/privacy", "/terms"):
            try:
                body = (DASHBOARD.parent / PUBLIC_DOCS[path.lstrip("/")]).read_bytes()
            except OSError:
                self.respond(503, b"Document unavailable", "text/plain; charset=utf-8")
                return
            self.respond(200, body, "text/plain; charset=utf-8")
        else:
            self.respond(404, b"Not found", "text/plain; charset=utf-8")

    def respond(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
