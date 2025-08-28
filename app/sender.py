from twilio.rest import Client
from .config import Config
import time

client = Client(Config.twilio_sid, Config.twilio_token)

def send_sms(body: str):
    recipients = [s.strip() for s in (Config.recipients or []) if s.strip()]
    if not recipients:
        print("[SMS] No recipients configured")
        return

    for to in recipients:
        if Config.dry_run:
            print(f"[DRY_RUN] → {to}: {body}")
            continue

        # Send the SMS
        msg = client.messages.create(to=to, from_=Config.twilio_from, body=body)
        print(f"[SMS] sent to {to} sid={msg.sid} initial_status={msg.status}")

        # Wait a couple of seconds and fetch the final status
        time.sleep(3)
        m = client.messages(msg.sid).fetch()
        print(
            f"[SMS] delivery status={m.status} "
            f"error_code={m.error_code} error_message={m.error_message}"
        )
