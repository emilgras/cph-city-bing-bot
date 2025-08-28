import redis
from datetime import datetime
from .config import Config

r = redis.Redis.from_url(Config.redis_url, decode_responses=True)

KEYS = {
    "welcome": "cphbot:welcome_sent",
    "first": "cphbot:first_suggestion_sent",
    "last": "cphbot:last_sent_at",
}

def get_flag(name: str) -> bool:
    return r.get(KEYS[name]) == "1"

def set_flag(name: str, value: bool = True):
    r.set(KEYS[name], "1" if value else "0")

def get_last_sent(tz) -> datetime | None:
    v = r.get(KEYS["last"])
    if not v: return None
    return datetime.fromisoformat(v).astimezone(tz)

def set_last_sent(dt: datetime):
    r.set(KEYS["last"], dt.isoformat())
