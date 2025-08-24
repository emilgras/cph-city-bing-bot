import asyncio
from datetime import datetime
from .config import Config
from .state import set_flag, set_last_sent
from .schedule import should_send_welcome, should_send_first_suggestion, should_send_regular
from .sources.weather import fetch_week_forecast
from .sources.webscout import scout_events
from .sources.evergreen import EVERGREEN, pick_by_weather
from .generator import build_prompt, generate, SYSTEM
from .sender import send_sms
from openai import AzureOpenAI

async def build_message(welcome=False):
    forecast = await fetch_week_forecast(Config.owm_key)
    web_hits = await scout_events(Config.bing_key, for_when="weekend")
    hits = [{"title": h["title"], "where": h["source"], "kind": "event"} for h in web_hits]
    pool = (hits or []) + EVERGREEN
    ideas = pick_by_weather(pool, forecast)
    client = AzureOpenAI(api_key=Config.azure_key, azure_endpoint=Config.azure_endpoint, api_version="2024-06-01")
    prompt = build_prompt(forecast, ideas, welcome=welcome)
    text = generate(client, SYSTEM, prompt)
    return text

def run_once():
    now = datetime.now(tz=Config.tz)
    async def do_send(welcome=False):
        msg = await build_message(welcome=welcome)
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
