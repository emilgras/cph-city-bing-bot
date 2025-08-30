from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import json
import logging
import re
import time
import uuid
from datetime import datetime

from ..config import Config
from ..dateutil_dk import labels_next_7_days
from .agents_client import create_thread, post_message, run_thread, poll_run, get_messages

DA_DAYS = ["Man","Tir","Ons","Tor","Fre","Lør","Søn"]  # 0=Mon..6=Sun

# --- Logging setup -----------------------------------------------------------

LOGGER_NAME = "foundry.agents.flow"
logger = logging.getLogger(LOGGER_NAME)

# Kør dette én gang i din app (ikke pr. modul) for globalt setup:
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s %(levelname)s %(name)s [corr=%(correlation_id)s] %(message)s",
# )

def labels_with_dates(now: datetime) -> list[str]:
    """Returner labels for de næste 7 dage (ugedag + dato)."""
    return [
        f"{DA_DAYS[(now.weekday() + i) % 7]} {(now + timedelta(days=i)).strftime('%d/%m')}"
        for i in range(7)
    ]

def labels_without_dates(now: datetime) -> list[str]:
    """Returner labels for de næste 7 dage (kun ugedag)."""
    return [DA_DAYS[(now.weekday() + i) % 7] for i in range(7)]

class _ContextFilter(logging.Filter):
    """Inject correlation_id into all log records (fallback: '-')."""

    def __init__(self, correlation_id: str | None):
        super().__init__()
        self.correlation_id = correlation_id or "-"

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "correlation_id"):
            record.correlation_id = self.correlation_id
        return True


def _with_corr_logger(correlation_id: str | None = None) -> logging.LoggerAdapter:
    # LoggerAdapter til at injicere correlation_id per-kald
    return logging.LoggerAdapter(logger, {"correlation_id": correlation_id or "-"})


# --- Errors ------------------------------------------------------------------


class AgentDataError(Exception):
    pass


# --- Helpers -----------------------------------------------------------------


def _safe_json_loads(s: str) -> dict:
    try:
        return json.loads(s)
    except Exception:
        return {}

def _flatten_text(obj) -> str:
    """Recursively collect string-like content from Foundry message objects."""
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, (int, float, bool)):
        return str(obj)
    if isinstance(obj, list):
        return "".join(_flatten_text(x) for x in obj)
    if isinstance(obj, dict):
        # Foundry bruger ofte {"type": "text", "text": "..."}
        if "text" in obj and isinstance(obj["text"], str):
            return obj["text"]
        if "value" in obj and isinstance(obj["value"], str):
            return obj["value"]
        if "input_text" in obj and isinstance(obj["input_text"], str):
            return obj["input_text"]

        v = obj.get("content")
        if isinstance(v, list):
            return "".join(_flatten_text(x) for x in v)
        if isinstance(v, str):
            return v
        return "".join(_flatten_text(x) for x in obj.values())

    return str(obj)


def _extract_json_from_messages(msgs: list[dict], log: logging.LoggerAdapter) -> dict:
    """Find seneste assistant-besked og parse JSON – robust mod nested shapes."""
    log.debug("Extracting JSON from messages: %d message(s)", len(msgs))

    assistant_msgs = [m for m in msgs if m.get("role") == "assistant"]
    if not assistant_msgs:
        log.warning("No assistant messages found")
        return {}

    # Foundry often returns newest first; we use the first assistant message.
    raw_content = assistant_msgs[0].get("content", [])
    content_text = _flatten_text(raw_content)

    if not content_text:
        log.error("Assistant content empty or unrecognized shape: %r", type(raw_content).__name__)
        return {}

    # 1) Direkt JSON
    data = _safe_json_loads(content_text)
    if data:
        log.debug("Parsed JSON (direct) with keys: %s", list(data.keys()))
        return data

    # 2) Fenced ```json ... ```
    m = re.search(r"```json\s*(\{.*?\})\s*```", content_text, re.S | re.I)
    if m:
        data = _safe_json_loads(m.group(1))
        if data:
            log.debug("Parsed JSON (fenced block) with keys: %s", list(data.keys()))
            return data

    # 3) Første {...} blob
    m = re.search(r"(\{.*\})", content_text, re.S)
    if m:
        data = _safe_json_loads(m.group(1))
        if data:
            log.debug("Parsed JSON (loose braces) with keys: %s", list(data.keys()))
            return data

    log.error("Failed to parse assistant output as JSON; first 200 chars: %r", content_text[:200])
    return {}



# --- Rate-limit helper -------------------------------------------------------

_RATE_HINT = re.compile(r"(\d+)\s*seconds", re.I)


def _retry_wait_seconds(msg: str, fallback: float = 20.0) -> float:
    """Parse 'Try again in N seconds' fra last_error.message."""
    m = _RATE_HINT.search(msg or "")
    return float(m.group(1)) if m else fallback


async def run_thread_with_retry(
    thread_id: str,
    *,
    max_attempts: int = 5,
    initial_wait: float = 20.0,
    escalate_step: float = 10.0,
    max_wait: float = 90.0,
    poll_interval: float = 2.0,
    poll_timeout: float = 180.0,
    log: logging.LoggerAdapter | None = None,
) -> dict:
    """
    Starter run og poller til completed. Ved rate_limit_exceeded:
    - venter (hint fra serveren, ellers initial_wait)
    - eskalerer ventetid ved gentagne fejl
    - starter ET NYT run på SAMME thread
    """
    log = log or _with_corr_logger("-")
    wait = 0.0
    for attempt in range(1, max_attempts + 1):
        if wait > 0:
            log.warning(
                "[AGENT] retry: sleeping %.1fs (attempt %d/%d)",
                wait,
                attempt,
                max_attempts,
            )
            await asyncio.sleep(wait)

        log.info("[AGENT] run=start (attempt %d/%d) thread=%s", attempt, max_attempts, thread_id)
        run_id = await run_thread(thread_id)
        log.info("[AGENT] calling threads/runs … run_id=%s", run_id)

        state = await poll_run(thread_id, run_id, interval=poll_interval, timeout=poll_timeout)
        status = state.get("status")
        err = (state.get("last_error") or {})
        code = err.get("code")
        msg = (err.get("message") or "")

        log.info("[AGENT] run=finished status=%s", status)

        if status == "completed":
            return state

        if status == "requires_action":
            log.error("[AGENT] run requires_action men der er ingen tool-håndtering implementeret")
            raise AgentDataError("Run requires_action (tool not handled)")

        if status == "failed" and code == "rate_limit_exceeded":
            hint = _retry_wait_seconds(msg, fallback=initial_wait)
            wait = min(max_wait, hint + (attempt - 1) * escalate_step)
            log.warning("[AGENT] rate_limit_exceeded: %r → wait=%.1fs", msg, wait)
            continue

        # Andre fejl → stop
        log.error("[AGENT] failed: status=%s code=%s msg=%r", status, code, msg)
        raise AgentDataError(f"Run failed: status={status}, code={code}, msg={msg}")

    raise AgentDataError("Gav op efter gentagne rate limits")


# --- Main flow ---------------------------------------------------------------

async def find_intro_weather_events(welcome: bool = False) -> tuple[str, list[dict], list[dict], str]:
    """
    One Agent call via Foundry (threads/runs).
    Strict: forecast must cover today→+6 dage.
    Adds detailed logging with correlation id, timings, and statuses.
    """
    correlation_id = uuid.uuid4().hex[:8]
    log = _with_corr_logger(correlation_id)
    logger.addFilter(_ContextFilter(correlation_id))

    t0 = time.perf_counter()
    log.info("Start find_intro_weather_events")

    now = datetime.now(tz=Config.tz)
    labels_prompt = labels_with_dates(now)      # til AI
    labels_sms = labels_without_dates(now)      # til SMS
    prefs = Config.event_preferences

    if welcome:
        # Enkel prompt kun til velkomst
        prompt = (
            "Skriv en kort, varm og uformel velkomsthilsen på dansk til en vennegruppe i København.\n"
            "Fortæl at du er deres nye Cph City Ping Bot 🤖, at du kan fiske fede events frem i byen,\n"
            "og at du ca. hver eller hveranden uge dumper et hyggeligt forslag i tråden, så de får en god grund til at ses.\n"
            "Hold det legende og chill i tonen. Max 320 tegn. Kun ren tekst – ingen JSON."
        )
    else:
        # Fuld JSON prompt
        prompt = (
            "Du må browse nettet.\n"
            "Opgave: Generér alt indhold til en kort dansk SMS for en vennegruppe i København.\n"
            f"1) Skriv ÉN varm, uformel intro (10–20 ord, gerne med lidt humor eller en kærlig stikpille til vennerne).\n"
            f"2) Lav vejrskitse for København KUN for disse dage i rækkefølge: {', '.join(labels_prompt)}. "
            "Format pr. element: {\"label\":\"<Dag>\", \"icon\":\"EMOJI\", \"tmax\":<heltal>} (brug danske ugedage).\n"
            f"3) Find 6 aktuelle events i København denne uge. Prioritér: {prefs}. "
            "Format pr. event: {\"title\":\"…\",\"where\":\"…\",\"kind\":\"event\"}.\n"
            "(titler må gerne lyde fristende eller lidt fjollede)\n"
            "4) Lav en kort sign-off (én sætning), hyggelig, neutral – men med et glimt i øjet.\n\n"
            "Svar KUN som gyldig JSON i dette skema:\n"
            "{\n"
            "  \"intro\": \"...\",\n"
            "  \"forecast\": [ {\"label\":\"Man 01/09\",\"icon\":\"☀️\",\"tmax\":22}, ... ],\n"
            "  \"events\":   [ {\"title\":\"…\",\"where\":\"…\",\"kind\":\"event\"}, ... ],\n"
            "  \"signoff\":  \"...\"\n"
            "}\n"
            "Ingen forklaringer, ingen markdown – KUN JSON."
        )

    # 1) Create thread
    t = time.perf_counter()
    thread_id = await create_thread()
    log.info("Thread created: %s (%.3fs)", thread_id, time.perf_counter() - t)

    # 2) Post message
    t = time.perf_counter()
    await post_message(thread_id, "user", prompt)
    log.info("User message posted (%.3fs)", time.perf_counter() - t)

    # 3) Run the thread
    t = time.perf_counter()
    run_state = await run_thread_with_retry(thread_id, log=log)
    log.info("Run finished with status=%s (%.3fs)", run_state.get("status"), time.perf_counter() - t)

    if run_state.get("status") != "completed":
        log.error("Run not completed. State: %s", json.dumps(run_state)[:500])
        raise AgentDataError(f"Run status: {run_state.get('status')}")

    # 4) Fetch messages
    t = time.perf_counter()
    msgs = await get_messages(thread_id)
    log.info("Fetched %d message(s) (%.3fs)", len(msgs or []), time.perf_counter() - t)

    if welcome:
        # Returnér velkomsttekst som "intro", resten tomt
        text = _flatten_text(msgs[0].get("content")) if msgs else ""
        welcome_text = (text or "").strip()
        return welcome_text, [], [], "— din Københavner-bot ☁️"

    # 5) Parse JSON
    data = _extract_json_from_messages(msgs or [], log) or {}
    if not data:
        raise AgentDataError("Assistant did not return valid JSON")

    # 6) Validate & normalize data
    intro = (data.get("intro") or "").strip()
    signoff = (data.get("signoff") or "— din Københavner-bot ☁️").strip()

    want = labels_prompt
    seen = set()
    forecast_ai: list[dict] = []
    for d in (data.get("forecast") or []):
        lab = str(d.get("label", "")).strip()
        if lab in want and lab not in seen:
            icon = (str(d.get("icon", "")).strip() or "🌤️")
            try:
                tmax = int(d.get("tmax", 20))
            except Exception as ex:
                log.exception("tmax parse error on %r", d)
                raise AgentDataError("tmax is not an integer") from ex
            forecast_ai.append({"label": lab, "icon": icon, "tmax": tmax})
            seen.add(lab)
        else:
            log.debug("Skipping forecast entry (unexpected/duplicate): %r", d)

    if len(forecast_ai) != len(want):
        missing = [lab for lab in want if lab not in seen]
        log.error("Forecast incomplete. Missing: %s | Got: %s", missing, [f["label"] for f in forecast_ai])
        raise AgentDataError(f"Forecast incomplete: missing {missing}")

    # Post-process forecast → erstat labels med kun ugedag (uden dato) til SMS
    forecast_sms: list[dict] = []
    for idx, d in enumerate(forecast_ai):
        forecast_sms.append({
            "label": labels_sms[idx],
            "icon": d["icon"],
            "tmax": d["tmax"]
        })

    events: list[dict] = []
    for e in (data.get("events") or [])[:5]:
        title = (e.get("title") or "").strip()
        where = (e.get("where") or "City").strip()
        if title:
            events.append({"title": title, "where": where, "kind": "event"})
        else:
            log.debug("Skipping event without title: %r", e)

    # 7) Done
    log.info(
        "Success: intro=%s chars, forecast=%d, events=%d, signoff=%s chars (total %.3fs)",
        len(intro),
        len(forecast_sms),
        len(events),
        len(signoff),
        time.perf_counter() - t0,
    )

    return intro, forecast_sms, events, signoff
