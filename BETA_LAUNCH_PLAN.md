# HashMargin Pro — website-first beta release plan

## Release decision
Launch a **free, clearly labeled calculator beta** before offering paid monitoring. Keep Render on its free plan. Do not enable payments, accounts, miner controls, or publish API keys.

## Current confirmed scope (source review)
- Public HTML dashboard with user-entered mining profitability assumptions
- Gross revenue, electricity, net margin, break-even rate, 30-day projection, downtime loss estimator
- No live BTC price feed, miner connection, user accounts, payments, or working customer alerts in the public preview
- `staging.py` serves `/`, `/dashboard`, and `/healthz`
- Render blueprint uses `hashmargin-preview`, free instance, `python staging.py`

## Launch gates (all must be confirmed before announcing public beta)
- [ ] Render deploy green on intended branch; `/healthz` returns HTTP 200 and `status: ok`
- [ ] Homepage returns HTTP 200 and dashboard loads on mobile and desktop
- [ ] Calculator outputs match independent examples, including zero power, zero hashrate, and invalid input
- [ ] Copy clearly labels modeled estimates and manual inputs; no implication of live miner monitoring
- [ ] No secrets, customer data, private endpoints, or control interfaces exposed
- [ ] Basic privacy statement, terms/disclaimer, and support contact published
- [ ] Test uptime and behavior after Render free-instance cold start
- [ ] Check accessibility, responsive layout, and browser console errors
- [ ] Obtain feedback from real ASIC operators before promising paid features

## Later paid product — NOT YET IMPLEMENTED
1. Reliable read-only pool data ingestion and multi-tenant account isolation
2. Worker-offline monitoring and verified notification delivery
3. Electricity-adjusted profitability and payout reconciliation
4. Security review, privacy/terms, billing lifecycle, cancellations and refunds
5. Pricing validation: test Pro $19.99/mo and Business $49.99/mo with prospective users; these are hypotheses, not revenue forecasts
6. Android companion only after the web service proves useful and reliable

## Operational safeguards
- Never commit Braiins tokens, Gmail app passwords, or payment secrets.
- Do not start `bridge.py` on the public preview or enable miner-control endpoints.
- Do not change the Render plan or enable payments without separate authorization.
- Treat inaccessible external checks as **unverified**, not proof of a deployment outage.
