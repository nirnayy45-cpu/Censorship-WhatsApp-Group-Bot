# WhatsApp URL Filter Bot

This service runs two cooperating processes:

- `url_filter_bot.py` — Telegram controls for scanning the WhatsApp QR code,
  selecting groups, toggling URL filtering, and managing keywords.
- `wa-filter-bridge.js` — the Baileys WhatsApp connection that deletes matching
  messages for everyone.

The `auth/` directory and JSON files are intentionally stored beside the service
so the WhatsApp login survives restarts. The WhatsApp account must be an admin
in every group where deletion is enabled.

## Required secret

Set `BOT_TOKEN` to the token created with Telegram's BotFather. Keep it in the
project's secure secrets, not in a file.

## Optional environment variables

- `ALLOWED_USER_IDS` — comma-separated Telegram user IDs. If omitted, anyone
  who discovers the bot can control it.
- `LOG_LEVEL` — defaults to `INFO`.

## First run

1. Start the service.
2. Open the Telegram bot and send `/link`.
3. Open the QR image sent by Telegram.
4. In WhatsApp, open **Settings → Linked devices → Link a device** and scan it.
5. Send `/groups` and select the groups to filter.

The bridge only deletes messages in selected groups. URL matching can be
disabled with `/urlfilter`; keywords are optional.