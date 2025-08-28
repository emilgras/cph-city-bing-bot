#!/usr/bin/env python3
"""Smoke test for Cph City Ping Bot (Agent strict).

Usage:
  python scripts/smoke.py                # read-only checks (Agent, Redis), no SMS
  python scripts/smoke.py --send         # actually send a tiny test SMS (uses DRY_RUN env)
  python scripts/smoke.py --welcome      # generate welcome-style intro
Notes:
  - Requires AGENT_ENDPOINT, AGENT_API_KEY, AGENT_ID, REDIS_URL (and Twilio vars for --send).
  - If DRY_RUN=true, SMS is not sent; only prints.
"""
from __future__ import annotations
import os, sys, asyncio, argparse
from datetime import datetime
from app.config import Config
from app.state import r
from app.sources.agent import find_intro_weather_events, AgentError, AgentDataError
from app.sources.evergreen import EVERGREEN, pick_by_weather
from app.compose import format_sms
from zoneinfo import ZoneInfo

def check_env(keys):
    ok = True
    for k in keys:
        if not os.getenv(k):
            print(f"[ENV] Missing: {k}")
            ok = False
        else:
            v = os.getenv(k)
            mask = v if len(v) <= 6 else v[:3] + "…" + v[-2:]
            print(f"[ENV] {k} = {mask}")
    return ok

async def test_agent():
    print("\n[AGENT] calling find_intro_weather_events() …")
    intro, forecast, events, signoff = await find_intro_weather_events(
        Config.agent_endpoint, Config.agent_api_key, Config.agent_id
    )
    print("[AGENT] intro:", intro[:80])
    print("[AGENT] forecast:", forecast)
    print("[AGENT] events:", events)
    return intro, forecast, events, signoff

def test_redis():
    print("\n[REDIS] PING …", end=" ")
    try:
        r.ping()
        print("OK")
        key = "cphbot:smoke_ts"
        r.set(key, datetime.now(tz=ZoneInfo("UTC")).isoformat())
        print("[REDIS] wrote key:", key)
    except Exception as e:
        print("FAIL:", e)
        raise

def maybe_send_sms(body: str):
    from app.sender import send_sms
    print("\n[SMS] preview (first 240 chars):\n" + body[:240])
    if args.send:
        print("[SMS] sending via Twilio … DRY_RUN=", Config.dry_run)
        send_sms(body)
    else:
        print("[SMS] not sent (use --send to actually send)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true", help="actually send a test SMS via Twilio")
    parser.add_argument("--welcome", action="store_true", help="format as welcome message (uses intro)")
    args = parser.parse_args()

    must = ["REDIS_URL","AGENT_ENDPOINT","AGENT_API_KEY","AGENT_ID"]
    if args.send:
        must += ["TWILIO_ACCOUNT_SID","TWILIO_AUTH_TOKEN","TWILIO_FROM_NUMBER","RECIPIENT_NUMBERS"]
    ok = check_env(must)
    if not ok:
        sys.exit(2)

    test_redis()

    try:
        intro, fc, ev, signoff = asyncio.run(test_agent())
    except (AgentError, AgentDataError) as e:
        print("[AGENT] FAILED:", e)
        sys.exit(3)
    except Exception as e:
        print("[AGENT] ERROR:", e)
        sys.exit(4)

    from app.sources.evergreen import EVERGREEN, pick_by_weather
    ideas = pick_by_weather((ev or []) + EVERGREEN, fc)
    body = format_sms(intro, fc, ideas, signoff, welcome=args.welcome)
    maybe_send_sms(body)
    print("\n[OK] smoke completed.")
