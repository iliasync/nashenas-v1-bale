#!/bin/bash
set -eu

APP_DIR="/home/jowkdwuy/nashenasV2"
CRON_COMMAND="*/2 * * * * /usr/bin/env bash $APP_DIR/cpanel_auto_deploy.sh"
TMP_FILE=$(mktemp)
trap 'rm -f "$TMP_FILE"' EXIT

(crontab -l 2>/dev/null || true) | grep -Fv "$APP_DIR/cpanel_auto_deploy.sh" > "$TMP_FILE"
echo "$CRON_COMMAND" >> "$TMP_FILE"
crontab "$TMP_FILE"
/bin/chmod 700 "$APP_DIR/cpanel_auto_deploy.sh"

echo "Auto deploy installed. GitHub will be checked every 2 minutes."
echo "Log: $APP_DIR/auto_deploy.log"
