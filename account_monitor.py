"""Private owner-pilot snapshot sync. Pool credentials stay on the collector."""
import hashlib
import hmac
import json
import math
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from customer_service import ServiceError, user_id
from integrations.braiins_pool import summarize


def clean_workers(value):
    if not isinstance(value, list) or len(value) > 200:
        raise ServiceError(400, 'Expected at most 200 workers')
    result, names = [], set()
    for worker in value:
        if not isinstance(worker, dict):
            raise ServiceError(400, 'Invalid worker')
        name, state = worker.get('name'), worker.get('state')
        if (not isinstance(name, str) or not 0 < len(name) <= 128
                or any(ord(c) < 32 for c in name) or name in names
                or state not in ('ok', 'off', 'dis', 'low', 'unknown')):
            raise ServiceError(400, 'Invalid worker identity or state')
        names.add(name)
        rate = worker.get('hash_rate_5m')
        if rate is not None and (isinstance(rate, bool) or not isinstance(rate, (int, float))
                                 or not math.isfinite(rate) or not 0 <= rate <= 1e18):
            raise ServiceError(400, 'Invalid worker hashrate')
        unit = worker.get('hash_rate_unit')
        if unit not in (None, 'Gh/s', 'Th/s', 'Ph/s', 'Mh/s', 'H/s'):
            raise ServiceError(400, 'Invalid hashrate unit')
        result.append({'name': name, 'state': state, 'hash_rate_5m': rate, 'hash_rate_unit': unit})
    return result


class AccountMonitor:
    def __init__(self, customers, clock=time.time):
        self.customers, self.clock = customers, clock

    def configuration_issues(self):
        """Safe startup diagnostics: setting names/reasons, never secret values."""
        env = self.customers.env
        issues = []
        key = env.get('HASHMARGIN_MONITOR_KEY', '')
        if not key:
            issues.append('HASHMARGIN_MONITOR_KEY missing')
        elif len(key) < 32:
            issues.append('HASHMARGIN_MONITOR_KEY shorter than 32 characters')
        if not env.get('HASHMARGIN_MONITOR_USER_ID'):
            issues.append('HASHMARGIN_MONITOR_USER_ID missing')
        if not env.get('SUPABASE_SERVICE_ROLE_KEY'):
            issues.append('SUPABASE_SERVICE_ROLE_KEY missing')
        return issues

    def publish(self, raw, signature):
        env = self.customers.env
        key = env.get('HASHMARGIN_MONITOR_KEY', '')
        owner = env.get('HASHMARGIN_MONITOR_USER_ID', '')
        if len(key) < 32 or not owner or not env.get('SUPABASE_SERVICE_ROLE_KEY'):
            raise ServiceError(503, 'Private collector is not linked yet')
        try:
            stamp, digest = signature.split(':', 1)
            if not stamp.isdigit() or abs(self.clock() - int(stamp)) > 300:
                raise ValueError()
            expected = hmac.new(key.encode(), stamp.encode() + b'.' + raw, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, digest):
                raise ValueError()
            data = json.loads(raw)
            if set(data) != {'workers'}:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise ServiceError(401, 'Invalid collector signature or payload') from None
        workers = clean_workers(data['workers'])
        observed = datetime.fromtimestamp(int(stamp), timezone.utc).isoformat()
        # Atomic monotonic update: replays and delayed requests cannot replace newer data.
        secret = env['SUPABASE_SERVICE_ROLE_KEY']
        self.customers.transport('POST', env['SUPABASE_URL'].rstrip('/') + '/rest/v1/rpc/publish_monitor_snapshot',
            {'apikey': secret, 'Authorization': 'Bearer ' + secret},
            {'owner_id': user_id(owner), 'seen_at': observed, 'worker_data': workers})
        return {'accepted': True, 'worker_count': len(workers)}

    def read(self, token):
        who = self.customers.identity(token)
        env = self.customers.env
        query = urlencode({'user_id': 'eq.' + who['id'], 'select': 'observed_at,workers', 'limit': '1'})
        rows = self.customers.transport('GET', env['SUPABASE_URL'].rstrip('/') + '/rest/v1/monitor_snapshots?' + query,
            {'apikey': env['SUPABASE_ANON_KEY'], 'Authorization': 'Bearer ' + token})
        if not rows:
            return {'connected': False, 'stale': True, 'workers': [], 'summary': None}
        row = rows[0]
        workers = clean_workers(row['workers'])
        age = self.clock() - datetime.fromisoformat(row['observed_at'].replace('Z', '+00:00')).timestamp()
        return {'connected': True, 'stale': age > 180 or age < -30, 'observed_at': row['observed_at'],
                'workers': workers, 'summary': summarize(workers), 'source': 'Private Braiins collector'}
