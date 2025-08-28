from __future__ import annotations
from datetime import datetime, timedelta

DA_DAYS = ["Man","Tir","Ons","Tor","Fre","Lør","Søn"]  # 0=Mon..6=Sun

def labels_until_next_sunday(now: datetime) -> list[str]:
    """Return labels from today to next Sunday (inclusive).
    If today is Sunday, return 7 labels (Sun..Sun)."""
    dow = now.weekday()  # 0=Mon..6=Sun
    dist = (6 - dow) if dow != 6 else 7
    days = []
    for i in range(dist + 1):
        d = now + timedelta(days=i)
        days.append(DA_DAYS[d.weekday()])
    return days
