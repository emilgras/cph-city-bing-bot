from __future__ import annotations
import httpx, json, re
from datetime import datetime
from ..config import Config
from ..dateutil_dk import labels_until_next_sunday

class AgentError(Exception): pass
class AgentDataError(Exception): pass

async def ask_agent(endpoint: str, api_key: str, agent_id: str, query: str, timeout: float = 25.0) -> str:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"messages": [{"role": "user", "content": query}]}
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(f"{endpoint.rstrip('/')}/agents/{agent_id}/chat/completions",
                              headers=headers, json=payload)
        if r.status_code == 401:
            raise AgentError("Unauthorized – check AGENT_API_KEY/permissions")
        if r.status_code == 404:
            raise AgentError("Agent not found – check AGENT_ENDPOINT/AGENT_ID")
        r.raise_for_status()
        data = r.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        raise AgentError(f"Unexpected agent response: {e}")

def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S | re.I)
    if m:
        try: return json.loads(m.group(1))
        except Exception: pass
    m = re.search(r"(\{.*\})", text, re.S)
    if m:
        try: return json.loads(m.group(1))
        except Exception: pass
    return {}

async def find_intro_weather_events(endpoint: str, api_key: str, agent_id: str):
    """One agent call → (intro, forecast[], events[], signoff). Strict: forecast must cover today→Sunday."""
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

    text = await ask_agent(endpoint, api_key, agent_id, prompt)
    data = _extract_json(text) or {}

    intro = (data.get("intro") or "").strip()
    signoff = (data.get("signoff") or "— din Københavner-bot ☁️").strip()

    # Validate forecast strictly
    want = labels
    seen = set()
    forecast = []
    for d in (data.get("forecast") or []):
        lab = str(d.get("label","")).strip()
        if lab in want and lab not in seen:
            icon = (str(d.get("icon","")).strip() or "🌤️")
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
