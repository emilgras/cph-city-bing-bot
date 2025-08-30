from __future__ import annotations
from datetime import datetime, timedelta

DA_DAYS = ["Man","Tir","Ons","Tor","Fre","Lør","Søn"]  # 0=Mon..6=Sun

def labels_next_7_days(now: datetime) -> list[str]:
    """Returner labels for de næste 7 dage startende i dag (inkl. dato)."""
    return [
        f"{DA_DAYS[(now.weekday() + i) % 7]} { (now + timedelta(days=i)).strftime('%d/%m') }"
        for i in range(7)
    ]
