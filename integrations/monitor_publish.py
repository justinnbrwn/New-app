"""Optional signed upload of telemetry, never pool/SMTP secrets."""
import hashlib
import hmac
import json
import os
import time
from urllib.request import Request, build_opener
from customer_service import NoRedirect, https_origin
from account_monitor import clean_workers


def publish_workers(workers, opener=None):
    origin = os.environ.get('HASHMARGIN_ACCOUNT_ORIGIN', '')
    if not origin:
        return False
    # Fix the recipient; no arbitrary URL or redirect can receive the signature.
    if https_origin(origin) != 'https://hashmargin-preview.onrender.com':
        raise ValueError('Use the HashMargin account site')
    key = os.environ.get('HASHMARGIN_MONITOR_KEY', '')
    if len(key) < 32:
        raise ValueError('A private monitor key of at least 32 characters is required')
    raw = json.dumps({'workers': clean_workers(workers)}, allow_nan=False, separators=(',', ':')).encode()
    stamp = str(int(time.time()))
    digest = hmac.new(key.encode(), stamp.encode() + b'.' + raw, hashlib.sha256).hexdigest()
    request = Request(origin + '/api/monitor/publish', raw,
        {'Content-Type': 'application/json', 'X-HashMargin-Signature': stamp + ':' + digest}, method='POST')
    open_request = opener or build_opener(NoRedirect).open
    with open_request(request, timeout=15) as response:
        if response.status != 200:
            raise RuntimeError('Account sync failed')
    return True
