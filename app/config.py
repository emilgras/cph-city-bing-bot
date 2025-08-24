import os
from dataclasses import dataclass, field
from typing import ClassVar, List
from zoneinfo import ZoneInfo

@dataclass
class Config:
    # Ikke et dataclass-felt (skal ikke i __init__)
    tz: ClassVar[ZoneInfo] = ZoneInfo(os.getenv("TZ", "Europe/Copenhagen"))

    # Forbindelser / nøgler
    redis_url: str = os.environ["REDIS_URL"]
    owm_key: str = os.environ["OPENWEATHER_API_KEY"]

    bing_key: str = os.environ["BING_SEARCH_KEY"]

    azure_endpoint: str = os.environ["AZURE_OPENAI_ENDPOINT"]
    azure_key: str = os.environ["AZURE_OPENAI_KEY"]
    azure_deployment: str = os.environ["AZURE_OPENAI_DEPLOYMENT"]

    twilio_sid: str = os.environ["TWILIO_ACCOUNT_SID"]
    twilio_token: str = os.environ["TWILIO_AUTH_TOKEN"]
    twilio_from: str = os.environ["TWILIO_FROM_NUMBER"]

    # Brug default_factory til muterbare defaults
    recipients: List[str] = field(
        default_factory=lambda: os.getenv("RECIPIENT_NUMBERS", "").split(",")
    )

    # Planlægningsparametre
    send_dow: int = int(os.getenv("SEND_DAY_OF_WEEK", "6"))
    send_hour: int = int(os.getenv("SEND_HOUR_LOCAL", "10"))
    interval_days: int = int(os.getenv("SEND_INTERVAL_DAYS", "7"))
    welcome_delay_min: int = int(os.getenv("WELCOME_DELAY_MINUTES", "5"))
    dry_run: bool = os.getenv("DRY_RUN", "false").lower() == "true"
