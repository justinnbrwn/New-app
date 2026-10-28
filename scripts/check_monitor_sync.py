"""Read-only Windows link diagnostic. No telemetry, email, or plaintext key upload."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import time
from datetime import timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler

ORIGIN = 'https://hashmargin-preview.onrender.com'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check(text, opener=None, clock=time.time):
    # Read only the two literal settings written by our setup commands.
    settings = {}
    pattern = r'''(?m)^\s*\$env:(HASHMARGIN_MONITOR_KEY|HASHMARGIN_ACCOUNT_ORIGIN)\s*=\s*(['"])([^'"\r\n]*)\2\s*$'''
    for match in re.finditer(pattern, text, re.IGNORECASE):
        settings[match[1].upper()] = match[3]
    origin = settings.get('HASHMARGIN_ACCOUNT_ORIGIN', '')
    key = settings.get('HASHMARGIN_MONITOR_KEY', '')
    if origin.rstrip('/') != ORIGIN:
        return 'ORIGIN_SETTING_MISSING_OR_INCORRECT'
    if not key:
        return 'WINDOWS_MONITOR_KEY_NOT_FOUND_IN_STARTUP'
    if len(key) < 32:
        return 'WINDOWS_MONITOR_KEY_TOO_SHORT'
    # Deliberately invalid workers value: valid auth must stop at validation before any DB write.
    raw = b'{"workers":null}'
    now = int(clock())
    stamp = str(now)
    signature = hmac.new(key.encode(), stamp.encode() + b'.' + raw, hashlib.sha256).hexdigest()
    request = Request(ORIGIN + '/api/monitor/publish', raw,
        {'Content-Type':'application/json', 'X-HashMargin-Signature':stamp + ':' + signature}, method='POST')
    open_request = opener or build_opener(NoRedirect).open
    try:
        with open_request(request, timeout=45) as response:
            return 'UNEXPECTED_RESPONSE_NO_WORKER_DATA_SENT'
    except HTTPError as error:
        if error.code == 400:
            try:
                body = json.loads(error.read(4096))
            except Exception:
                return 'HTTP_400_UNEXPECTED_RESPONSE'
            return ('KEY_MATCH_OK_NO_DATA_WRITTEN' if body.get('error') == 'Expected at most 200 workers'
                    else 'HTTP_400_UNEXPECTED_RESPONSE')
        if error.code == 401:
            try:
                server_time = parsedate_to_datetime(error.headers['Date'])
                if server_time.tzinfo is None:
                    server_time = server_time.replace(tzinfo=timezone.utc)
                if abs(server_time.timestamp() - now) > 300:
                    return 'WINDOWS_CLOCK_DIFFERS_BY_OVER_FIVE_MINUTES'
            except Exception:
                pass
            return 'WINDOWS_AND_RENDER_KEYS_DO_NOT_MATCH'
        if error.code == 503:
            return 'SERVER_COLLECTOR_NOT_LINKED_OR_TEMPORARILY_UNAVAILABLE'
        return 'SERVER_HTTP_' + str(error.code)
    except (URLError, TimeoutError, OSError):
        return 'NETWORK_OR_TLS_CONNECTION_FAILED'


def main():
    startup = Path(os.environ['APPDATA']) / 'HashMarginPro' / 'start-monitor.ps1'
    raw = startup.read_bytes()
    text = raw.decode('utf-16') if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else raw.decode('utf-8-sig')
    print('MONITOR LINK CHECK:', check(text))
    print('No worker snapshots or emails were sent. No secret values were displayed.')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('MONITOR LINK CHECK: STARTUP_FILE_COULD_NOT_BE_READ')
