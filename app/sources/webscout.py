import httpx
from bs4 import BeautifulSoup

BING_ENDPOINT = "https://api.bing.microsoft.com/v7.0/search"

async def bing_search(key: str, query: str, count: int = 6):
    headers = {"Ocp-Apim-Subscription-Key": key}
    params = {"q": query, "mkt": "da-DK", "count": count, "safeSearch": "Moderate"}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(BING_ENDPOINT, headers=headers, params=params)
        r.raise_for_status()
        data = r.json()
    out = []
    for w in data.get("webPages", {}).get("value", [])[:count]:
        out.append({
            "title": w.get("name"),
            "url": w.get("url"),
            "snippet": w.get("snippet"),
            "displayUrl": w.get("displayUrl"),
        })
    return out

async def quick_scrape(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, follow_redirects=True)
            r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else url
        p = soup.find("p")
        text = p.get_text(" ", strip=True)[:300] if p else ""
        return f"{title} — {text}"
    except Exception:
        return ""

async def scout_events(key: str, for_when: str = "weekend"):
    q = f"København events {for_when} koncerter street food markeder kalender"
    results = await bing_search(key, q, count=6)
    enriched = []
    for r in results:
        snippet = r.get("snippet") or await quick_scrape(r["url"]) or ""
        enriched.append({"title": r["title"], "snippet": snippet, "source": r["displayUrl"]})
    return enriched
