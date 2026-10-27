# HashMargin Pro — commercial readiness and trust requirements

Status: **free calculator beta in preparation**. No claim of paid-service readiness.

## Required before publicly representing this as a commercial business
- [x] Identify the proposed operator: Justinn Brown, sole proprietor (user-confirmed).
- [ ] Confirm applicable jurisdiction, any assumed-name filing, and a real customer support contact.
- [ ] Review applicable business registration, tax, consumer-protection, and privacy obligations with qualified professionals where needed.
- [ ] Publish accurate privacy notice and terms that match hosting logs, any analytics, and actual data flows. Current pages are provisional.
- [ ] Confirm ownership/licensing for all branding, graphics, code, and third-party data sources.
- [ ] Make clear all calculator inputs are manually entered and all outputs are estimates.
- [ ] Add an accurate support contact and incident-response procedure.
- [ ] Run full tests, test on real browsers, and verify live HTTPS and health checks after deploy.
- [ ] Document service uptime limitations of free hosting and do not promise always-on monitoring.
- [ ] Before collecting money: verify alerts end-to-end, isolate customer data, implement authentication and authorization, handle billing cancellation/refunds, and complete security and legal reviews.
- [ ] Avoid guarantees of mining income, ROI, worker uptime, or savings.

## Safe release sequence
1. Free public calculator beta; no credentials collected; no paid claims.
2. Verified read-only monitoring pilot with explicit opt-in, secure secret storage, and real alert delivery.
3. Paid SaaS only after independent production checks and customer support are operational.

## Verification evidence
For each release, record date, commit SHA, test output, deployment URL, HTTP status for `/` and `/healthz`, and browser/device test results. An external DNS failure is inconclusive, not evidence of a service outage.
