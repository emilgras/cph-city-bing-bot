EVERGREEN = [
    {"title": "Sauna + havdyp 🧖‍♂️", "where": "Islands Brygge", "kind": "event"},
    {"title": "Street food 🍜", "where": "Reffen", "kind": "event"},
    {"title": "Brætspilscafé 🎲", "where": "City", "kind": "event"},
    {"title": "Indendørs minigolf 🎯", "where": "Nørrebro", "kind": "event"},
    {"title": "Shuffleboard 🥌", "where": "Vesterbro", "kind": "event"},
    {"title": "BBQ i parken 🔥", "where": "Fælledparken", "kind": "event"},
]

def pick_by_weather(ideas, forecast):
    # Simple bias: if majority is bad weather → prefer "indoor-ish" items (guessing by title)
    bad = sum(1 for d in forecast if d["icon"] in ("🌧️","🌦️","☁️"))
    prefer_indoor = bad >= len(forecast)/2
    def is_indoor(x):
        t = (x.get("title","") + " " + x.get("where","")).lower()
        return any(w in t for w in ["indendørs","sauna","brætspil","minigolf","museum","shuffle"])
    pool = [i for i in ideas if is_indoor(i)] if prefer_indoor else ideas
    return pool[:5]
