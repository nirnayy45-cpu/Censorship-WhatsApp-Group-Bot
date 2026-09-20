# WhatsApp URL Filter Bot

Telegram-controlled WhatsApp bot that removes URLs and configured keywords from selected groups.

## Run & Operate

- `pnpm --filter @workspace/api-server run dev` — run the API server (port 5000)
- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from the OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- Required env: `DATABASE_URL` — Postgres connection string
- `bash services/whatsapp-url-filter/start.sh` — run the Telegram control bot and WhatsApp bridge together
- Required secret: `BOT_TOKEN`
- Optional env: `ALLOWED_USER_IDS`, `LOG_LEVEL`

## Stack

- pnpm workspaces, Node.js 24, TypeScript 5.9
- API: Express 5
- DB: PostgreSQL + Drizzle ORM
- Validation: Zod (`zod/v4`), `drizzle-zod`
- API codegen: Orval (from OpenAPI spec)
- Build: esbuild (CJS bundle)

## Where things live

- `services/whatsapp-url-filter/url_filter_bot.py` — Telegram control surface
- `services/whatsapp-url-filter/wa-filter-bridge.js` — WhatsApp connection and deletion logic
- `services/whatsapp-url-filter/start.sh` — supervisor for both processes
- `services/whatsapp-url-filter/README.md` — setup and first-link instructions

## Architecture decisions

- Telegram and WhatsApp run as separate processes because the libraries have independent event loops.
- The two processes communicate through local JSON files so the control surface can update filters without a network API.
- WhatsApp credentials and filter state stay on the persistent filesystem and are ignored by git.

## Product

The Telegram bot links a WhatsApp account, exports its groups, lets an operator select groups,
and removes matching URLs or keywords. Deletion requires the WhatsApp account to be a group admin.

## User preferences

None recorded.

## Gotchas

- Keep the `auth/` directory across restarts; deleting it logs the WhatsApp account out.
- Set `ALLOWED_USER_IDS` before sharing the Telegram bot with anyone.
- The WhatsApp account must be an admin in each selected group.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
