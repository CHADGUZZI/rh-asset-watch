#!/usr/bin/env python3
"""
Robinhood Chain stock-token watcher.

Polls https://api.robinhood.com/rhj/assets, diffs against the last snapshot,
and sends a Telegram message when tickers are added (or removed).

Usage:
  python3 watch.py            # one poll cycle (what launchd runs every 60s)
  python3 watch.py --test     # send a test Telegram message
  python3 watch.py --chat-id  # print chat IDs that have messaged the bot
  python3 watch.py --reseed   # rebuild snapshot from the live API, no alerts

Config lives in .env next to this file:
  TELEGRAM_BOT_TOKEN=123456:ABC...
  TELEGRAM_CHAT_ID=123456789
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(HERE, ".env")
STATE_FILE = os.path.join(HERE, "state.json")
LOG_FILE = os.path.join(HERE, "watch.log")
API_URL = "https://api.robinhood.com/rhj/assets"
EXPLORER = "https://explorer.robinhood.com/address/"  # best-effort link
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) rh-asset-watch/1.0",
    "Accept": "application/json",
}


def log(msg):
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def load_env():
    cfg = {}
    if os.path.exists(ENV_FILE):
        for raw in open(ENV_FILE):
            raw = raw.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            k, v = raw.split("=", 1)
            cfg[k.strip()] = v.strip().strip('"').strip("'")
    cfg.setdefault("TELEGRAM_BOT_TOKEN", os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    cfg.setdefault("TELEGRAM_CHAT_ID", os.environ.get("TELEGRAM_CHAT_ID", ""))
    return cfg


def http_json(url, data=None, timeout=20):
    body = None
    headers = dict(HEADERS)
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def fetch_assets():
    data = http_json(API_URL)
    assets = data.get("assets") or []
    out = {}
    for a in assets:
        sym = a.get("tokenSymbol")
        if not sym:
            continue
        dep = (a.get("deployments") or [{}])[0]
        out[sym] = {
            "name": (a.get("tokenName") or "").replace(" • Robinhood Token", "").strip(),
            "address": dep.get("contractAddress", ""),
            "chainId": dep.get("chainId"),
            "status": a.get("status", ""),
            "isin": a.get("isin", ""),
            "multiplier": a.get("currentMultiplier", ""),
        }
    return out


def load_state():
    if not os.path.exists(STATE_FILE):
        return None
    try:
        return json.load(open(STATE_FILE))
    except (OSError, ValueError):
        return None


def save_state(assets):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"assets": assets}, f, indent=1, sort_keys=True)
    os.replace(tmp, STATE_FILE)


def send_telegram(cfg, text):
    token, chat = cfg.get("TELEGRAM_BOT_TOKEN"), cfg.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        log("Telegram not configured (fill TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env). Message was:\n" + text)
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # Telegram caps messages at 4096 chars; split if needed.
    chunks = [text[i:i + 3900] for i in range(0, len(text), 3900)] or [text]
    ok = True
    for c in chunks:
        try:
            resp = http_json(url, {"chat_id": chat, "text": c, "parse_mode": "HTML", "disable_web_page_preview": "true"})
            ok = ok and bool(resp.get("ok"))
        except Exception as e:  # noqa: BLE001
            log(f"Telegram send failed: {e}")
            ok = False
    return ok


def fmt_asset(sym, a):
    line = f"<b>{sym}</b> — {a['name']}"
    if a.get("address"):
        line += f"\n<code>{a['address']}</code>"
    if a.get("status") and a["status"] != "ASSET_STATUS_ACTIVE":
        line += f"\n  status: {a['status'].replace('ASSET_STATUS_', '')}"
    return line


def poll(cfg):
    try:
        live = fetch_assets()
    except Exception as e:  # noqa: BLE001
        log(f"fetch failed: {e}")
        return
    if len(live) < 20:
        # Guard against a broken/partial response wiping the snapshot and
        # triggering a flood of false "removed" alerts.
        log(f"suspiciously small response ({len(live)} assets); skipping")
        return

    state = load_state()
    if state is None:
        save_state(live)
        log(f"seeded snapshot with {len(live)} assets")
        send_telegram(cfg, f"🟢 rh-asset-watch started. Tracking {len(live)} Robinhood Chain stock tokens. "
                           f"You'll get a message here the moment a new ticker shows up on the API.")
        return

    old = state.get("assets", {})
    added = sorted(set(live) - set(old))
    removed = sorted(set(old) - set(live))
    status_changes = sorted(s for s in set(live) & set(old) if live[s].get("status") != old[s].get("status"))

    if not (added or removed or status_changes):
        log(f"no change ({len(live)} assets)")
        # still refresh multipliers etc. silently
        save_state(live)
        return

    parts = []
    if added:
        parts.append(f"🚨 <b>{len(added)} NEW Robinhood Chain stock token{'s' if len(added) > 1 else ''}</b>\n\n"
                     + "\n\n".join(fmt_asset(s, live[s]) for s in added))
    if status_changes:
        parts.append("🔄 <b>Status changed</b>\n" + "\n".join(
            f"{s}: {old[s].get('status', '').replace('ASSET_STATUS_', '')} → {live[s].get('status', '').replace('ASSET_STATUS_', '')}"
            for s in status_changes))
    if removed:
        parts.append("❌ <b>Removed from API</b>\n" + "\n".join(f"{s} — {old[s].get('name', '')}" for s in removed))
    parts.append(f"Total now: {len(live)} · {API_URL}")
    msg = "\n\n".join(parts)

    log(f"CHANGE added={added} removed={removed} status={status_changes}")
    sent = send_telegram(cfg, msg)
    if sent or not (cfg.get("TELEGRAM_BOT_TOKEN") and cfg.get("TELEGRAM_CHAT_ID")):
        # Only advance the snapshot if we delivered (or if Telegram isn't set up,
        # so we don't loop forever). If a configured send fails, retry next cycle.
        save_state(live)
    else:
        log("send failed; will retry with same diff next cycle")


def cmd_chat_id(cfg):
    token = cfg.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Set TELEGRAM_BOT_TOKEN in .env first.")
        return 1
    resp = http_json(f"https://api.telegram.org/bot{token}/getUpdates")
    seen = {}
    for u in resp.get("result", []):
        m = u.get("message") or u.get("channel_post") or {}
        chat = m.get("chat") or {}
        if chat.get("id"):
            seen[chat["id"]] = f"{chat.get('type')} {chat.get('title') or chat.get('username') or chat.get('first_name')}"
    if not seen:
        print("No messages yet. Open Telegram, send your bot any message (e.g. 'hi'), then run this again.")
        return 1
    for cid, desc in seen.items():
        print(f"TELEGRAM_CHAT_ID={cid}    # {desc}")
    return 0


def main(argv):
    cfg = load_env()
    if "--chat-id" in argv:
        return cmd_chat_id(cfg)
    if "--test" in argv:
        ok = send_telegram(cfg, f"✅ rh-asset-watch test message at {datetime.now().strftime('%H:%M:%S')}. Alerts are working.")
        print("sent" if ok else "NOT sent — check .env and watch.log")
        return 0 if ok else 1
    if "--reseed" in argv:
        live = fetch_assets()
        save_state(live)
        print(f"snapshot reseeded with {len(live)} assets")
        return 0
    poll(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
