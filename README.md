# Termin Checker — Bonn Ausländeramt

A Telegram bot that watches the [Bonn Ausländeramt](https://termine.bonn.de/m/auslaenderamt/extern/calendar/) appointment calendar and notifies a Telegram chat the moment a free slot appears.

## What it does

1. Opens the booking flow in a headless Chromium browser (Playwright).
2. Navigates to the **"Aufenthaltstitel zum Zweck der Bildung"** service for a Bonn postcode e.g. **53119**.
3. Reads the rendered page and decides whether free slots are available.
4. Notifies Telegram:
   - **Instantly** when a slot appears (text + screenshot).
   - **Every 5 hours** a "still running" heartbeat when there are no slots.
   - **Daily summary** at 21:00.

## How detection works

The page text is normalised (whitespace collapsed) and matched case-insensitively:

| Page content | Verdict |
|---|---|
| `keine freien termine` | No slots |
| Calendar (`auswahl des termins` / `suchen sie sich bitte ein datum`) without that phrase | Slot likely available |
| Anything else (service selection, session expired, …) | Silently retry |

Alerts are **de-duplicated by page content**, so the bot does not re-send for the same slot. Slot alerts attach a screenshot (no HTML).

## Requirements

- Python 3.9+
- Playwright + Chromium

```bash
python -m venv .venv
source .venv/bin/activate
pip install playwright requests nest_asyncio
python -m playwright install --with-deps chromium
```

## Configuration

At the top of `checker_clean.py`:

| Setting | Description | Default |
|---|---|---|
| `TELEGRAM_TOKEN` | Bot token from [@BotFather](https://t.me/BotFather) | — |
| `TELEGRAM_CHAT_ID` | Chat/group to notify | — |
| `CHECK_INTERVAL` | Seconds between checks | `20` |
| `GENERAL_MESSAGE_INTERVAL_SECONDS` | Heartbeat interval | `5 * 3600` (5h) |
| `DAILY_SUMMARY_HOUR` | Hour for the daily summary | `21` |


## Running

```bash
python BonnTerminBot.py
```

For a persistent background run:

```bash
nohup .venv/bin/python BonnTerminBot.py > nohup.out 2>&1 < /dev/null &
```

Stop it with:

```bash
pkill -f 'BonnTerminBot[.]py'
```

## Notes & caveats

- The booking flow relies on brittle selectors (test IDs and labels). If the city updates the page, these break and the bot will need selector fixes.
- Frequent checks can trigger rate-limiting or IP blocking — keep `CHECK_INTERVAL` reasonable.
- This is for personal use; respect the site's terms of service.
