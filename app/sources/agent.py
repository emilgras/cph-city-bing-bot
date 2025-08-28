from __future__ import annotations
import json, re
from datetime import datetime
from ..config import Config
from ..dateutil_dk import labels_until_next_sunday
from .agents_client import create_thread, post_message, run_thread, poll_run, get_messages

class AgentDataError(Exception): pass

def _extract_json_from_messages(msgs: list[dict]) -> dict:
    # Find latest assistant message and collect text parts
    assistant_msgs = [m for m in msgs if m.get("role") == "assistant"]
    if not assistant_msgs:
        return {}
    content_text = ""
    for part in assistant_msgs[0].get("content", []):
        if isinstance(part, dict):
            text = part.get("text") or part.get("content") or ""
        else:
            text = str(part)
        content_text += (text or "")
    # Try parsing JSON
    try:
        return json.loads(content_text)
    except Exception:
        pass
    m = re.search(r"```json\s*(\{.*?\})\s*```", content_text, re.S | re.I)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    m = re.search(r"(\{.*\})", content_text, re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    return {}

async def find_intro_weather_events() -> tuple[str, list[dict], list[dict], str]:
    """One Agent call via Foundry (threads/runs). Strict: forecast must cover today→Sunday."""
    now = datetime.now(tz=Config.tz)
    labels = labels_until_next_sunday(now)
    prefs  = Config.event_preferences

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

    thread_id = await create_thread()
    await post_message(thread_id, "user", prompt)
    run_id = await run_thread(thread_id)
    run_state = await poll_run(thread_id, run_id)
    if run_state.get("status") != "completed":
        raise AgentDataError(f"Run status: {run_state.get('status')}")
    msgs = await get_messages(thread_id)
    data = _extract_json_from_messages(msgs) or {}

    intro = (data.get("intro") or "").strip()
    signoff = (data.get("signoff") or "— din Københavner-bot ☁️").strip()

    # Validate forecast strictly
    want = labels
    seen = set()
    forecast = []
    for d in (data.get("forecast") or []):
        lab = str(d.get("label", "")).strip()
        if lab in want and lab not in seen:
            icon = (str(d.get("icon", "")).strip() or "🌤️")
            try:
                tmax = int(d.get("tmax", 20))
            except Exception:
                raise AgentDataError("tmax is not an integer")
            forecast.append({"label": lab, "icon": icon, "tmax": tmax})
            seen.add(lab)

    if len(forecast) != len(want):
        missing = [lab for lab in want if lab not in seen]
        raise AgentDataError(f"Forecast incomplete: missing {missing}")

    # Normalize events
    events = []
    for e in (data.get("events") or [])[:5]:
        title = (e.get("title") or "").strip()
        where = (e.get("where") or "City").strip()
        if title:
            events.append({"title": title, "where": where, "kind": "event"})

    return intro, forecast, events, signoff
