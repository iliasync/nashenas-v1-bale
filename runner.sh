#!/bin/bash

APP_DIR="/home/jowkdwuy/nashenasV2"
PYTHON_BIN="/home/jowkdwuy/virtualenv/nashenasV2/3.12/bin/python"
MAIN_FILE="$APP_DIR/main.py"
PID_FILE="$APP_DIR/bot.pid"
LOG_FILE="$APP_DIR/bot.log"

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

# در اولین دیپلوی ممکن است bot.pid قدیمی توسط Git حذف شده باشد؛ در این حالت
# پردازش دقیق همین پروژه و همین کاربر cPanel را پیدا می‌کنیم.
if [ -z "$OLD_PID" ] && command -v pgrep >/dev/null 2>&1; then
    OLD_PID=$(pgrep -u "$(id -u)" -f "^$PYTHON_BIN $MAIN_FILE$" | head -n 1)
fi

if [ -n "$OLD_PID" ]; then
    if kill -0 "$OLD_PID" 2>/dev/null; then
        # فقط پردازشی را می‌بندیم که واقعاً main.py همین پروژه باشد.
        OLD_CMD=$(ps -p "$OLD_PID" -o args= 2>/dev/null)
        case "$OLD_CMD" in
            *"$PYTHON_BIN"*"$MAIN_FILE"*)
                kill "$OLD_PID"
                for _ in 1 2 3 4 5 6 7 8 9 10; do
                    kill -0 "$OLD_PID" 2>/dev/null || break
                    sleep 1
                done
                if kill -0 "$OLD_PID" 2>/dev/null; then
                    kill -KILL "$OLD_PID"
                fi
                ;;
            *)
                echo "$(date) - Refused to stop unrelated PID $OLD_PID: $OLD_CMD" >> "$LOG_FILE"
                exit 1
                ;;
        esac
    fi
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
