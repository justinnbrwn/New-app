"""Passwordless managed accounts and TEST-ONLY subscriptions. No local customer DB.

Network operations are explicit and injectable for offline security tests.
There is deliberately no live-billing switch in this release.
"""
import hashlib
import hmac
import json
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, parse_qs
from urllib.request import Request, build_opener, HTTPRedirectHandler
from uuid import UUID


class ServiceError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)


class NoRedirect(HTTPRedirectHandler):
    # Never forward bearer/API credentials to a redirect destination.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_json(method, url, headers, data=None, form=False):
    body = None if data is None else (urlencode(data).encode() if form else json.dumps(data).encode())
    headers = dict(headers)
    if body is not None:
        headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
    try:
        with build_opener(NoRedirect).open(Request(url, body, headers, method=method), timeout=12) as response:
            raw = response.read(1_048_577)
            if len(raw) > 1_048_576:
                raise ServiceError(502, 'Provider response too large')
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        # Provider errors may contain emails, tokens or financial data. Do not echo them.
        if exc.code in (401, 403):
            raise ServiceError(401, 'Authentication rejected') from None
        if exc.code == 429:
            raise ServiceError(429, 'Please wait before trying again') from None
        raise ServiceError(502, 'Provider request failed') from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise ServiceError(503, 'Provider temporarily unavailable') from None


def https_origin(value):
    p = urlsplit(value)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.query or p.fragment or p.path not in ('', '/') or p.port not in (None, 443):
        raise ValueError('An HTTPS origin is required')
    return value.rstrip('/')


def user_id(value):
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise ServiceError(401, 'Invalid account identity') from None


class Customers:
    def __init__(self, env=None, transport=request_json):
        self.env = os.environ if env is None else env
        self.transport = transport

    def accounts_ready(self):
        return self.env.get('HASHMARGIN_ACCOUNTS_ENABLED') == 'true' and all(self.env.get(k) for k in ('SUPABASE_URL', 'SUPABASE_ANON_KEY', 'APP_ORIGIN'))

    def require_accounts(self):
        if not self.accounts_ready():
            raise ServiceError(503, 'Customer accounts are not configured yet')
        try:
            https_origin(self.env['SUPABASE_URL'])
            https_origin(self.env['APP_ORIGIN'])
        except ValueError:
            raise ServiceError(503, 'Account configuration unavailable') from None

    def billing_ready(self):
        return (self.accounts_ready() and self.env.get('HASHMARGIN_BILLING_MODE') == 'test'
                and self.env.get('STRIPE_SECRET_KEY', '').startswith('sk_test_')
                and all(self.env.get(k) for k in ('STRIPE_PRO_PRICE_ID', 'STRIPE_WEBHOOK_SECRET', 'SUPABASE_SERVICE_ROLE_KEY')))

    def require_billing(self):
        self.require_accounts()
        if not self.billing_ready():
            raise ServiceError(503, 'Test checkout is not configured. Live payments are disabled')

    def auth(self, method, path, data=None, token=None):
        self.require_accounts()
        headers = {'apikey': self.env['SUPABASE_ANON_KEY']}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        return self.transport(method, self.env['SUPABASE_URL'].rstrip('/') + '/auth/v1/' + path, headers, data)

    def require_invited_email(self, email):
        # Optional beta restriction while billing and wider launch remain unfinished.
        allowed = {x.strip().lower() for x in self.env.get('HASHMARGIN_ACCOUNT_TEST_EMAILS', '').split(',') if x.strip()}
        if allowed and email.lower() not in allowed:
            raise ServiceError(403, 'Account testing is limited to invited email addresses')

    def send_code(self, data):
        email = data.get('email', '')
        if not isinstance(email, str) or len(email) > 254 or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
            raise ServiceError(400, 'Enter a valid email address')
        self.require_invited_email(email)
        self.auth('POST', 'otp', {'email': email.strip().lower(), 'create_user': True})
        return {'message': 'If available, a sign-in email has been sent. Paste its code or copy its confirmation link into the field below.'}

    def verify_code(self, data):
        email, code = data.get('email', ''), data.get('code', '')
        if not isinstance(email, str) or len(email) > 254 or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email) or not isinstance(code, str) or len(code) > 4096:
            raise ServiceError(400, 'Enter your email and sign-in code or copied confirmation link')
        email, code = email.lower(), code.strip()
        self.require_invited_email(email)
        if re.fullmatch(r'\d{6,10}', code):
            payload = {'email': email, 'token': code, 'type': 'email'}
        else:
            # Parse credentials only. Never fetch a pasted URL or follow its redirect.
            # A fixed trusted Auth endpoint performs all verification.
            try:
                link, project = urlsplit(code), urlsplit(self.env.get('SUPABASE_URL', ''))
                query = parse_qs(link.query)
                hashes, types = query.get('token', []), query.get('type', [])
                if (link.scheme != 'https' or link.hostname != project.hostname or not project.hostname
                        or link.username or link.password or link.port not in (None, 443)
                        or link.path != '/auth/v1/verify' or link.fragment
                        or len(hashes) != 1 or len(types) != 1
                        or not re.fullmatch(r'[a-fA-F0-9]{32,128}', hashes[0])
                        or types[0] not in ('signup', 'magiclink', 'email')):
                    raise ValueError()
                payload = {'token_hash': hashes[0], 'type': types[0]}
            except ValueError:
                raise ServiceError(400, 'Use the code or original confirmation link from your HashMargin email') from None
        session = self.auth('POST', 'verify', payload)
        token = session.get('access_token')
        if not token:
            raise ServiceError(401, 'Invalid or expired code or link')
        # Never return refresh tokens. Browser keeps this short-lived bearer only in memory.
        who = self.identity(token)
        if who['email'].lower() != email:
            # Do not sign the visitor into an account different from the one requested.
            self.auth('POST', 'logout', {}, token)
            raise ServiceError(403, 'The confirmation link belongs to another email address')
        return {'access_token': token, 'expires_in': session.get('expires_in', 3600)}

    def identity(self, token):
        if not isinstance(token, str) or not token or len(token) > 8192 or '\n' in token or '\r' in token:
            raise ServiceError(401, 'Sign in to continue')
        obj = self.auth('GET', 'user', token=token)
        uid = user_id(obj.get('id'))
        if not obj.get('email_confirmed_at') or obj.get('is_anonymous'):
            raise ServiceError(403, 'Verify your email before continuing')
        self.require_invited_email(obj.get('email', ''))
        return {'id': uid, 'email': obj.get('email', '')}

    def stripe(self, method, path, data=None, idempotency=None):
        self.require_billing()
        headers = {'Authorization': 'Bearer ' + self.env['STRIPE_SECRET_KEY']}
        if idempotency:
            headers['Idempotency-Key'] = idempotency
        return self.transport(method, 'https://api.stripe.com/v1/' + path, headers, data, form=True)

    def rows(self, uid, token):
        self.require_billing()
        # User token, not service-role: database RLS independently enforces ownership.
        return self.transport('GET', self.env['SUPABASE_URL'].rstrip('/') + '/rest/v1/test_subscriptions?' + urlencode({'user_id': 'eq.' + uid, 'select': 'subscription_id,customer_id'}),
                              {'apikey': self.env['SUPABASE_ANON_KEY'], 'Authorization': 'Bearer ' + token})

    def price(self):
        pid = self.env.get('STRIPE_PRO_PRICE_ID', '')
        if not re.fullmatch(r'price_[A-Za-z0-9]+', pid):
            raise ServiceError(503, 'Test price unavailable')
        obj = self.stripe('GET', 'prices/' + pid)
        if (obj.get('livemode') is not False or obj.get('active') is not True or obj.get('unit_amount') != 1200 or obj.get('currency') != 'usd'
                or obj.get('recurring', {}).get('interval') != 'month' or obj['recurring'].get('interval_count') != 1):
            raise ServiceError(503, 'Expected an active test price of USD 12 per month')
        return pid

    def subscription(self, sid):
        if not re.fullmatch(r'sub_[A-Za-z0-9]+', sid):
            raise ServiceError(400, 'Invalid subscription')
        obj = self.stripe('GET', 'subscriptions/' + sid + '?expand%5B%5D=latest_invoice')
        if obj.get('livemode') is not False:
            raise ServiceError(400, 'Live subscription rejected')
        return obj

    def entitled(self, obj, uid):
        return (obj.get('metadata', {}).get('hashmargin_user_id') == uid
                and obj.get('status') == 'active'
                and isinstance(obj.get('latest_invoice'), dict)
                and obj['latest_invoice'].get('status') == 'paid'
                and any(item.get('price', {}).get('id') == self.env['STRIPE_PRO_PRICE_ID'] for item in obj.get('items', {}).get('data', [])))

    def account(self, token):
        who = self.identity(token)
        active = False
        if self.billing_ready():
            for row in self.rows(who['id'], token):
                obj = self.subscription(row['subscription_id'])
                active |= self.entitled(obj, who['id'])
        return {'email': who['email'], 'test_subscription_active': active, 'live_payments_enabled': False, 'miner_connections_enabled': False}

    def checkout(self, token):
        self.require_billing()
        who = self.identity(token)
        pid = self.price()
        for row in self.rows(who['id'], token):
            obj = self.subscription(row['subscription_id'])
            if obj.get('metadata', {}).get('hashmargin_user_id') == who['id'] and obj.get('status') in ('active', 'trialing', 'past_due', 'unpaid', 'incomplete', 'paused'):
                raise ServiceError(409, 'A test subscription already exists. Manage it before starting another')
        origin = https_origin(self.env['APP_ORIGIN'])
        # A single reusable checkout per account per 30-minute window. Stripe expires it
        # after 30–60 minutes; no caller-controlled price, customer, owner or redirect.
        bucket = int(time.time() // 1800)
        result = self.stripe('POST', 'checkout/sessions', {
            'mode': 'subscription', 'line_items[0][price]': pid, 'line_items[0][quantity]': 1,
            'client_reference_id': who['id'], 'metadata[hashmargin_user_id]': who['id'],
            'subscription_data[metadata][hashmargin_user_id]': who['id'],
            'success_url': origin + '/account?checkout=returned', 'cancel_url': origin + '/account?checkout=canceled',
            'expires_at': (bucket + 2) * 1800,
        }, 'hashmargin-test-' + who['id'] + '-' + str(bucket))
        if result.get('livemode') is not False:
            raise ServiceError(502, 'Live checkout rejected')
        return {'url': self.safe_url(result.get('url'), 'checkout.stripe.com'), 'mode': 'test'}

    @staticmethod
    def safe_url(value, hostname):
        p = urlsplit(value or '')
        if p.scheme != 'https' or p.hostname != hostname or p.username or p.password or p.port not in (None, 443):
            raise ServiceError(502, 'Invalid billing destination')
        return value

    def portal(self, token):
        self.require_billing()
        who = self.identity(token)
        rows = self.rows(who['id'], token)
        if not rows:
            raise ServiceError(409, 'No test subscription to manage')
        obj = self.subscription(rows[0]['subscription_id'])
        if obj.get('metadata', {}).get('hashmargin_user_id') != who['id'] or obj.get('customer') != rows[0]['customer_id']:
            raise ServiceError(403, 'Subscription ownership mismatch')
        result = self.stripe('POST', 'billing_portal/sessions', {'customer': obj['customer'], 'return_url': https_origin(self.env['APP_ORIGIN']) + '/account'})
        return {'url': self.safe_url(result.get('url'), 'billing.stripe.com'), 'mode': 'test'}

    def webhook(self, raw, signature):
        self.require_billing()
        try:
            parts = [part.split('=', 1) for part in signature.split(',')]
            timestamp = next(v for k, v in parts if k == 't')
            if abs(time.time() - int(timestamp)) > 300:
                raise ValueError()
            expected = hmac.new(self.env['STRIPE_WEBHOOK_SECRET'].encode(), timestamp.encode() + b'.' + raw, hashlib.sha256).hexdigest()
            if not any(k == 'v1' and hmac.compare_digest(v, expected) for k, v in parts):
                raise ValueError()
            event = json.loads(raw)
            if event.get('livemode') is not False:
                raise ValueError()
        except (ValueError, StopIteration, TypeError):
            raise ServiceError(400, 'Invalid test webhook signature or payload') from None
        kind = event.get('type', '')
        if kind in ('checkout.session.completed', 'customer.subscription.created', 'customer.subscription.updated', 'customer.subscription.deleted'):
            source = event.get('data', {}).get('object', {})
            sid = source.get('subscription') if kind == 'checkout.session.completed' else source.get('id')
            if not isinstance(sid, str):
                raise ServiceError(400, 'Subscription missing')
            # Retrieve current state, not the event snapshot: replay/out-of-order events
            # cannot restore an old entitlement. Every protected read rechecks Stripe.
            obj = self.subscription(sid)
            uid = user_id(obj.get('metadata', {}).get('hashmargin_user_id'))
            if kind == 'checkout.session.completed' and source.get('client_reference_id') != uid:
                raise ServiceError(400, 'Checkout owner mismatch')
            if not any(i.get('price', {}).get('id') == self.env['STRIPE_PRO_PRICE_ID'] for i in obj.get('items', {}).get('data', [])):
                raise ServiceError(400, 'Subscription price mismatch')
            cid = obj.get('customer', '')
            if not isinstance(cid, str) or not re.fullmatch(r'cus_[A-Za-z0-9]+', cid):
                raise ServiceError(400, 'Customer missing')
            secret = self.env['SUPABASE_SERVICE_ROLE_KEY']
            self.transport('POST', self.env['SUPABASE_URL'].rstrip('/') + '/rest/v1/test_subscriptions?on_conflict=subscription_id',
                           {'apikey': secret, 'Authorization': 'Bearer ' + secret, 'Prefer': 'resolution=merge-duplicates'},
                           {'subscription_id': sid, 'user_id': uid, 'customer_id': cid})
        return {'received': True}
