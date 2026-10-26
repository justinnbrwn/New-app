"""Pure calculations for private monitoring. No secrets, network, or mining control."""
from decimal import Decimal, InvalidOperation

BAD_STATES = {"off", "dis", "low"}

def detect_changes(previous, current):
    """Alert only on newly unhealthy workers; avoid repeat notifications."""
    before = {w["name"]: w.get("state") for w in previous}
    events = []
    for worker in current:
        name, state = worker["name"], worker.get("state", "unknown")
        if state in BAD_STATES and before.get(name) not in BAD_STATES:
            events.append({"worker": name, "state": state, "kind": "worker_anomaly"})
    return events

def profitability(kw, usd_per_kwh, gross_usd_per_day, uptime_fraction=1):
    """Estimate electricity and net revenue; inputs must be user supplied."""
    try:
        power = Decimal(str(kw))
        rate = Decimal(str(usd_per_kwh))
        gross = Decimal(str(gross_usd_per_day))
        uptime = Decimal(str(uptime_fraction))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Invalid numeric input") from exc
    if not all(v.is_finite() for v in (power, rate, gross, uptime)):
        raise ValueError("Values must be finite")
    if min(power, rate, gross, uptime) < 0 or uptime > 1:
        raise ValueError("Values must be nonnegative and uptime at most one")
    energy = power * Decimal("24") * uptime
    cost = energy * rate
    revenue = gross * uptime
    return {"kwh_per_day": float(energy), "electricity_usd_per_day": float(cost),
            "gross_usd_per_day": float(revenue), "net_usd_per_day": float(revenue - cost)}
