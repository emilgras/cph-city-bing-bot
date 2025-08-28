# Cph City Ping Bot — Azure AI Foundry Agents (threads/runs)

Hyggelig SMS-bot for en vennegruppe i København. Alt indhold (intro + vejr i dag→søndag + 5 events + signoff)
hentes via **Azure AI Foundry Agents API** (threads/runs). **Ingen weather-fallback** — hvis forecast ikke er komplet,
afbrydes run’et (ingen SMS). Kører som Heroku worker + Scheduler.

## Konfiguration (Heroku → Settings → Config Vars)
- `REDIS_URL`               = rediss://... (Upstash/Redis)
- `AGENT_PROJECT_ENDPOINT`  = https://foundry-<navn>.services.ai.azure.com/api/projects/<projectName>
- `AGENT_API_VERSION`       = 2025-05-01
- `AGENT_BEARER_TOKEN`      = <bearer token>
- `AGENT_ID`                = <agent/assistant id>
- `TWILIO_ACCOUNT_SID`      = ...
- `TWILIO_AUTH_TOKEN`       = ...
- `TWILIO_FROM_NUMBER`      = +45xxxxxxxx
- `RECIPIENT_NUMBERS`       = +45xxxxxxxx,+45yyyyyyyy
- `SEND_DAY_OF_WEEK`        = 6
- `SEND_HOUR_LOCAL`         = 10
- `SEND_INTERVAL_DAYS`      = 7
- `WELCOME_DELAY_MINUTES`   = 5
- `DRY_RUN`                 = true
- `EVENT_PREFERENCES`       = sauna, street food, live musik, brætspil, minigolf, shuffleboard, ved vandet

## Scheduler
Tilføj **Heroku Scheduler** job: Every 10–15 minutes → `python -m app`

## Smoke test
```bash
heroku run python scripts/smoke.py -a <din-app>
heroku run python scripts/smoke.py --send -a <din-app>
heroku run python scripts/smoke.py --welcome -a <din-app>
```
