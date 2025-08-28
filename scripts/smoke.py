#!/usr/bin/env python3
from __future__ import annotations
import os, sys, asyncio, argparse
from app.config import Config
from app.state import r
from app.compose import format_sms
from app.sources.agent import find_intro_weather_events, AgentDataError
from app.sources.evergreen import EVERGREEN, pick_by_weather

def check_env(keys):
    ok = True
    for k in keys:
        v = os.getenv(k)
        if not v:
            print(f"[ENV] Missing: {k}"); ok = False
        else:
            mask = v if len(v) <= 6 else v[:3] + "…" + v[-2:]
            print(f"[ENV] {k} = {mask}")
    return ok

def test_redis():
    print("\n[REDIS] PING …", end=" ")
    try:
        r.ping()
        print("OK")
    except Exception as e:
        print("FAIL:", e); raise

async def test_agent():
    print("\n[AGENT] calling threads/runs …")
    intro, forecast, events, signoff = await find_intro_weather_events()
    print("[AGENT] intro:", intro[:80])
    print("[AGENT] forecast count:", len(forecast))
    print("[AGENT] events count:", len(events))
    return intro, forecast, events, signoff

def maybe_send_sms(body: str, send: bool):
    from app.sender import send_sms
    print("\n[SMS] preview (first 240 chars):\n" + body[:240])
    if send:
        print("[SMS] sending via Twilio … DRY_RUN=", Config.dry_run)
        send_sms(body)
    else:
        print("[SMS] not sent (use --send to actually send)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true", help="actually send a test SMS (respects DRY_RUN)")
    parser.add_argument("--welcome", action="store_true", help="format as welcome message")
    args = parser.parse_args()

    must = [
        "REDIS_URL",
        "AZURE_TENANT_ID","AZURE_CLIENT_ID","AZURE_CLIENT_SECRET",
        "AGENT_PROJECT_ENDPOINT","AGENT_API_VERSION","AGENT_ID",
    ]
    if args.send:
        must += ["TWILIO_ACCOUNT_SID","TWILIO_AUTH_TOKEN","TWILIO_FROM_NUMBER","RECIPIENT_NUMBERS"]
    if not check_env(must):
        sys.exit(2)

    test_redis()

    try:
        intro, fc, ev, signoff = asyncio.run(test_agent())
    except AgentDataError as e:
        print("[AGENT] FAILED:", e); sys.exit(3)
    except Exception as e:
        print("[AGENT] ERROR:", e); sys.exit(4)

    body = format_sms(intro, fc, pick_by_weather((ev or []) + EVERGREEN, fc), signoff, welcome=args.welcome)
    maybe_send_sms(body, args.send)
    print("\n[OK] smoke completed.")
