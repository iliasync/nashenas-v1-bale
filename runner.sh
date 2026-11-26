#!/bin/bash

APP_DIR="/home/jowkdwuy/nashenasV2"
PYTHON_BIN="/home/jowkdwuy/virtualenv/nashenasV2/3.12/bin/python"
MAIN_FILE="$APP_DIR/main.py"
PID_FILE="$APP_DIR/bot.pid"
HB_FILE="$APP_DIR/heartbeat.ts"
LOG_FILE="${BOT_LOG_FILE:-$APP_DIR/bot.log}"
MAX_LOG_BYTES=10485760

export PYTHONUNBUFFERED=1
cd "$APP_DIR" || exit 1

if [ -f "$APP_DIR/.env" ]; then
    set -a
    . "$APP_DIR/.env"
    set +a
fi

if [ -f "$LOG_FILE" ]; then
    LOG_SIZE=$(wc -c < "$LOG_FILE" 2>/dev/null || echo 0)
    if [ "$LOG_SIZE" -ge "$MAX_LOG_BYTES" ]; then
        mv -f "$LOG_FILE" "${LOG_FILE}.old" 2>/dev/null || :
        : > "$LOG_FILE" 2> /dev/null || true
    fi
fi

if [ -f "${LOG_FILE}.old" ]; then
    OLD_LOG_SIZE=$(wc -c < "${LOG_FILE}.old" 2>/dev/null || echo 0)
    if [ "$OLD_LOG_SIZE" -ge "$MAX_LOG_BYTES" ]; then
        : > "${LOG_FILE}.old" 2> /dev/null || true
    fi
fi

CRASH_REASON=""
if [ -f "$APP_DIR/restart.trigger" ]; then
    rm -f "$APP_DIR/restart.trigger"
    ACTION="restart"
else
    ACTION="${1:-watchdog}"
fi

if [ "$ACTION" = "watchdog" ]; then
    ALIVE=0
    if [ -f "$PID_FILE" ]; then
        PID=$(tr -dc '0-9' < "$PID_FILE" 2>/dev/null)
        if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
            ALIVE=1
        else
            CRASH_REASON="پروسس ربات (PID $PID) متوقف یا توسط سرور Kill شده بود"
            rm -f "$PID_FILE"
        fi
    else
        CRASH_REASON="فایل PID ربات وجود نداشت (ربات خاموش بود)"
    fi

    # Check heartbeat freeze (> 180s stale)
    if [ "$ALIVE" = "1" ] && [ -f "$HB_FILE" ]; then
        LAST_HB=$(tr -dc '0-9' < "$HB_FILE" 2>/dev/null || echo 0)
        NOW_TS=$(date +%s)
        if [ -n "$LAST_HB" ] && [ "$LAST_HB" -gt 0 ]; then
            DIFF=$((NOW_TS - LAST_HB))
            if [ "$DIFF" -gt 180 ]; then
                CRASH_REASON="ربات به مدت ${DIFF} ثانیه فریز شده بود (عدم ثبت Heartbeat یا قفل دیتابیس)"
                ACTION="restart"
            else
                exit 0
            fi
        else
            exit 0
        fi
    elif [ "$ALIVE" = "1" ]; then
        exit 0
    fi
fi

if [ "$ACTION" = "restart" ] || [ "$ACTION" = "force-restart" ] || [ "$ACTION" = "stop" ]; then
    if [ -f "$PID_FILE" ]; then
        OLD_PID=$(tr -dc '0-9' < "$PID_FILE" 2>/dev/null)
        if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
            kill "$OLD_PID" 2>/dev/null || true
            sleep 2
            kill -0 "$OLD_PID" 2>/dev/null && kill -9 "$OLD_PID" 2>/dev/null || true
        fi
        rm -f "$PID_FILE"
    fi
    pkill -u "$(id -u)" -f "(^|/)python.*nashenasV2/main" 2>/dev/null || true
    if [ "$ACTION" = "stop" ]; then
        exit 0
    fi
fi

date +%s > "$HB_FILE"
nohup "$PYTHON_BIN" "$MAIN_FILE" >> "$LOG_FILE" 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"
sleep 2

if kill -0 "$NEW_PID" 2>/dev/null; then
    echo "$(date) - Bot started with PID $NEW_PID" >> "$LOG_FILE"
    if [ -n "$CRASH_REASON" ]; then
        ERR_TAIL=$(tail -n 12 "$LOG_FILE" 2>/dev/null | head -c 900)
        BOT_TOK="${BOT_TOKEN:-1133133663:vcFyBB7XRfWwHYVk7dpLlQ8pACwb6mM3Bck}"
        MSG="⚠️ *هشدار مانیتورینگ nashenasV2*
📌 *علت:* ${CRASH_REASON}
✅ ربات خودکار با PID جدید \`${NEW_PID}\` روشن شد.

📝 *آخرین لاگ:*
\`\`\`
${ERR_TAIL}
\`\`\`"
        curl -s -m 4 -X POST "https://tapi.bale.ai/bot${BOT_TOK}/sendMessage" \
            -H "Content-Type: application/json" \
            -d "$(printf '{"chat_id":2065995342,"text":%s,"parse_mode":"Markdown"}' "$(python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' <<< "$MSG")")" >/dev/null 2>&1 || true
    fi
    exit 0
else
    echo "$(date) - Failed to start bot" >> "$LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
fi
