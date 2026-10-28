import hashlib
import hmac
import json
import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timezone
from account_monitor import AccountMonitor, clean_workers
from customer_service import ServiceError
from integrations.monitor_publish import publish_workers

OWNER = 'a251505e-d292-40b3-b7b6-b2b7ea0ab15c'
WORKERS = [{'name': '<worker>', 'state': 'off', 'hash_rate_5m': 0, 'hash_rate_unit': 'Gh/s'}]


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.customers = Mock()
        self.customers.env = {'HASHMARGIN_MONITOR_KEY': 'k' * 40, 'HASHMARGIN_MONITOR_USER_ID': OWNER,
            'SUPABASE_URL': 'https://project.supabase.co', 'SUPABASE_SERVICE_ROLE_KEY': 'server-only',
            'SUPABASE_ANON_KEY': 'publishable'}
        self.customers.identity.return_value = {'id': OWNER, 'email': 'owner@example.invalid'}
        self.monitor = AccountMonitor(self.customers, clock=lambda: 1000)

    def signature(self, raw, stamp='1000'):
        digest = hmac.new(b'k' * 40, stamp.encode() + b'.' + raw, hashlib.sha256).hexdigest()
        return stamp + ':' + digest

    def test_publish_forces_server_owner_and_strips_private_fields(self):
        raw = json.dumps({'workers': [{**WORKERS[0], 'pool_token': 'must-not-be-saved'}]}).encode()
        self.assertEqual(self.monitor.publish(raw, self.signature(raw))['worker_count'], 1)
        args = self.customers.transport.call_args.args
        self.assertEqual(args[3]['owner_id'], OWNER)
        self.assertNotIn('pool_token', args[3]['worker_data'][0])

    def test_signature_tampering_expiry_and_missing_link(self):
        raw = json.dumps({'workers': WORKERS}).encode()
        for signed in ['invalid', self.signature(raw, '1'), self.signature(b'other')]:
            with self.assertRaises(ServiceError): self.monitor.publish(raw, signed)
        self.customers.transport.assert_not_called()
        self.customers.env['HASHMARGIN_MONITOR_KEY'] = ''
        with self.assertRaises(ServiceError) as e: self.monitor.publish(raw, self.signature(raw))
        self.assertEqual(e.exception.status, 503)

    def test_payload_cannot_choose_an_owner(self):
        raw = json.dumps({'workers': WORKERS, 'user_id': OWNER}).encode()
        with self.assertRaises(ServiceError): self.monitor.publish(raw, self.signature(raw))

    def test_worker_bounds(self):
        for workers in [WORKERS * 201, WORKERS * 2, [{'name':'x','state':'bad'}],
                        [{**WORKERS[0], 'hash_rate_5m': float('nan')}],
                        [{**WORKERS[0], 'hash_rate_5m': True}], [{**WORKERS[0], 'name':'\n'}]]:
            with self.assertRaises(ServiceError): clean_workers(workers)

    def test_read_uses_authenticated_user_and_rls_token(self):
        self.customers.transport.return_value = [{'observed_at': datetime.fromtimestamp(999, timezone.utc).isoformat(), 'workers': WORKERS}]
        result = self.monitor.read('user-bearer')
        self.assertFalse(result['stale'])
        self.assertEqual(result['summary']['offline_count'], 1)
        call = self.customers.transport.call_args.args
        self.assertIn(OWNER, call[1]); self.assertEqual(call[2]['Authorization'], 'Bearer user-bearer')
        self.assertNotIn('server-only', str(call))

    def test_missing_and_stale_are_explicit(self):
        self.customers.transport.return_value = []
        self.assertFalse(self.monitor.read('token')['connected'])
        self.customers.transport.return_value = [{'observed_at':'1970-01-01T00:00:01+00:00', 'workers':[]}]
        self.assertTrue(self.monitor.read('token')['stale'])

    def test_local_publisher_is_opt_in_and_fixed_destination(self):
        with patch.dict('os.environ', {}, clear=True): self.assertFalse(publish_workers(WORKERS))
        with patch.dict('os.environ', {'HASHMARGIN_ACCOUNT_ORIGIN':'https://other.example', 'HASHMARGIN_MONITOR_KEY':'k'*40}):
            with self.assertRaises(ValueError): publish_workers(WORKERS)

    def test_local_publisher_sends_no_pool_secret(self):
        opener = Mock(); opener.return_value.__enter__ = Mock(return_value=Mock(status=200)); opener.return_value.__exit__ = Mock(return_value=False)
        with patch.dict('os.environ', {'HASHMARGIN_ACCOUNT_ORIGIN':'https://hashmargin-preview.onrender.com', 'HASHMARGIN_MONITOR_KEY':'k'*40, 'BRAIINS_POOL_TOKEN':'pool-secret'}):
            self.assertTrue(publish_workers(WORKERS, opener))
        req = opener.call_args.args[0]
        self.assertNotIn(b'pool-secret', req.data)
        self.assertEqual(set(json.loads(req.data)), {'workers'})


if __name__ == '__main__': unittest.main()
