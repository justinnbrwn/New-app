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

## Remaining configuration — keep billing disabled

Supabase Free, database migration/RLS, owner-only authentication, and delivered email sign-in are verified below. Stripe sandbox resources are prepared below. The remaining secrets are not exposed by the connected tools. Enter these directly in Render Environment, never in chat or GitHub:

- `STRIPE_SECRET_KEY`: `sk_test_...` from Hashmargin_pro sandbox (account `acct_1UV1cE9fowbuxAPk`).
- `STRIPE_WEBHOOK_SECRET`: signing secret for webhook `we_1UVbtj9fowbuxAPkFgeDfKWM`.
- `SUPABASE_SERVICE_ROLE_KEY`: server-side key for project `uwmqarxufkpacgxayloq`.

The recurring price is already configured as `STRIPE_PRO_PRICE_ID`. After secrets are saved, enable the sandbox webhook, set `HASHMARGIN_BILLING_MODE=test`, deploy, and test the authenticated app checkout, signed webhook delivery/retry, entitlement updates, cancellation, and unpaid states. Until then the app returns 503 for checkout. Never enable live billing.

## Limits and gates before any live launch

This is an integration preparation, not a commercial-ready service. There is no implementation of paid monitoring features. Add durable checkout-attempt coordination before live billing: current idempotency coalesces requests within a 30-minute window, but another window can create an additional open test checkout before the first webhook arrives. Keep test users informed and cancel surplus test subscriptions. Live billing remains blocked in code.

Rate limiting is local to one server process and keyed by the direct peer (which may be Render's proxy); configure trusted proxy-aware, distributed abuse controls and verify client-IP handling before broad public auth. There is no custom durable entitlement cache: Stripe failures fail closed; canceled subscriptions cannot regain access from stale webhook events. Sign-in state is intentionally lost on checkout redirect; sign in again and refresh status after returning.

Finish support-contact verification and an account-data deletion flow before wider signup. Never expose `bridge.py`, tenant prototype routes, or SMTP/miner credentials on the public server.

## Verification

- `python -m unittest discover -s tests -v`: 51 passing tests with fake providers. No email is sent and no Stripe payment is attempted.
- `python -m unittest -v test_asic test_bridge test_fleet test_tenants test_upgrade`: 23 passing legacy tests.
- `node --check customer-account.js`: passed.
- Broad root test discovery also finds three pre-existing release tests for absent Android/compose files. Those checks cannot pass in this website-only checkout and were not represented as passing.
- Actual database, email, and standalone sandbox processor verification are recorded below; app-to-Stripe webhook integration remains blocked on server secrets.


## October 28 connected-service verification

The Free Supabase project is connected in Render using its publishable key (kept out of source). Database checks passed against actual Postgres: two synthetic users could each read only their own rows; anonymous reads and authenticated writes were denied; even privileged ownership reassignment was rejected by the trigger. All synthetic test data was rolled back. The security advisor reported no issues.

Email delivery through the configured Gmail SMTP service was verified in the owner's inbox. The default signup template contains a confirmation link, so the website now also accepts the copied original Supabase confirmation link. It parses only the trusted project's HTTPS verification link, never fetches a supplied URL, ignores redirect targets, accepts only sign-in/signup types, verifies through the fixed Auth API endpoint, and checks that the verified email matches the requested email. Numeric OTPs remain supported. This avoids requiring template edits for beta testing.

Account testing is limited by `HASHMARGIN_ACCOUNT_TEST_EMAILS` to the invited owner address. Wider customer signup remains gated until the remaining launch items are complete. Billing remains disabled in the app. See the later sandbox verification; no live transaction was attempted.

Updated offline verification: 51 tests under `tests/` and 23 legacy API/tenant tests pass. Real-provider signup/sign-in/logout verification is performed separately after deployment; do not interpret fake-provider unit tests as proof of Stripe integration.


### Live authentication verification completed

On October 28, the deployed website completed a real Supabase signup/sign-in using the owner's delivered confirmation email: verification 200; authenticated account read 200 with the correct email; forged bearer 401; non-invited email 403; logout 200; the same bearer after logout 401; replayed one-time link 401. Checkout returns 503 because billing remains disabled. The live account page renders the enabled invitation-limited form.

Render deployment `dep-dbh3d0mvq37c73bn1ae0` became live at source commit `9e948f374c08cc4db2d5a1f930e4d91c3a1f209f`. Both Render and the Supabase organization were confirmed on Free plans. No paid resource or real charge was activated.

The final Supabase advisor also reported that leaked-password protection is disabled. This beta uses passwordless sign-in and stores no account passwords; no paid protection upgrade was enabled. Reference: https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection

### Stripe sandbox verification

Connected only to `acct_1UV1cE9fowbuxAPk` (Hashmargin_pro sandbox), `livemode=false`.

- Product `prod_VWfCzfLRypcEu4`; recurring USD 12/month price `price_1UVbsM9fowbuxAPkj1YB9mjb`.
- Customer portal `bpc_1UVbt79fowbuxAPkeYhZAtQv`: invoice history, payment-method update, cancellation at period end; no plan switching.
- Webhook `we_1UVbtj9fowbuxAPkFgeDfKWM`: app `/api/stripe/webhook`, checkout completion and subscription create/update/delete events, API version `2026-09-30.endive`. Kept disabled until its signing secret is saved.
- Standalone hosted checkout `cs_test_a1poaFCB3613w9MC1vwbvVQbv15LiNrtlmSIm9jqKBnvGcGEXLFrWY9XVt`: synthetic customer, test decline card rejected, test success card accepted, API status `complete`, payment status `paid`, `livemode=false`. Portal displays the paid $12 sandbox invoice.
- Customer portal cancellation succeeded: the page confirms service ends November 28, 2026, with no renewal. Test subscription `sub_1UVbzA9fowbuxAPkeE1Cy4L9` and synthetic customer `cus_VWfHLyMa3zm8oT`. This standalone processor test is not linked to a real application user and does not prove webhook/entitlement integration.

The application pins the tested Stripe API version, explicitly disables Managed Payments for its Checkout Sessions, uses card payment methods, and requests flexible subscription billing. All 74 scoped Python tests and JavaScript syntax checks pass. No live key, live transaction, or paid hosting was used.
