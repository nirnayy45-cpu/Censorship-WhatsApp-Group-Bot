#!/usr/bin/env bash
set -euo pipefail

SERVICE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$SERVICE_DIR/auth"

if [[ -z "${BOT_TOKEN:-}" ]]; then
  echo "BOT_TOKEN is not configured." >&2
  exit 1
fi

cleanup() {
  kill "${TELEGRAM_PID:-}" "${WHATSAPP_PID:-}" 2>/dev/null || true
  wait "${TELEGRAM_PID:-}" "${WHATSAPP_PID:-}" 2>/dev/null || true
}
shutdown_requested=0
shutdown() {
  shutdown_requested=1
  cleanup
}
trap shutdown INT TERM

start_children() {
  python "$SERVICE_DIR/url_filter_bot.py" &
  TELEGRAM_PID=$!

  node "$SERVICE_DIR/wa-filter-bridge.js" &
  WHATSAPP_PID=$!

  echo "Telegram PID: $TELEGRAM_PID"
  echo "WhatsApp PID: $WHATSAPP_PID"
}

echo "WhatsApp URL filter service started."
start_children

while [[ "$shutdown_requested" -eq 0 ]]; do
  wait -n "$TELEGRAM_PID" "$WHATSAPP_PID" || true
  [[ "$shutdown_requested" -eq 1 ]] && break

  echo "A bot process stopped; restarting both processes in 3 seconds."
  kill "$TELEGRAM_PID" "$WHATSAPP_PID" 2>/dev/null || true
  wait "$TELEGRAM_PID" "$WHATSAPP_PID" 2>/dev/null || true
  sleep 3
  start_children
done

cleanup