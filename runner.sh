#!/bin/bash

APP_DIR="/home/jowkdwuy/nashenasV2"
SOURCE_REPO_DIR="/home/jowkdwuy/repositories/nashenasV2"
PYTHON_BIN="/home/jowkdwuy/virtualenv/nashenasV2/3.12/bin/python"
MAIN_FILE="$APP_DIR/main.py"
PID_FILE="$APP_DIR/bot.pid"
# خروجی دائمیِ بات روی هاست ذخیره نمی‌شود تا دیسک پر نشود.
LOG_FILE="/dev/null"

cd "$APP_DIR" || exit 1

if [ -f "$APP_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$APP_DIR/.env"
    set +a
fi

OLD_PID=""
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(tr -dc '0-9' < "$PID_FILE")
fi

# همه نمونه‌های main.py متعلق به همین پوشه و همین کاربر را جمع می‌کنیم؛ وجود
# چند نمونه قدیمی باعث می‌شود بخشی از پیام‌ها به کد قدیمی برسد.
CANDIDATE_PIDS="$OLD_PID"
if command -v pgrep >/dev/null 2>&1; then
    FOUND_PIDS=$(pgrep -u "$(id -u)" -f '(^|/)main\.py([[:space:]]|$)' 2>/dev/null || true)
    CANDIDATE_PIDS="$CANDIDATE_PIDS $FOUND_PIDS"
fi

VALID_PIDS=""
for PID in $CANDIDATE_PIDS; do
    case "$PID" in *[!0-9]*|'') continue ;; esac
    kill -0 "$PID" 2>/dev/null || continue
    OLD_CMD=$(ps -p "$PID" -o args= 2>/dev/null)
    OLD_CWD=$(readlink "/proc/$PID/cwd" 2>/dev/null || true)
    case "$OLD_CMD" in
        *"$MAIN_FILE"*) VALID_PIDS="$VALID_PIDS $PID" ;;
        *"$SOURCE_REPO_DIR/main.py"*) VALID_PIDS="$VALID_PIDS $PID" ;;
        *"main.py"*)
            if [ "$OLD_CWD" = "$APP_DIR" ] || [ "$OLD_CWD" = "$SOURCE_REPO_DIR" ]; then
                VALID_PIDS="$VALID_PIDS $PID"
            fi
            ;;
        *)
            echo "$(date) - Ignored unrelated PID $PID: $OLD_CMD" >> "$LOG_FILE"
            ;;
    esac
done

VALID_PIDS=$(printf '%s\n' $VALID_PIDS | awk 'NF && !seen[$1]++ {print $1}')
if [ -n "$VALID_PIDS" ]; then
    echo "$(date) - Stopping old bot PID(s): $(echo "$VALID_PIDS" | tr '\n' ' ')" >> "$LOG_FILE"
    kill $VALID_PIDS 2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        STILL_RUNNING=""
        for PID in $VALID_PIDS; do
            kill -0 "$PID" 2>/dev/null && STILL_RUNNING="$STILL_RUNNING $PID"
        done
        [ -z "$STILL_RUNNING" ] && break
        sleep 1
    done
    for PID in $VALID_PIDS; do
        kill -0 "$PID" 2>/dev/null && kill -KILL "$PID" 2>/dev/null || true
    done
fi
rm -f "$PID_FILE"

nohup "$PYTHON_BIN" "$MAIN_FILE" >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
sleep 2

NEW_PID=$(cat "$PID_FILE")
if kill -0 "$NEW_PID" 2>/dev/null; then
    echo "$(date) - Bot started with PID $NEW_PID" >> "$LOG_FILE"
else
    echo "$(date) - Failed to start bot" >> "$LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
fi
