#!/bin/bash
set -eu

APP_DIR="/home/jowkdwuy/nashenasV2"
REPO_DIR="/home/jowkdwuy/repositories/nashenasV2"
CRON_COMMAND="*/2 * * * * /usr/bin/env bash $APP_DIR/cpanel_auto_deploy.sh"
TMP_FILE=$(mktemp)
trap 'rm -f "$TMP_FILE"' EXIT

(crontab -l 2>/dev/null || true) | grep -Fv "$APP_DIR/cpanel_auto_deploy.sh" > "$TMP_FILE"
echo "$CRON_COMMAND" >> "$TMP_FILE"
crontab "$TMP_FILE"
/bin/chmod 700 "$APP_DIR/cpanel_auto_deploy.sh"

# هنگام نصب از طریق ZIP، نسخه GitHub ممکن است هنوز قدیمی باشد. ثبت SHA فعلی
# remote مانع می‌شود cron همان نسخه قدیمی را روی کد تازه ZIP برگرداند.
if [ ! -f "$APP_DIR/.deployed_sha" ] && [ -d "$REPO_DIR/.git" ]; then
    /usr/bin/git -C "$REPO_DIR" fetch --quiet origin main || true
    /usr/bin/git -C "$REPO_DIR" rev-parse origin/main > "$APP_DIR/.deployed_sha" 2>/dev/null || true
fi

echo "Auto deploy installed. GitHub will be checked every 2 minutes."
echo "Log: $APP_DIR/auto_deploy.log"
