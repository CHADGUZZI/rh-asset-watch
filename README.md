# rh-asset-watch

Polls `https://api.robinhood.com/rhj/assets` and sends a Telegram message when
Robinhood adds (or removes) a stock token on Robinhood Chain.

Runs 24/7 for free on GitHub Actions (every 5 minutes, public repo = unlimited minutes).
The snapshot (`state.json`) is committed back to this repo so state survives between runs.

## Finish setup: connect Telegram (about 2 minutes)

1. In Telegram, open **@BotFather**, send `/newbot`, follow the prompts, copy the token.
2. Open your new bot in Telegram and send it any message (e.g. `hi`).
3. In a terminal, in this folder:
   ```
   echo "TELEGRAM_BOT_TOKEN=PASTE_TOKEN_HERE" > .env
   python3 watch.py --chat-id          # prints TELEGRAM_CHAT_ID=... ; add that line to .env
   python3 watch.py --test             # you should get a message on your phone
   gh secret set TELEGRAM_BOT_TOKEN --body "PASTE_TOKEN_HERE"
   gh secret set TELEGRAM_CHAT_ID  --body "PASTE_CHAT_ID_HERE"
   gh workflow run watch.yml           # optional: trigger a run now
   ```
`.env` is git-ignored and only used for local testing. The cloud job reads the two repo secrets.

## Operating

| Command | What it does |
|---|---|
| `gh run list --limit 5` | recent cloud runs |
| `gh run view --log` | log of the latest run |
| `gh workflow disable watch.yml` / `enable` | pause / resume |
| `python3 watch.py` | run one poll locally |
| `python3 watch.py --reseed` | reset snapshot without alerting (then commit + push) |

Alerts fire on new tickers, removed tickers, and status changes. If a Telegram
send fails, the snapshot is not advanced and the same diff is retried next run.

Latency: GitHub's cron runs every 5 minutes but is often delayed 5-15 minutes
under load. For sub-minute alerts, port `watch.py` to a Cloudflare Worker with a
1-minute Cron Trigger and KV storage (also free).

## Local fallback (optional)

`~/Library/LaunchAgents/com.chadguzzi.rh-asset-watch.plist` runs the same script
every 60 s while the Mac is awake. It is currently unloaded to avoid duplicate
alerts. Load it with `launchctl load <plist>` if you ever want it back.
