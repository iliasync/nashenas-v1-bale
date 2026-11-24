#!/bin/bash
set -u

REPO_DIR="/home/jowkdwuy/repositories/nashenasV2"
APP_DIR="/home/jowkdwuy/nashenasV2"
PYTHON_BIN="/home/jowkdwuy/virtualenv/nashenasV2/3.12/bin/python"
DEPLOYED_FILE="$APP_DIR/.deployed_sha"
LOCK_FILE="$APP_DIR/auto_deploy.lock"
# لاگ deploy روی فایل محلیِ چرخشی نگه‌داری می‌شود تا با محدودیت cPanel
# برای /dev/null مواجه نشویم و دیسک هم پر نشود.
LOG_FILE="${DEPLOY_LOG_FILE:-$APP_DIR/auto_deploy.log}"
MAX_LOG_BYTES=1048576
if ! (touch "$LOG_FILE" 2>/dev/null); then
    LOG_FILE="$APP_DIR/.deploy-runtime.log"
    touch "$LOG_FILE" 2>/dev/null || exit 1
fi
if [ -f "$LOG_FILE" ]; then
    LOG_SIZE=$(wc -c < "$LOG_FILE" 2>/dev/null || echo 0)
    if [ "$LOG_SIZE" -ge "$MAX_LOG_BYTES" ]; then
        mv -f "$LOG_FILE" "${LOG_FILE}.1" 2>/dev/null || :
        : > "$LOG_FILE" 2>/dev/null || true
    fi
fi

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $*" >> "$LOG_FILE"
}

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    exit 0
fi

if [ ! -d "$REPO_DIR/.git" ]; then
    log "Repository not found: $REPO_DIR"
    exit 1
fi

cd "$REPO_DIR" || exit 1
if ! /usr/bin/git fetch --quiet origin main; then
    log "git fetch failed"
    exit 1
fi

REMOTE_SHA=$(/usr/bin/git rev-parse origin/main) || exit 1
DEPLOYED_SHA=""
if [ -f "$DEPLOYED_FILE" ]; then
    DEPLOYED_SHA=$(tr -dc '0-9a-f' < "$DEPLOYED_FILE")
fi
if [ "$REMOTE_SHA" = "$DEPLOYED_SHA" ]; then
    if [ -f "$APP_DIR/restart.trigger" ]; then
        rm -f "$APP_DIR/restart.trigger"
        log "restart.trigger found; restarting bot"
        /bin/chmod 700 "$APP_DIR/runner.sh"
        /usr/bin/env bash "$APP_DIR/runner.sh"
    fi
    exit 0
fi

if ! /usr/bin/git checkout --quiet main || ! /usr/bin/git merge --ff-only --quiet origin/main; then
    log "fast-forward update failed; repository needs manual review"
    exit 1
fi

# از بازگرداندن نسخه قدیمی GitHub روی نسخه جدیدی که با ZIP نصب شده جلوگیری کن.
if ! grep -q '^BUILD_MARKER = ' "$REPO_DIR/config.py"; then
    log "refused to deploy legacy remote $REMOTE_SHA (BUILD_MARKER is missing)"
    exit 1
fi

if ! "$PYTHON_BIN" -c "
import os, shutil

src = '.'
dst = '$APP_DIR'
ignore_list = {'.git', '.env', 'bot.pid', 'bot.log', 'bot.sqlite3', 'bot.sqlite3-shm', 'bot.sqlite3-wal', '__pycache__', 'auto_deploy.log', 'auto_deploy.lock'}

for root, dirs, files in os.walk(src):
    rel_root = os.path.relpath(root, src)
    if rel_root == '.':
        dirs[:] = [d for d in dirs if d not in ignore_list]
        target_dir = dst
    else:
        parts = rel_root.split(os.sep)
        if any(p in ignore_list for p in parts):
            continue
        dirs[:] = [d for d in dirs if d not in ignore_list]
        target_dir = os.path.join(dst, rel_root)
        os.makedirs(target_dir, exist_ok=True)

    for f in files:
        if f in ignore_list or f.endswith('.pyc') or f.endswith('.deployed_sha'):
            continue
        s_file = os.path.join(root, f)
        d_file = os.path.join(target_dir, f)
        shutil.copy2(s_file, d_file)
"; then
    log "file sync failed for $REMOTE_SHA"
    exit 1
fi

if ! "$PYTHON_BIN" -m pip install --disable-pip-version-check -r "$APP_DIR/requirements.txt" >> "$LOG_FILE" 2>&1; then
    log "dependency installation failed for $REMOTE_SHA"
    exit 1
fi

/bin/chmod 700 "$APP_DIR/runner.sh" "$APP_DIR/cpanel_auto_deploy.sh"
if ! /usr/bin/env bash "$APP_DIR/runner.sh"; then
    log "bot restart failed for $REMOTE_SHA"
    exit 1
fi

echo "$REMOTE_SHA" > "$DEPLOYED_FILE"
log "successfully deployed $REMOTE_SHA"
