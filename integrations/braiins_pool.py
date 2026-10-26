"""Read-only Braiins Pool client. NOT imported by the public staging service.

Run locally with a limited read-only Braiins Pool access-profile token in
BRAIINS_POOL_TOKEN environment variable. Never paste tokens into GitHub or chat.
"""
import json
import os
from urllib.request import Request, urlopen

WORKERS_URL = "https://pool.braiins.com/accounts/workers/json/btc"

def fetch_workers(token=None, opener=urlopen):
    token = token or os.environ.get("BRAIINS_POOL_TOKEN")
    if not token:
        raise ValueError("BRAIINS_POOL_TOKEN is required (read-only access profile)")
    if any(c in token for c in "\r\n"):
        raise ValueError("Invalid token")
    req = Request(WORKERS_URL, headers={"Pool-Auth-Token": token, "Accept": "application/json"}, method="GET")
    with opener(req, timeout=12) as response:
        if response.status != 200:
            raise RuntimeError("Braiins Pool returned an unsuccessful status")
        data = response.read(1_000_001)
    if len(data) > 1_000_000:
        raise ValueError("Pool response too large")
    result = json.loads(data)
    workers = result.get("btc", {}).get("workers", {})
    if not isinstance(workers, dict):
        raise ValueError("Unexpected workers response")
    # Only operational telemetry, never echo API tokens or account financial details.
    return [{"name": str(name), "state": str(v.get("state", "unknown")),
             "hash_rate_5m": v.get("hash_rate_5m"),
             "hash_rate_unit": v.get("hash_rate_unit"),
             "last_share": v.get("last_share")}
            for name, v in workers.items() if isinstance(v, dict)]

def summarize(workers):
    offline = [w["name"] for w in workers if w["state"] in ("off", "dis")]
    low = [w["name"] for w in workers if w["state"] == "low"]
    return {"workers": len(workers), "offline_count": len(offline),
            "low_count": len(low), "needs_attention": bool(offline or low)}
