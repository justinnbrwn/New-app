# HashMargin Pro: free preview and prepared account / test billing integration

## Cost and payment boundaries

The existing `hashmargin-preview` service remains on Render's `free` plan. No worker, disk, cron, paid database, paid SMTP plan or paid service is created by this change. The optional account provider must use a Free Supabase project. No application customer records are saved to Render's ephemeral filesystem.

Accounts default off. Billing defaults off. `HASHMARGIN_BILLING_MODE=test` plus an `sk_test_` secret is required for every Stripe API call; there is no live-billing switch. Live keys, live prices, live subscriptions and live webhook events are rejected. The existing live payment link is not used anywhere in the served website. Its external Stripe activation state has not been changed.

## Implemented

- Managed passwordless email-code signup/sign-in, verification, short-lived bearer session and logout. No password database, browser localStorage or refresh-token storage.
- Same-origin JSON write APIs; no CORS permission or cookie authentication. Responses are no-store. CSP, HSTS, referrer and content-type protections; request size/time limits; bounded process-local rate limits.
- Authenticated server-created USD 12/month test subscriptions with fixed server price, account ownership, return URLs, Stripe idempotency keys, and a customer portal derived from the account's subscription record.
- Test-only webhook raw-body signature and 5-minute timestamp verification. Subscription identity is upserted by unique Stripe subscription ID; ownership is immutable at the database layer. Entitlements are never accepted from a success URL, client metadata, or an old event snapshot. Current Stripe status, paid invoice, price and account ownership are checked on each account-status request.
- SQL migration with database row-level security; authenticated customers can only read their own test subscriptions and cannot write billing records. The server key is only used by verified webhooks. No miner API exposed.

## Configuration still required (do not enable before completing)

1. Connect Supabase and choose/create a **Free** project. Apply `migrations/001_test_subscriptions.sql` once. Test two independent users: neither can read the other's rows; neither can insert/update/delete billing rows; anonymous reads fail. The migration has not been executed or verified against a real database yet.
2. Enable email OTP, set the email template to include `{{ .Token }}`, and verify code expiration, provider rate limits and email delivery. Supabase default email delivery is limited; verify permitted test recipients and sender configuration. No paid email service is authorized.
3. Set `APP_ORIGIN`, `SUPABASE_URL`, and `SUPABASE_ANON_KEY` through Render's secret/configuration workflow. Set the account flag true only after auth tests pass. Never paste secrets into GitHub or chat.
4. Access the existing Stripe account's **test/sandbox** environment. The live product and Payment Link are not test credentials. Create/select an active recurring test price of USD 12/month. Set the test key, test webhook signing secret, test price ID and Supabase service-role secret in Render. Set billing mode `test` only after schema verification.
5. Configure a TEST webhook at `/api/stripe/webhook` for `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`. Enable the TEST customer portal including cancellation. Do not enable live checkout or subscribe through the existing live Payment Link.
6. Real provider end-to-end tests: verified and expired email codes; logout/token expiry; two-user RLS isolation; test-card success/decline; canceled checkout; webhook delivery/retry; past-due/unpaid/canceled subscriptions; portal cancellation. These were not run without provider credentials.

## Limits and gates before any live launch

This is an integration preparation, not a commercial-ready service. There is no implementation of paid monitoring features. Add durable checkout-attempt coordination before live billing: current idempotency coalesces requests within a 30-minute window, but another window can create an additional open test checkout before the first webhook arrives. Keep test users informed and cancel surplus test subscriptions. Live billing remains blocked in code.

Rate limiting is local to one server process and keyed by the direct peer (which may be Render's proxy); configure trusted proxy-aware, distributed abuse controls and verify client-IP handling before broad public auth. There is no custom durable entitlement cache: Stripe failures fail closed; canceled subscriptions cannot regain access from stale webhook events. Sign-in state is intentionally lost on checkout redirect; sign in again and refresh status after returning.

Finish support-contact verification and an account-data deletion flow before wider signup. Never expose `bridge.py`, tenant prototype routes, or SMTP/miner credentials on the public server.

## Verification

- `python -m unittest discover -s tests -v`: 47 passing tests, including 26 new account/API/billing tests with fake providers. No email is sent and no Stripe payment is attempted.
- `python -m unittest -v test_asic test_bridge test_fleet test_tenants test_upgrade`: 23 passing legacy tests.
- `node --check customer-account.js`: passed.
- Broad root test discovery also finds three pre-existing release tests for absent Android/compose files. Those checks cannot pass in this website-only checkout and were not represented as passing.
- Database RLS enforcement and real Stripe/email flows remain pending connected-service verification.


## October 28 connected-service verification

The Free Supabase project is connected in Render using its publishable key (kept out of source). Database checks passed against actual Postgres: two synthetic users could each read only their own rows; anonymous reads and authenticated writes were denied; even privileged ownership reassignment was rejected by the trigger. All synthetic test data was rolled back. The security advisor reported no issues.

Email delivery through the configured Gmail SMTP service was verified in the owner's inbox. The default signup template contains a confirmation link, so the website now also accepts the copied original Supabase confirmation link. It parses only the trusted project's HTTPS verification link, never fetches a supplied URL, ignores redirect targets, accepts only sign-in/signup types, verifies through the fixed Auth API endpoint, and checks that the verified email matches the requested email. Numeric OTPs remain supported. This avoids requiring template edits for beta testing.

Account testing is limited by `HASHMARGIN_ACCOUNT_TEST_EMAILS` to the invited owner address. Wider customer signup remains gated until the remaining launch items are complete. Billing remains disabled, and no Stripe sandbox or live transaction has been attempted. Do not enable live charges.

Updated offline verification: 51 tests under `tests/` and 23 legacy API/tenant tests pass. Real-provider signup/sign-in/logout verification is performed separately after deployment; do not interpret fake-provider unit tests as proof of Stripe integration.
