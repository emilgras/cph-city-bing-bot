from twilio.rest import Client
from .config import Config
import time

# One global instance of Config
_cfg = Config()

client = Client(_cfg.twilio_sid, _cfg.twilio_token)

def send_sms(body: str):
    recipients = [s.strip() for s in (_cfg.recipients or []) if s.strip()]
    if not recipients:
        print("[SMS] No recipients configured")
        return

    for to in recipients:
        if _cfg.dry_run:
            print(f"[DRY_RUN] → {to}: {body}")
            continue

        # Send the SMS
        msg = client.messages.create(to=to, from_=_cfg.twilio_from, body=body)
        print(f"[SMS] sent to {to} sid={msg.sid} initial_status={msg.status}")

        # Wait a few seconds and fetch the status from Twilio
        time.sleep(3)
        m = client.messages(msg.sid).fetch()
        print(
            f"[SMS] delivery status={m.status} "
            f"error_code={m.error_code} error_message={m.error_message}"
        )
