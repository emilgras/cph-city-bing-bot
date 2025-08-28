from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import datetime

from ..config import Config
from ..dateutil_dk import labels_until_next_sunday
from .agents_client import create_thread, post_message, run_thread, poll_run, get_messages


# --- Logging setup -----------------------------------------------------------

LOGGER_NAME = "foundry.agents.flow"
logger = logging.getLogger(LOGGER_NAME)

# Kør dette én gang i din app (ikke pr. modul) for globalt setup:
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s %(levelname)s %(name)s [corr=%(correlation_id)s] %(message)s",
# )

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

def _extract_json_from_messages(msgs: list[dict], log: logging.LoggerAdapter) -> dict:
    """Find seneste assistant-besked og parse JSON – med detaljeret logging."""
    log.debug("Extracting JSON from messages: %d message(s)", len(msgs))

    assistant_msgs = [m for m in msgs if m.get("role") == "assistant"]
    if not assistant_msgs:
        log.warning("No assistant messages found")
        return {}

    # I praksis giver Foundry seneste øverst; vi bruger første.
    content = assistant_msgs[0].get("content", [])
    parts_count = len(content) if isinstance(content, list) else 1
    log.debug("Assistant content parts: %s", parts_count)

    content_text = ""
    for part in (content if isinstance(content, list) else [content]):
        if isinstance(part, dict):
            text = part.get("text") or part.get("content") or ""
        else:
            text = str(part)
        content_text += (text or "")

    # Først: direkte JSON
    data = _safe_json_loads(content_text)
    if data:
        log.debug("Parsed JSON (direct) with keys: %s", list(data.keys()))
        return data

    # Derpå: fenced code block ```json {...}
    m = re.search(r"```json\s*(\{.*?\})\s*```", content_text, re.S | re.I)
    if m:
        data = _safe_json_loads(m.group(1))
        if data:
            log.debug("Parsed JSON (fenced block) with keys: %s", list(data.keys()))
            return data

    # Sidst: fang første {...}
    m = re.search(r"(\{.*\})", content_text, re.S)
    if m:
        data = _safe_json_loads(m.group(1))
        if data:
            log.debug("Parsed JSON (loose braces) with keys: %s", list(data.keys()))
            return data

    log.error("Failed to parse assistant output as JSON; first 200 chars: %r", content_text[:200])
    return {}


# --- Main flow ---------------------------------------------------------------

async def find_intro_weather_events() -> tuple[str, list[dict], list[dict], str]:
    """
    One Agent call via Foundry (threads/runs).
    Strict: forecast must cover today→Sunday.
    Adds detailed logging with correlation id, timings, and statuses.
    """
    correlation_id = uuid.uuid4().hex[:8]
    log = _with_corr_logger(correlation_id)
    logger.addFilter(_ContextFilter(correlation_id))

    t0 = time.perf_counter()
    log.info("Start find_intro_weather_events")

    now = datetime.now(tz=Config.tz)
    labels = labels_until_next_sunday(now)
    prefs = Config.event_preferences

    prompt = (
        "Du må browse nettet.\n"
        "Opgave: Generér alt indhold til en kort dansk SMS for en vennegruppe i København.\n"
        f"1) Skriv ÉN varm, uformel intro (15–25 ord).\n"
        f"2) Lav vejrskitse for København KUN for disse dage i rækkefølge: {', '.join(labels)}. "
        "Format pr. element: {\"label\":\"<Dag>\", \"icon\":\"EMOJI\", \"tmax\":<heltal>} (brug danske ugedage).\n"
        f"3) Find 5 aktuelle events i København denne uge. Prioritér: {prefs}. "
        "Format pr. event: {\"title\":\"…\",\"where\":\"…\",\"kind\":\"event\"}.\n"
        "4) Lav en kort sign-off (én sætning), hyggelig og neutral.\n\n"
        "Svar KUN som gyldig JSON i dette skema:\n"
        "{\n"
        "  \"intro\": \"...\",\n"
        "  \"forecast\": [ {\"label\":\"Man\",\"icon\":\"☀️\",\"tmax\":22}, ... ],\n"
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
    run_id = await run_thread(thread_id)
    log.info("Run started: %s (%.3fs)", run_id, time.perf_counter() - t)

    # 4) Poll run status
    t = time.perf_counter()
    run_state = await poll_run(thread_id, run_id)
    log.info(
        "Run finished with status=%s (%.3fs)",
        run_state.get("status"),
        time.perf_counter() - t,
    )

    if run_state.get("status") != "completed":
        log.error("Run not completed. State: %s", json.dumps(run_state)[:500])
        raise AgentDataError(f"Run status: {run_state.get('status')}")

    # 5) Fetch messages
    t = time.perf_counter()
    msgs = await get_messages(thread_id)
    log.info("Fetched %d message(s) (%.3fs)", len(msgs or []), time.perf_counter() - t)

    # 6) Parse JSON
    data = _extract_json_from_messages(msgs or [], log) or {}
    if not data:
        raise AgentDataError("Assistant did not return valid JSON")

    # 7) Validate & normalize data
    intro = (data.get("intro") or "").strip()
    signoff = (data.get("signoff") or "— din Københavner-bot ☁️").strip()

    want = labels
    seen = set()
    forecast: list[dict] = []
    for d in (data.get("forecast") or []):
        lab = str(d.get("label", "")).strip()
        if lab in want and lab not in seen:
            icon = (str(d.get("icon", "")).strip() or "🌤️")
            try:
                tmax = int(d.get("tmax", 20))
            except Exception as ex:
                log.exception("tmax parse error on %r", d)
                raise AgentDataError("tmax is not an integer") from ex
            forecast.append({"label": lab, "icon": icon, "tmax": tmax})
            seen.add(lab)
        else:
            log.debug("Skipping forecast entry (unexpected/duplicate): %r", d)

    if len(forecast) != len(want):
        missing = [lab for lab in want if lab not in seen]
        log.error("Forecast incomplete. Missing: %s | Got: %s", missing, [f["label"] for f in forecast])
        raise AgentDataError(f"Forecast incomplete: missing {missing}")

    events: list[dict] = []
    for e in (data.get("events") or [])[:5]:
        title = (e.get("title") or "").strip()
        where = (e.get("where") or "City").strip()
        if title:
            events.append({"title": title, "where": where, "kind": "event"})
        else:
            log.debug("Skipping event without title: %r", e)

    # 8) Done
    log.info(
        "Success: intro=%s chars, forecast=%d, events=%d, signoff=%s chars (total %.3fs)",
        len(intro),
        len(forecast),
        len(events),
        len(signoff),
        time.perf_counter() - t0,
    )

    return intro, forecast, events, signoff
