from twilio.rest import Client
from .config import Config

client = Client(Config.twilio_sid, Config.twilio_token)

def send_sms(body: str):
    for to in filter(None, Config.recipients):
        if Config.dry_run:
            print(f"[DRY_RUN] → {to}: {body}")
        else:
            client.messages.create(to=to, from_=Config.twilio_from, body=body)
