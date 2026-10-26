"""Private, read-only HashMargin worker monitor.

Run locally only. This module is NOT imported by staging.py or render.yaml.
Requires BRAIINS_POOL_TOKEN and HASHMARGIN_MONITOR_KEY in the environment.
Binds to 127.0.0.1 by design; do not expose via public proxy.
"""
import hmac
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from integrations.braiins_pool import fetch_workers, summarize

CACHE_SECONDS = 60
_cache = {"at": 0.0, "result": None}
_lock = threading.Lock()

def snapshot(now=None, fetch=fetch_workers):
    now = time.monotonic() if now is None else now
    with _lock:
        if _cache["result"] is not None and now - _cache["at"] < CACHE_SECONDS:
            return _cache["result"]
        workers = fetch()
        result = {"status": "ok", "summary": summarize(workers),
                  "workers": workers, "source": "braiins", "cached_for_seconds": CACHE_SECONDS}
        _cache.update(at=now, result=result)
        return result

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            return self.reply(200, {"status": "ok", "mode": "private-monitor"})
        if self.path != "/v1/workers":
            return self.reply(404, {"error": "not_found"})
        expected = os.environ.get("HASHMARGIN_MONITOR_KEY", "")
        supplied = self.headers.get("Authorization", "")
        if not expected or not hmac.compare_digest(supplied, "Bearer " + expected):
            return self.reply(401, {"error": "unauthorized"})
        try:
            return self.reply(200, snapshot())
        except Exception:
            # Never log or return pool credentials, account data, or upstream details.
            return self.reply(503, {"error": "upstream_unavailable"})

    def reply(self, status, payload):
        data = json.dumps(payload, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        pass

if __name__ == "__main__":
    if not os.environ.get("BRAIINS_POOL_TOKEN") or not os.environ.get("HASHMARGIN_MONITOR_KEY"):
        raise SystemExit("Set BRAIINS_POOL_TOKEN and HASHMARGIN_MONITOR_KEY privately before starting")
    ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("MONITOR_PORT", "8765"))), Handler).serve_forever()
