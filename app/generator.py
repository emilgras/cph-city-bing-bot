from openai import AzureOpenAI

MAX_CHARS = 480

SYSTEM = (
    "Du er en dansk SMS-bot for en vennegruppe i København. "
    "Skriv kort, varmt og uformelt. Ingen svar nødvendig. "
    "Struktur: kort hilsen + 'Vejret' blok (2-4 linjer) + 'Forslag' 5 bullets + sign-off. "
    "Hold ALT under 480 tegn. Brug danske ugedage og emojis."
)

def build_prompt(forecast, suggestions, welcome=False):
    if welcome:
        return "Skriv en velkomstbesked (dansk), varm og kort, max 480 tegn. Forklar botten og at første forslag kommer om lidt."
    lines = ["Hej bande! Skal vi finde på noget snart?", "", "Vejret:"]
    for d in forecast:
        lines.append(f"{d['icon']} {d['label']}: {d['tmax']}°")
    lines.append("\nForslag:")
    for s in suggestions[:5]:
        lines.append(f"• {s['title']} ({s['where']})")
    lines.append("\n— din Københavner-bot ☁️  \nIngen svar nødvendig. Skriv STOP for at framelde.")
    draft = "\n".join(lines)
    return f"Gør denne tekst kortere, hyggelig (dansk), under 480 tegn:\n\n{draft}"

def trim_to_limit(text: str, limit: int = MAX_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit]

def generate(client: AzureOpenAI, system: str, prompt: str) -> str:
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"system","content":system}, {"role":"user","content":prompt}],
        temperature=0.7,
        max_tokens=180,
    )
    text = resp.choices[0].message.content.strip()
    return trim_to_limit(text)
