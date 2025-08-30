import asyncio
from datetime import datetime
from .config import Config
from .state import set_flag, set_last_sent
from .schedule import should_send_welcome, should_send_first_suggestion, should_send_regular
from .sources.agent import find_intro_weather_events, AgentDataError
from .sources.evergreen import EVERGREEN, pick_by_weather
from .sender import send_sms

MAX_CHARS = 480

def format_sms(intro: str, forecast: list[dict], ideas: list[dict], signoff: str, welcome=False) -> str:
    if welcome and intro:
        text = (
            f"{intro}\n"
            "PS: Om lidt sender jeg mit første forslag 😉\n"
            f"{signoff}\n"
            "Ingen svar nødvendig. Skriv STOP for at framelde."
        )
        return text[:MAX_CHARS]

    lines = [intro or "Hej bande! Skal vi finde på noget snart? 😊", "", "Vejret:"]
    for d in forecast:
        lines.append(f"{d['icon']} {d['label']}: {d['tmax']}°")

    lines.append("\nForslag:")
    for s in ideas[:5]:
        lines.append(f"• {s['title']} ({s['where']})")

    lines.append(f"\n{signoff or '— din Københavner-bot ☁️'}")
    lines.append("Ingen svar nødvendig. Skriv STOP for at framelde.")
    return "\n".join(lines)[:MAX_CHARS]

async def build_message(welcome=False):
    intro, forecast, events, signoff = await find_intro_weather_events(welcome=welcome)

    pool = (events or []) + EVERGREEN
    ideas = pick_by_weather(pool, forecast)

    return format_sms(intro, forecast, ideas, signoff, welcome=welcome)

def run_once():
    now = datetime.now(tz=Config.tz)

    async def do_send(welcome=False):
        try:
            msg = await build_message(welcome=welcome)
        except AgentDataError as e:
            print(f"[ABORT] Missing/invalid forecast: {e}")
            return
        except Exception as e:
            print(f"[ERROR] Agent call failed: {e}")
            return
        send_sms(msg)
        set_last_sent(now)

    if should_send_welcome(now):
        asyncio.run(do_send(welcome=True))
        set_flag("welcome", True)
        return

    if should_send_first_suggestion(now):
        asyncio.run(do_send(welcome=False))
        set_flag("first", True)
        return

    if should_send_regular(now):
        asyncio.run(do_send(welcome=False))
        return

    print("[noop] Not time yet.")
