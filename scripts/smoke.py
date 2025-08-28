#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import asyncio
import argparse
import time
import logging
from typing import Iterable

from app.config import Config
from app.state import r
from app.compose import format_sms
from app.sources.agent import find_intro_weather_events, AgentDataError
from app.sources.evergreen import EVERGREEN, pick_by_weather


# -------------------- logging --------------------

def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # Ekstra støj fra httpx nedtones i normal mode
    if not verbose:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("anyio").setLevel(logging.WARNING)


# -------------------- env & deps --------------------

def _mask(v: str) -> str:
    if not v:
        return ""
    return v if len(v) <= 6 else v[:3] + "…" + v[-2:]

def check_env(keys: Iterable[str]) -> bool:
    print("\n[ENV] Checking required variables …")
    ok = True
    for k in keys:
        v = os.getenv(k)
        if not v or not v.strip():
            print(f"[ENV] Missing: {k}")
            ok = False
        else:
            print(f"[ENV] {k} = {_mask(v)}")
    # Bonus: vis de vigtigste endpoints så fejl er tydelige
    if ok:
        print(f"[ENV] Project endpoint: {os.getenv('AGENT_PROJECT_ENDPOINT')}")
        print(f"[ENV] Agent API version: {os.getenv('AGENT_API_VERSION')}")
        print(f"[ENV] Agent id: {os.getenv('AGENT_ID')}")
    return ok

def test_redis() -> None:
    print("\n[REDIS] PING …", end=" ")
    t0 = time.perf_counter()
    try:
        r.ping()
        dt = (time.perf_counter() - t0) * 1000
        print(f"OK ({dt:.1f} ms)")
    except Exception as e:
        print("FAIL:", e)
        raise


# -------------------- agent flow --------------------

async def test_agent() -> tuple[str, list[dict], list[dict], str]:
    print("\n[AGENT] calling threads/runs …")
    intro, forecast, events, signoff = await find_intro_weather_events()
    print("[AGENT] intro:", (intro or "")[:80])
    print("[AGENT] forecast count:", len(forecast or []))
    print("[AGENT] events count:", len(events or []))
    return intro, forecast, events, signoff


# -------------------- sms --------------------

def maybe_send_sms(body: str, send: bool) -> None:
    from app.sender import send_sms
    preview = (body or "")[:240]
    print("\n[SMS] preview (first 240 chars):\n" + preview)
    if send:
        print("[SMS] sending via Twilio … DRY_RUN=", Config.dry_run)
        send_sms(body)
    else:
        print("[SMS] not sent (use --send to actually send)")


# -------------------- main --------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true", help="actually send a test SMS (respects DRY_RUN)")
    parser.add_argument("--welcome", action="store_true", help="format as welcome message")
    parser.add_argument("-v", "--verbose", action="store_true", help="verbose logging")
    args = parser.parse_args()

    setup_logging(args.verbose)

    must = [
        "REDIS_URL",
        "AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET",
        "AGENT_PROJECT_ENDPOINT", "AGENT_API_VERSION", "AGENT_ID",
    ]
    if args.send:
        must += ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER", "RECIPIENT_NUMBERS"]

    if not check_env(must):
        print("[EXIT] Missing environment; aborting.")
        return 2

    try:
        test_redis()
    except Exception:
        return 1

    try:
        intro, fc, ev, signoff = asyncio.run(test_agent())
    except AgentDataError as e:
        msg = str(e)
        print("[AGENT] FAILED:", msg)
        # Hjælpsomme hints ved rate limits
        if "rate_limit_exceeded" in msg or "Try again in" in msg:
            print("[AGENT] HINT: Systemet er midlertidigt mættet.")
            print("        • Vent det antal sekunder som beskeden angiver (eller lidt mere).")
            print("        • Kør igen – koden starter et NYT run på SAMME thread efter ventetid.")
            print("        • Sænk samtidighed / brug rate limiter, eller hæv kvoten hvis det er vedvarende.")
        return 3
    except Exception as e:
        print("[AGENT] ERROR:", e)
        return 4

    try:
        body = format_sms(
            intro= intro,
            forecast= fc,
            events= pick_by_weather((ev or []) + EVERGREEN, fc),
            signoff= signoff,
            welcome= args.welcome
        )
        maybe_send_sms(body, args.send)
    except Exception as e:
        print("[SMS] ERROR:", e)
        return 5

    print("\n[OK] smoke completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
