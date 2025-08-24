from datetime import datetime, timedelta
from .config import Config
from .state import get_flag, get_last_sent

def should_send_welcome(now: datetime) -> bool:
    return not get_flag("welcome")

def should_send_first_suggestion(now: datetime) -> bool:
    last = get_last_sent(Config.tz)
    return (get_flag("welcome") and not get_flag("first") and last and
            now >= last + timedelta(minutes=Config.welcome_delay_min))

def should_send_regular(now: datetime) -> bool:
    if not get_flag("first"):
        return False
    last = get_last_sent(Config.tz)
    if last is None:
        return True
    correct_day = now.weekday() == Config.send_dow
    correct_hour = now.hour == Config.send_hour and now.minute < 15
    enough_days = (now - last).days >= Config.interval_days
    return correct_day and correct_hour and enough_days
