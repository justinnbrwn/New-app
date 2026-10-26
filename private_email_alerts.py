"""Local-only Braiins worker email alerts.

No HTTP listener, no public endpoint, and no miner control.
Credentials must be provided as environment variables on the private machine.
"""
import os
import smtplib
import ssl
import time
from email.message import EmailMessage
from integrations.braiins_pool import fetch_workers
from integrations.monitor_analysis import detect_changes

def send_email(events, smtp_factory=smtplib.SMTP_SSL):
    if not events:
        return False
    host = os.environ["HASHMARGIN_SMTP_HOST"]
    port = int(os.environ.get("HASHMARGIN_SMTP_PORT", "465"))
    sender = os.environ["HASHMARGIN_EMAIL_FROM"]
    recipient = os.environ["HASHMARGIN_EMAIL_TO"]
    username = os.environ["HASHMARGIN_SMTP_USER"]
    password = os.environ["HASHMARGIN_SMTP_PASSWORD"]
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = "HashMargin Pro: mining worker alert"
    offline = sum(e["state"] in ("off", "dis") for e in events)
    low = sum(e["state"] == "low" for e in events)
    msg.set_content(
        f"New mining worker anomalies detected. Offline: {offline}. "
        f"Low hashrate: {low}. Check your private Braiins dashboard. "
        "No account details or worker names are included."
    )
    with smtp_factory(host, port, context=ssl.create_default_context(), timeout=15) as smtp:
        smtp.login(username, password)
        smtp.send_message(msg)
    return True

def check_once(previous, fetch=fetch_workers, send=send_email):
    current = fetch()
    if previous is not None:
        events = detect_changes(previous, current)
        if events:
            send(events)
    return current

def main():
    required = ("BRAIINS_POOL_TOKEN", "HASHMARGIN_SMTP_HOST",
                "HASHMARGIN_EMAIL_FROM", "HASHMARGIN_EMAIL_TO",
                "HASHMARGIN_SMTP_USER", "HASHMARGIN_SMTP_PASSWORD")
    if any(not os.environ.get(name) for name in required):
        raise SystemExit("Missing required private monitor configuration")
    previous = None
    while True:
        try:
            previous = check_once(previous)
            print("Worker check completed", flush=True)
        except Exception:
            print("Worker check or notification failed", flush=True)
        time.sleep(60)

if __name__ == "__main__":
    main()
