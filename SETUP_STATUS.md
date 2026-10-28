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

## Current configuration — owner-only sandbox

The user saved server credentials directly in Render and explicitly approved enabling sandbox checkout. `HASHMARGIN_BILLING_MODE=test`; live billing remains impossible in this release. The sandbox webhook is enabled. Supabase Free, migration/RLS, owner-only authentication, delivered email sign-in, and all three server credentials have been verified through actual application operations; no secret values were retrieved or printed.

`STRIPE_PRO_PRICE_ID=price_1UVbsM9fowbuxAPkj1YB9mjb`. Wider customer signup and any commercial launch remain gated by the limits below. No paid service or live charge is approved.

## Limits and gates before any live launch

This is an integration preparation, not a commercial-ready service. Braiins polling and email alerts already exist in the private Windows collector. The hosted account now reads isolated snapshots from that collector; this is a private owner pilot, not a multi-customer paid monitoring service. Add durable checkout-attempt coordination before live billing: current idempotency coalesces requests within a 30-minute window, but another window can create an additional open test checkout before the first webhook arrives. Keep test users informed and cancel surplus test subscriptions. Live billing remains blocked in code.

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
- Webhook `we_1UVbtj9fowbuxAPkFgeDfKWM`: app `/api/stripe/webhook`, checkout completion and subscription create/update/delete events, API version `2026-09-30.endive`. Enabled after the user saved its signing secret and explicitly approved sandbox checkout.
- Standalone hosted checkout `cs_test_a1poaFCB3613w9MC1vwbvVQbv15LiNrtlmSIm9jqKBnvGcGEXLFrWY9XVt`: synthetic customer, test decline card rejected, test success card accepted, API status `complete`, payment status `paid`, `livemode=false`. Portal displays the paid $12 sandbox invoice.
- Customer portal cancellation succeeded: the page confirms service ends November 28, 2026, with no renewal. Test subscription `sub_1UVbzA9fowbuxAPkeE1Cy4L9` and synthetic customer `cus_VWfHLyMa3zm8oT`. This standalone processor test is not linked to a real application user and does not prove webhook/entitlement integration.

The application pins the tested Stripe API version, explicitly disables Managed Payments for its Checkout Sessions, uses card payment methods, and requests flexible subscription billing. All 74 scoped Python tests and JavaScript syntax checks pass. No live key, live transaction, or paid hosting was used.


### Application-to-provider sandbox test completed

October 28, 2026: manual credential deployment and approved test-mode deployment `dep-dbh4ujbl550s73c5jgig` are live. `/healthz` returned 200; `/api/config` confirmed accounts enabled, test checkout enabled, and live payments disabled. Render remains Free.

The existing invited owner completed fresh email-link verification (200). The app read its account (200), created its own sandbox Checkout Session (200), and returned a hosted USD 12/month checkout. Synthetic billing identity and Stripe's test card were used; no real card or funds. Session `cs_test_a1OzpUAYfilQezLmkBUN7YFQbAkjQ61clhwmtncIDH7aRnjaGL54Eao9WK` completed, payment status paid, livemode false.

The actual signed Stripe webhook created exactly one subscription ownership record in Supabase for `sub_1UVcka9fowbuxAPk7g7J4vqO`, customer `cus_VWg6imqQSxlA9n`. The authenticated app subsequently reported `test_subscription_active=true`, confirming the supplied Stripe test key, webhook signing secret, and Supabase server key operate together.

Duplicate subscription checkout was rejected with 409. An invalid webhook signature was rejected with 400. The app-created customer portal returned 200 and displayed the paid sandbox invoice. Its cancellation flow confirmed service would end November 28. The disposable test subscription was then canceled immediately via the sandbox API (no proration/final invoice) to verify access removal and avoid leaving an active test subscription. The app then returned 200 with `test_subscription_active=false`, proving canceled access is removed.

These are actual app/provider tests, distinct from the earlier standalone processor test and 74 scoped offline Python tests. Real time passage for expiry, past-due renewal simulation, and explicit webhook transport retry remain separate coverage gaps; commercial readiness is not claimed. Tax configuration must be reviewed before any future approved live launch; no tax service was activated.


## Existing Braiins collector linked to hosted accounts

The existing `private_email_alerts.py` optionally publishes sanitized worker snapshots through `integrations/monitor_publish.py`. It continues polling Braiins and sending the existing email alerts locally. No pool or SMTP credentials are uploaded. Publishing is opt-in; failures do not stop local alerts. No paid Render worker is used.

The hosted `/api/monitor/publish` endpoint requires an HMAC signature from the existing private monitor key, a timestamp within five minutes, and bounded validated telemetry. It fixes ownership to the server-configured owner UUID; payloads cannot select another user. An atomic database function accepts only newer observations. The account reads snapshots with its own verified bearer under RLS, shows observation time/staleness, and safely renders names as text. Only one latest snapshot per user is stored; no historical-service promise is made.

To complete the actual Windows connection (this cloud session cannot operate the Windows scheduled task):

1. In Render Environment add `HASHMARGIN_MONITOR_KEY` using the same private key already used locally (minimum 32 characters). Never use the Braiins token for this value. Owner UUID `HASHMARGIN_MONITOR_USER_ID` is set automatically for the invited owner. Save/deploy. Never paste the key into chat.
2. Update the existing Windows checkout to the deployment branch so it includes `account_monitor.py`, `integrations/monitor_publish.py`, and the changed collector.
3. In the existing monitor's startup environment, add `HASHMARGIN_ACCOUNT_ORIGIN=https://hashmargin-preview.onrender.com` and ensure the existing `HASHMARGIN_MONITOR_KEY` is available to that process. Restart only the existing “HashMargin Pro Monitor” task. Do not launch a duplicate collector. Existing Braiins and SMTP settings stay local.
4. Confirm “Account snapshot synced” appears in the local log, then sign in and refresh the account page. No worker rows or successful Braiins delivery are claimed until an actual collector upload arrives. Earlier Braiins test returned zero workers; empty data is explicitly distinct from offline miners.

Verification: 61 tests under `tests/` plus 23 legacy tests pass (84 total); JavaScript syntax passes. Actual Postgres tests confirmed owner-only reads, denied anonymous reads/authenticated writes, no public function execution, and rejection of older snapshots; test writes rolled back. Security advisor reported no new findings; existing leaked-password warning remains on this passwordless beta (https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection).

Live billing is still blocked in code and only the Stripe sandbox is connected. The user's GO LIVE authorizes launch work; a live-account connection and production billing implementation/verification remain required. No live charge or paid service has been activated.
