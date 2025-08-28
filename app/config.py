import os
from dataclasses import dataclass, field
from typing import ClassVar, List
from zoneinfo import ZoneInfo

@dataclass
class Config:
    tz: ClassVar[ZoneInfo] = ZoneInfo(os.getenv("TZ", "Europe/Copenhagen"))

    # Persistence
    redis_url: str = os.environ["REDIS_URL"]

    # Azure AD for token (client credentials)
    azure_tenant_id: str = os.environ["AZURE_TENANT_ID"]
    azure_client_id: str = os.environ["AZURE_CLIENT_ID"]
    azure_client_secret: str = os.environ["AZURE_CLIENT_SECRET"]

    # Foundry Agents (threads/runs)
    agent_project_endpoint: str = os.environ["AGENT_PROJECT_ENDPOINT"]  # .../api/projects/<name>
    agent_api_version: str = os.getenv("AGENT_API_VERSION", "2025-05-01")
    agent_id: str = os.environ["AGENT_ID"]

    # Twilio
    twilio_sid: str = os.environ["TWILIO_ACCOUNT_SID"]
    twilio_token: str = os.environ["TWILIO_AUTH_TOKEN"]
    twilio_from: str = os.environ["TWILIO_FROM_NUMBER"]

    recipients: List[str] = field(default_factory=lambda: os.getenv("RECIPIENT_NUMBERS", "").split(","))

    # Scheduling
    send_dow: int = int(os.getenv("SEND_DAY_OF_WEEK", "6"))
    send_hour: int = int(os.getenv("SEND_HOUR_LOCAL", "10"))
    interval_days: int = int(os.getenv("SEND_INTERVAL_DAYS", "7"))
    welcome_delay_min: int = int(os.getenv("WELCOME_DELAY_MINUTES", "5"))
    dry_run: bool = os.getenv("DRY_RUN", "false").lower() == "true"

    # Preferences for events (comma-separated, used in prompt)
    event_preferences: str = os.getenv(
        "EVENT_PREFERENCES",
        "sauna, street food, live musik, brætspil, minigolf, shuffleboard, ved vandet"
    ).strip()
