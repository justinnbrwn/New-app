import hashlib
import hmac
import json
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from customer_service import Customers, ServiceError
import staging

UID = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'
ENV = {'HASHMARGIN_ACCOUNTS_ENABLED': 'true', 'HASHMARGIN_BILLING_MODE': 'test',
       'SUPABASE_URL': 'https://project.supabase.co', 'SUPABASE_ANON_KEY': 'public-test-key',
       'SUPABASE_SERVICE_ROLE_KEY': 'server-only-secret', 'APP_ORIGIN': 'https://hashmargin-preview.onrender.com',
       'STRIPE_SECRET_KEY': 'sk_test_fake', 'STRIPE_WEBHOOK_SECRET': 'whsec_fake', 'STRIPE_PRO_PRICE_ID': 'price_test'}


class FakeProvider:
    def __init__(self):
        self.calls = []
        self.owner = UID
        self.confirmed = True
        self.status = 'active'
        self.invoice = 'paid'
        self.rows = []
        self.live = False
        self.price_id = 'price_test'

    def __call__(self, method, url, headers, data=None, form=False):
        self.calls.append((method, url, headers, data))
        if '/auth/v1/user' in url:
            if headers.get('Authorization') != 'Bearer verified-token':
                raise ServiceError(401, 'Authentication rejected')
            return {'id': UID, 'email': 'test@example.com', 'email_confirmed_at': 'today' if self.confirmed else None}
        if '/auth/v1/verify' in url:
            return {'access_token': 'verified-token', 'refresh_token': 'DO-NOT-RETURN'}
        if '/auth/v1/otp' in url or '/auth/v1/logout' in url:
            return {}
        if '/rest/v1/' in url:
            return self.rows if method == 'GET' else {}
        if '/prices/' in url:
            return {'livemode': self.live, 'active': True, 'unit_amount': 1200, 'currency': 'usd', 'recurring': {'interval': 'month', 'interval_count': 1}}
        if '/subscriptions/' in url:
            return {'id': 'sub_test', 'livemode': self.live, 'metadata': {'hashmargin_user_id': self.owner}, 'customer': 'cus_test', 'status': self.status,
                    'latest_invoice': {'status': self.invoice}, 'items': {'data': [{'price': {'id': self.price_id}}]}}
        if '/checkout/sessions' in url:
            return {'livemode': self.live, 'url': 'https://checkout.stripe.com/c/pay/cs_test_fake'}
        if '/billing_portal/' in url:
            return {'url': 'https://billing.stripe.com/p/session/test_fake'}
        raise AssertionError(url)


class CustomerTests(unittest.TestCase):
    def setUp(self):
        self.provider = FakeProvider()
        self.service = Customers(dict(ENV), self.provider)

    def rejected(self, code, action):
        with self.assertRaises(ServiceError) as caught:
            action()
        self.assertEqual(caught.exception.status, code)

    def signed(self, event, timestamp=None):
        raw = json.dumps(event).encode()
        timestamp = str(int(time.time()) if timestamp is None else timestamp)
        signature = hmac.new(ENV['STRIPE_WEBHOOK_SECRET'].encode(), timestamp.encode()+b'.'+raw, hashlib.sha256).hexdigest()
        return raw, 't='+timestamp+',v1='+signature

    def event(self):
        return {'id': 'evt_test', 'livemode': False, 'type': 'checkout.session.completed', 'data': {'object': {'subscription': 'sub_test', 'client_reference_id': UID}}}

    def test_disabled_by_default(self):
        self.rejected(503, lambda: Customers({}, self.provider).send_code({'email': 'test@example.com'}))
        self.assertEqual(self.provider.calls, [])

    def test_live_keys_never_make_a_network_call(self):
        for key in ('sk_live_fake', 'rk_live_fake', 'rk_test_fake'):
            self.service.env['STRIPE_SECRET_KEY'] = key
            self.rejected(503, lambda: self.service.checkout('verified-token'))
        self.assertEqual(self.provider.calls, [])

    def test_live_mode_switch_is_not_supported(self):
        self.service.env['HASHMARGIN_BILLING_MODE'] = 'live'
        self.rejected(503, lambda: self.service.checkout('verified-token'))
        self.assertEqual(self.provider.calls, [])

    def test_signin_verifies_and_hides_refresh_token(self):
        self.service.send_code({'email': 'TEST@example.com'})
        result = self.service.verify_code({'email': 'test@example.com', 'code': '123456'})
        self.assertEqual(result['access_token'], 'verified-token')
        self.assertNotIn('refresh_token', result)

    def test_original_confirmation_link_uses_fixed_provider_endpoint(self):
        link = ENV['SUPABASE_URL'] + '/auth/v1/verify?token=' + 'a'*56 + '&type=signup&redirect_to=https%3A%2F%2Fevil.test'
        result = self.service.verify_code({'email': 'test@example.com', 'code': link})
        self.assertEqual(result['access_token'], 'verified-token')
        call = next(c for c in self.provider.calls if '/auth/v1/verify' in c[1])
        self.assertEqual(call[1], ENV['SUPABASE_URL'] + '/auth/v1/verify')
        self.assertEqual(call[3], {'token_hash': 'a'*56, 'type': 'signup'})
        self.assertFalse(any('evil.test' in c[1] for c in self.provider.calls))

    def test_untrusted_links_and_non_login_types_rejected(self):
        good = ENV['SUPABASE_URL'] + '/auth/v1/verify?token=' + 'a'*56 + '&type=magiclink'
        for link in (good.replace('project.supabase.co', 'evil.test'),
                     good.replace('https:', 'http:'), good + '&type=signup',
                     good.replace('type=magiclink', 'type=recovery'),
                     good.replace('type=magiclink', 'type=email_change'),
                     good + '#fragment', good.replace('/auth/v1/verify', '/evil')):
            self.rejected(400, lambda: self.service.verify_code({'email': 'test@example.com', 'code': link}))
        self.assertEqual(self.provider.calls, [])

    def test_email_mismatch_signs_out_and_never_returns_session(self):
        link = ENV['SUPABASE_URL'] + '/auth/v1/verify?token=' + 'a'*56 + '&type=signup'
        self.rejected(403, lambda: self.service.verify_code({'email': 'other@example.com', 'code': link}))
        self.assertTrue(any('/auth/v1/logout' in c[1] for c in self.provider.calls))

    def test_beta_invitation_restriction_blocks_uninvited_email(self):
        self.service.env['HASHMARGIN_ACCOUNT_TEST_EMAILS'] = 'invited@example.com'
        self.rejected(403, lambda: self.service.send_code({'email': 'test@example.com'}))
        self.rejected(403, lambda: self.service.verify_code({'email': 'test@example.com', 'code': '123456'}))
        self.assertEqual(self.provider.calls, [])
        self.rejected(403, lambda: self.service.identity('verified-token'))
        self.service.env['HASHMARGIN_ACCOUNT_TEST_EMAILS'] = ' TEST@example.com '
        self.assertEqual(self.service.identity('verified-token')['id'], UID)

    def test_invalid_code_and_email(self):
        self.rejected(400, lambda: self.service.send_code({'email': 'bad'}))
        self.rejected(400, lambda: self.service.verify_code({'email': 'test@example.com', 'code': 'text'}))

    def test_forged_bearer_rejected(self):
        self.rejected(401, lambda: self.service.account('forged'))

    def test_unconfirmed_account_rejected(self):
        self.provider.confirmed = False
        self.rejected(403, lambda: self.service.checkout('verified-token'))

    def test_server_controls_price_and_owner(self):
        result = self.service.checkout('verified-token')
        self.assertEqual(result['mode'], 'test')
        data = self.provider.calls[-1][3]
        self.assertEqual(data['client_reference_id'], UID)
        self.assertEqual(data['line_items[0][price]'], 'price_test')
        self.assertEqual(data['subscription_data[metadata][hashmargin_user_id]'], UID)
        self.assertEqual(data['success_url'], ENV['APP_ORIGIN']+'/account?checkout=returned')
        self.assertNotIn('customer_email', data)

    def test_live_price_rejected_before_checkout(self):
        self.provider.live = True
        self.rejected(503, lambda: self.service.checkout('verified-token'))
        self.assertFalse(any('/checkout/sessions' in call[1] for call in self.provider.calls))

    def test_no_subscription_from_return_url(self):
        result = self.service.account('verified-token')
        self.assertFalse(result['test_subscription_active'])
        self.assertFalse(result['live_payments_enabled'])

    def test_customer_reads_use_user_token_not_admin(self):
        self.service.account('verified-token')
        call = next(c for c in self.provider.calls if '/rest/v1/' in c[1])
        self.assertEqual(call[2]['Authorization'], 'Bearer verified-token')
        self.assertIn('user_id=eq.'+UID, call[1])

    def test_status_and_invoice_must_both_be_paid(self):
        self.provider.rows = [{'subscription_id': 'sub_test', 'customer_id': 'cus_test'}]
        self.assertTrue(self.service.account('verified-token')['test_subscription_active'])
        for state in ('canceled', 'past_due', 'unpaid', 'trialing', 'incomplete', 'paused'):
            self.provider.status = state
            self.assertFalse(self.service.account('verified-token')['test_subscription_active'])
        self.provider.status = 'active'; self.provider.invoice = 'open'
        self.assertFalse(self.service.account('verified-token')['test_subscription_active'])

    def test_wrong_owner_and_wrong_price_never_grant_access(self):
        self.provider.rows = [{'subscription_id': 'sub_test', 'customer_id': 'cus_test'}]
        self.provider.owner = OTHER
        self.assertFalse(self.service.account('verified-token')['test_subscription_active'])
        self.rejected(403, lambda: self.service.portal('verified-token'))
        self.provider.owner = UID; self.provider.price_id = 'price_other'
        self.assertFalse(self.service.account('verified-token')['test_subscription_active'])

    def test_existing_subscription_blocks_duplicate_checkout(self):
        self.provider.rows = [{'subscription_id': 'sub_test', 'customer_id': 'cus_test'}]
        self.rejected(409, lambda: self.service.checkout('verified-token'))

    def test_checkout_idempotency(self):
        with patch('customer_service.time.time', return_value=1800000010):
            self.service.checkout('verified-token'); self.service.checkout('verified-token')
        calls = [c for c in self.provider.calls if '/checkout/sessions' in c[1]]
        self.assertEqual(calls[0][2]['Idempotency-Key'], calls[1][2]['Idempotency-Key'])
        self.assertEqual(calls[0][3], calls[1][3])

    def test_portal_uses_bound_customer(self):
        self.provider.rows = [{'subscription_id': 'sub_test', 'customer_id': 'cus_test'}]
        self.service.portal('verified-token')
        self.assertEqual(self.provider.calls[-1][3]['customer'], 'cus_test')

    def test_forged_and_stale_webhooks_never_write(self):
        raw, signature = self.signed(self.event())
        self.rejected(400, lambda: self.service.webhook(raw+b' ', signature))
        self.rejected(400, lambda: self.service.webhook(*self.signed(self.event(), int(time.time())-301)))
        self.rejected(400, lambda: self.service.webhook(raw, 'broken'))
        self.assertEqual(self.provider.calls, [])

    def test_live_event_rejected(self):
        event = self.event(); event['livemode'] = True
        self.rejected(400, lambda: self.service.webhook(*self.signed(event)))
        self.assertEqual(self.provider.calls, [])

    def test_checkout_owner_mismatch_rejected(self):
        event = self.event(); event['data']['object']['client_reference_id'] = OTHER
        self.rejected(400, lambda: self.service.webhook(*self.signed(event)))
        self.assertFalse(any(c[0] == 'POST' and '/rest/v1/' in c[1] for c in self.provider.calls))

    def test_replay_only_upserts_identity_and_rechecks_current_state(self):
        event = self.event()
        for _ in range(2):
            self.assertTrue(self.service.webhook(*self.signed(event))['received'])
        writes = [c for c in self.provider.calls if c[0] == 'POST' and '/rest/v1/' in c[1]]
        self.assertEqual(writes[0][3], writes[1][3])
        self.assertNotIn('status', writes[0][3])
        self.provider.rows = [{'subscription_id': 'sub_test', 'customer_id': 'cus_test'}]
        self.provider.status = 'canceled'
        self.assertFalse(self.service.account('verified-token')['test_subscription_active'])

    def test_bad_redirect_url_rejected(self):
        for url in ('http://checkout.stripe.com', 'https://checkout.stripe.com.evil.test', 'https://user@checkout.stripe.com'):
            self.rejected(502, lambda: self.service.safe_url(url, 'checkout.stripe.com'))


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), staging.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True); cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(2)

    def call(self, path, method='GET', body=None, headers=None):
        conn = HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        conn.request(method, path, body, headers or {})
        response = conn.getresponse(); result = response.status, dict(response.getheaders()), response.read()
        conn.close(); return result

    def test_public_config_never_exposes_keys(self):
        with patch.object(staging, 'CUSTOMERS', Customers(dict(ENV), FakeProvider())):
            status, headers, body = self.call('/api/config')
        self.assertEqual(status, 200)
        for value in ('sk_test_fake', 'server-only-secret', 'public-test-key'):
            self.assertNotIn(value.encode(), body)
        self.assertFalse(json.loads(body)['live_payments_enabled'])
        self.assertEqual(headers['Cache-Control'], 'no-store')

    def test_origin_rejected_before_auth_provider(self):
        provider = FakeProvider()
        with patch.object(staging, 'CUSTOMERS', Customers(dict(ENV), provider)):
            status, _, _ = self.call('/api/checkout', 'POST', '{}', {'Origin': 'https://evil.test', 'Content-Type': 'application/json'})
        self.assertEqual(status, 403); self.assertEqual(provider.calls, [])

    def test_malformed_and_oversize_bodies(self):
        with patch.object(staging, 'CUSTOMERS', Customers(dict(ENV), FakeProvider())):
            headers = {'Origin': ENV['APP_ORIGIN'], 'Content-Type': 'application/json'}
            self.assertEqual(self.call('/api/auth/code', 'POST', '[]', headers)[0], 400)
            self.assertEqual(self.call('/api/auth/code', 'POST', '{', headers)[0], 400)
            self.assertEqual(self.call('/api/auth/code', 'POST', 'x'*65537, headers)[0], 413)

    def test_authorization_required_and_no_private_routes(self):
        with patch.object(staging, 'CUSTOMERS', Customers(dict(ENV), FakeProvider())):
            self.assertEqual(self.call('/api/me')[0], 401)
        for path in ('/api/miners', '/api/tenants', '/.env', '/bridge.py', '/migrations/001_test_subscriptions.sql'):
            self.assertEqual(self.call(path)[0], 404)

    def test_account_page_is_available_without_creating_account(self):
        status, _, body = self.call('/account?checkout=returned')
        self.assertEqual(status, 200); self.assertIn(b'Live payments are disabled', body)


if __name__ == '__main__':
    unittest.main()
