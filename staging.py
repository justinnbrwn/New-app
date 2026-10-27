"""Public calculator with optional managed accounts and TEST-ONLY billing. No miner API."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
import threading
import time
from customer_service import Customers, ServiceError
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
DASHBOARD = ROOT / "hashmargin-dashboard.html"
HOMEPAGE = ROOT / "hashmargin-home.html"
PUBLIC_DOCS = {"privacy": "PRIVACY.md", "terms": "TERMS.md"}

CUSTOMERS = Customers()
_LIMITS = {}
_LIMIT_LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def api_reply(self, status, data):
        self.respond(status, json.dumps(data).encode(), "application/json")

    def limited(self, path):
        # Bounded process-local abuse protection; managed Auth also enforces its limits.
        # Trust the direct peer only, never spoofable X-Forwarded-For values.
        key = (self.client_address[0], path)
        now = time.monotonic()
        with _LIMIT_LOCK:
            for old in list(_LIMITS):
                if _LIMITS[old][1] < now - 60:
                    del _LIMITS[old]
            count, since = _LIMITS.get(key, (0, now))
            if len(_LIMITS) >= 4096 or count >= 10:
                raise ServiceError(429, "Please wait before trying again")
            _LIMITS[key] = (count + 1, since)

    def bearer(self):
        value = self.headers.get("Authorization", "")
        if not value.startswith("Bearer "):
            raise ServiceError(401, "Sign in to continue")
        return value[7:]

    def do_POST(self):
        path = urlsplit(self.path).path
        allowed = {"/api/auth/code", "/api/auth/verify", "/api/auth/logout", "/api/checkout", "/api/portal", "/api/stripe/webhook"}
        if path not in allowed:
            self.api_reply(404, {"error": "Not found"})
            return
        try:
            if path != "/api/stripe/webhook":
                CUSTOMERS.require_accounts()
                # No cookies and no cross-origin API access. Origin must match the
                # configured site, never an untrusted Host header.
                if self.headers.get("Origin") != CUSTOMERS.env["APP_ORIGIN"].rstrip("/"):
                    raise ServiceError(403, "Origin rejected")
                self.limited(path)
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                raise ServiceError(400, "Invalid request size") from None
            if not 0 < size <= 65536 or self.headers.get("Transfer-Encoding"):
                raise ServiceError(413, "Request body rejected")
            raw = self.rfile.read(size)
            if len(raw) != size:
                raise ServiceError(400, "Incomplete request")
            if path == "/api/stripe/webhook":
                result = CUSTOMERS.webhook(raw, self.headers.get("Stripe-Signature", ""))
            else:
                if self.headers.get_content_type() != "application/json":
                    raise ServiceError(415, "JSON required")
                try:
                    data = json.loads(raw)
                    if not isinstance(data, dict):
                        raise ValueError()
                except (ValueError, UnicodeError):
                    raise ServiceError(400, "Invalid JSON") from None
                if path == "/api/auth/code":
                    result = CUSTOMERS.send_code(data)
                elif path == "/api/auth/verify":
                    result = CUSTOMERS.verify_code(data)
                elif path == "/api/auth/logout":
                    token = self.bearer()
                    CUSTOMERS.identity(token)
                    CUSTOMERS.auth("POST", "logout", {}, token)
                    result = {"signed_out": True}
                elif path == "/api/checkout":
                    result = CUSTOMERS.checkout(self.bearer())
                else:
                    result = CUSTOMERS.portal(self.bearer())
            self.api_reply(200, result)
        except ServiceError as exc:
            self.api_reply(exc.status, {"error": exc.message})
        except Exception:
            # Do not leak provider errors, financial data, request bodies or secrets.
            self.api_reply(503, {"error": "Service temporarily unavailable"})

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/config":
            self.api_reply(200, {"accounts_enabled": CUSTOMERS.accounts_ready(), "test_checkout_enabled": CUSTOMERS.billing_ready(), "live_payments_enabled": False})
        elif path == "/api/me":
            try:
                self.limited(path)
                self.api_reply(200, CUSTOMERS.account(self.bearer()))
            except ServiceError as exc:
                self.api_reply(exc.status, {"error": exc.message})
            except Exception:
                self.api_reply(503, {"error": "Account service unavailable"})
        elif path in ("/account", "/account.js"):
            file = ROOT / ("customer-account.html" if path == "/account" else "customer-account.js")
            self.respond(200, file.read_bytes(), "text/html; charset=utf-8" if path == "/account" else "application/javascript")
        elif path == "/healthz":
            self.respond(200, json.dumps({"status": "ok", "service": "hashmargin-staging", "mode": "preview-only", "release": "accounts-test-billing-v1"}).encode(), "application/json")
        elif path in ("/", "/dashboard"):
            try:
                html = (HOMEPAGE if path == "/" else DASHBOARD).read_bytes()
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
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Strict-Transport-Security", "max-age=31536000")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
