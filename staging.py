"""Safe public preview: no authentication, telemetry, database, or customer data."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os

PAYMENT_LINK = "https://buy.stripe.com/5kQdR24YccWu3y719p3VC00"

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/healthz"):
            self.send_error(404)
            return
        if self.path == "/healthz":
            body = json.dumps({"status": "ok", "service": "hashmargin-staging", "mode": "preview-only"}).encode("utf-8")
            content_type = "application/json"
        else:
            body = ("""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>HashMargin Pro | Coming Soon</title><style>body{font:16px system-ui,sans-serif;background:#101827;color:#f7f9fc;margin:0;padding:10vh 20px}main{max-width:620px;margin:auto}h1{font-size:2.6rem}p{line-height:1.6;color:#cbd5e1}.button{display:inline-block;background:#8067ef;color:white;padding:14px 22px;border-radius:9px;text-decoration:none;font-weight:700}small{display:block;margin-top:20px;color:#aebbd0}</style></head><body><main><h1>HashMargin Pro</h1><p>ASIC mining profitability tools are in development. Customer accounts and paid access are not available yet.</p><p>Interested in the $12/month subscription? Review the checkout details before purchasing. <strong>Purchasing does not currently grant software access.</strong></p><a class="button" href="""" + PAYMENT_LINK + """" rel="noopener noreferrer">View subscription checkout</a><small>Preview only. No customer logins, miner connections, or automatic subscription activation.</small></main></body></html>""").encode("utf-8")
            content_type = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
