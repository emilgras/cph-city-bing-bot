# Cph City Ping Bot — Agent (strict weather)

A tiny Heroku worker that pings a friend group in Copenhagen with a cozy Danish SMS:
intro + weather sketch (today → Sunday) + ~5 suggestions. **Weather must come from the Agent**
(grounded web search). If the Agent response is incomplete, the run aborts (no SMS).

## What it uses
- **Azure AI Foundry Agent** (with Grounding/Bing Search) — single call returns `intro`, `forecast`, `events`, `signoff`
- **Twilio** — sends SMS to recipients
- **Redis (Upstash)** — stores welcome/first/last-sent flags
- **Heroku Scheduler** — wakes the worker periodically; the app decides when to send

## Deploy quickstart
1. Create a Heroku app and add **Config Vars** (Settings → Reveal Config Vars):
   - `REDIS_URL`              = rediss://... (Upstash or other Redis)
   - `AGENT_ENDPOINT`         = https://<your-region>.api.cognitive.microsoft.com
   - `AGENT_API_KEY`          = <Agents bearer key>
   - `AGENT_ID`               = <Agent ID from AI Studio>
   - `TWILIO_ACCOUNT_SID`     = ...
   - `TWILIO_AUTH_TOKEN`      = ...
   - `TWILIO_FROM_NUMBER`     = +45xxxxxxxx
   - `RECIPIENT_NUMBERS`      = +45xxxxxxxx,+45yyyyyyyy
   - `SEND_DAY_OF_WEEK`       = 6        # default (Sunday), 0=Mon..6=Sun
   - `SEND_HOUR_LOCAL`        = 10       # local time
   - `SEND_INTERVAL_DAYS`     = 7        # cadence (7 or 14)
   - `WELCOME_DELAY_MINUTES`  = 5
   - `DRY_RUN`                = true     # set to false to actually send
   - `EVENT_PREFERENCES`      = sauna, street food, live musik, brætspil, minigolf, shuffleboard, ved vandet

2. Push code (GitHub or `git push heroku main`).

3. Add **Heroku Scheduler** job (Every 10 or 15 minutes) with command:
   ```
   python -m app
   ```

4. Watch logs:
   ```bash
   heroku logs --tail -a <your-app>
   ```

## Notes
- No OpenWeather integration at all. Agent must deliver full forecast for the required day labels (today→Sunday).
- If forecast is missing/incomplete, the worker prints `[ABORT] Missing/invalid forecast: ...` and sends nothing.
- SMS length is capped (~480 chars) by formatting function.


## Smoke test
Run from Heroku dyno:
```bash
heroku run python scripts/smoke.py -a <your-app>
```
Send a real test SMS (uses DRY_RUN env):
```bash
heroku run python scripts/smoke.py --send -a <your-app>
```
Generate welcome-style text:
```bash
heroku run python scripts/smoke.py --welcome -a <your-app>
```
