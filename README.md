# Cph City Ping Bot — Foundry Agents (OAuth auto-refresh)

Hyggelig SMS-bot for København. Alt indhold (intro + vejr i dag→søndag + 5 events + signoff) hentes via
**Azure AI Foundry Agents API (threads/runs)**. **Ingen weather-fallback**: hvis forecast ikke er komplet,
afbrydes run’et (ingen SMS). Token hentes automatisk via **Azure AD (client credentials)** og fornyes når det udløber.

## Konfiguration (Heroku → Settings → Config Vars)
Obligatorisk:
- `REDIS_URL`               = rediss://... (Upstash/Redis)
- `AZURE_TENANT_ID`         = <Entra ID tenant>
- `AZURE_CLIENT_ID`         = <App registration client id>
- `AZURE_CLIENT_SECRET`     = <Client secret>
- `AGENT_PROJECT_ENDPOINT`  = https://foundry-<region>.services.ai.azure.com/api/projects/<projectName>
- `AGENT_API_VERSION`       = 2025-05-01
- `AGENT_ID`                = <agent/assistant id>
- `TWILIO_ACCOUNT_SID`      = ...
- `TWILIO_AUTH_TOKEN`       = ...
- `TWILIO_FROM_NUMBER`      = +45xxxxxxxx
- `RECIPIENT_NUMBERS`       = +45xxxxxxxx,+45yyyyyyyy

Valgfrit:
- `SEND_DAY_OF_WEEK`        = 6
- `SEND_HOUR_LOCAL`         = 10
- `SEND_INTERVAL_DAYS`      = 7
- `WELCOME_DELAY_MINUTES`   = 5
- `DRY_RUN`                 = true
- `EVENT_PREFERENCES`       = sauna, street food, live musik, brætspil, minigolf, shuffleboard, ved vandet

## Kørsel
- Heroku Scheduler job: Every 10–15 minutes → `python -m app`
- Logs: `heroku logs --tail -a <din-app>`

## Smoke test
```bash
heroku run python scripts/smoke.py -a <din-app>
heroku run python scripts/smoke.py --send -a <din-app>
heroku run python scripts/smoke.py --welcome -a <din-app>
```
