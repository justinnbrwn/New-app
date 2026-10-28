# HashMargin Pro — account, billing and miner monitoring integration

Status: IN DEVELOPMENT. These features are not active on the public preview.

## Recommended production services
- Customer authentication: managed Supabase Auth, email verification and password reset; require RLS for all customer-owned data.
- Subscription billing: Stripe Checkout and Customer Portal. Create checkout sessions on the server, never in the browser. Verify Stripe webhook signatures against the raw request body. Grant entitlements only after verified subscription events.
- Read-only mining connections: start with Braiins Pool API. Collect customer-provided read-only API tokens via authenticated TLS endpoints; encrypt tokens at rest with a separate server-side encryption key, never expose tokens to browsers, logs, URLs or GitHub.
- Database: managed Postgres with per-user ownership enforced on the server and RLS. Store billing customer/subscription IDs and miner connection metadata; do not store passwords directly.
- Scheduled monitoring: isolated background worker for pool polling and alert evaluation. Apply per-user rate limits, request timeouts and provider API quotas.

## Public launch gates
1. Configure Supabase project and server/client environment variables; validate signup, login, logout, email verification, password reset, and cross-user isolation.
2. Configure Stripe account, products and price IDs; test checkout, canceled checkout, webhook replay/idempotency, failed payments, cancellation, and customer portal.
3. Add server-side authorization and secret encryption before accepting pool tokens; validate read-only scopes and connection revocation.
4. Audit authorization, webhook signature verification, token encryption, privacy notice, support contact and data deletion.
5. Deploy a staging service separately from the current calculator-only preview and run integration tests before changing the public service.

## Environment variable names (never commit values)
SUPABASE_URL
SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY
STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET
STRIPE_PRO_PRICE_ID
STRIPE_BUSINESS_PRICE_ID
MINER_TOKEN_ENCRYPTION_KEY

## Current architecture
The public `staging.py` server intentionally exposes only the homepage, calculator, policy pages and health check. It has no account, billing, miner-connection or write API. Do not point public traffic at `bridge.py` or any mining control interface.

## Billing transparency
The $19.99 Pro and $49.99 Business amounts are proposed prices, not active subscriptions. No checkout links should be enabled until the corresponding Stripe products, account entitlements, cancellation flow, and terms are tested.
