from twilio.rest import Client
from .config import Config

_cfg = Config()  # ← create one instance that reads env

client = Client(_cfg.twilio_sid, _cfg.twilio_token)

def send_sms(body: str):
    # Clean recipients (strip + drop empties)
    recipients = [s.strip() for s in (_cfg.recipients or []) if s.strip()]
    if not recipients:
        print("[SMS] No recipients configured (RECIPIENT_NUMBERS empty).")
        return

    for to in recipients:
        if _cfg.dry_run:
            print(f"[DRY_RUN] → {to}: {body}")
        else:
            client.messages.create(to=to, from_=_cfg.twilio_from, body=body)
