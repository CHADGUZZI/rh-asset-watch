# rh-asset-watch

Polls `https://api.robinhood.com/rhj/assets` every 60 seconds and sends a Telegram
message when Robinhood adds (or removes) a stock token on Robinhood Chain.

## One-time setup (about 2 minutes)

1. In Telegram, open **@BotFather**, send `/newbot`, follow the prompts, copy the token.
2. Put the token in `.env` as `TELEGRAM_BOT_TOKEN=...`.
3. Open your new bot in Telegram and send it any message.
4. In a terminal:
   ```
   cd "/Users/chadguzzi/Downloads/Perception/AI Brains/CRYPTO/rh-asset-watch"
   python3 watch.py --chat-id      # prints TELEGRAM_CHAT_ID=... ; paste into .env
   python3 watch.py --test         # you should get a message on your phone
   ```

The launchd job is already loaded and re-reads `.env` every cycle, so no restart is needed.

## Operating

| Command | What it does |
|---|---|
| `launchctl list \| grep rh-asset` | confirm the job is loaded |
| `tail -f watch.log` | watch polling activity |
| `launchctl unload ~/Library/LaunchAgents/com.chadguzzi.rh-asset-watch.plist` | stop |
| `launchctl load ~/Library/LaunchAgents/com.chadguzzi.rh-asset-watch.plist` | start |
| `python3 watch.py --reseed` | reset snapshot without alerting |

Runs only while this Mac is awake. For 24/7 coverage, run the same script on a
cheap VPS with cron (`* * * * * cd /path && python3 watch.py`) or as a GitHub
Actions cron job with the two env vars stored as repo secrets.
