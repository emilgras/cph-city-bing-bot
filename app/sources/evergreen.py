EVERGREEN = [
    {"title": "Sauna + havdyp 🧖‍♂️", "where": "Islands Brygge", "kind": "indoor"},
    {"title": "Street food 🍜", "where": "Reffen", "kind": "outdoor"},
    {"title": "Brætspilscafé 🎲", "where": "City", "kind": "indoor"},
    {"title": "Indendørs minigolf 🎯", "where": "Nørrebro", "kind": "indoor"},
    {"title": "Shuffleboard 🥌", "where": "Vesterbro", "kind": "indoor"},
    {"title": "BBQ i parken 🔥", "where": "Fælledparken", "kind": "outdoor"},
]

def pick_by_weather(ideas, forecast):
    bad = sum(1 for d in forecast if d["icon"] in ("🌧️","🌦️","☁️"))
    prefer_indoor = bad >= len(forecast)/2
    pool = [i for i in ideas if (i["kind"]=="indoor")==prefer_indoor] or ideas
    return pool[:5]
