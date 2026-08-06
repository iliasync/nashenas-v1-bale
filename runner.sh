#!/bin/bash

APP_DIR="/home/jowkdwuy/nashenasV2"
PYTHON_BIN="/home/jowkdwuy/virtualenv/nashenasV2/3.12/bin/python"
MAIN_FILE="$APP_DIR/main.py"
PID_FILE="$APP_DIR/bot.pid"
LOG_FILE="$APP_DIR/bot.log"

cd "$APP_DIR" || exit 1

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        exit 0
    else
        rm -f "$PID_FILE"
    fi
fi

nohup "$PYTHON_BIN" "$MAIN_FILE" >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
sleep 2

NEW_PID=$(cat "$PID_FILE")
if kill -0 "$NEW_PID" 2>/dev/null; then
    echo "$(date) - Bot started with PID $NEW_PID" >> "$LOG_FILE"
else
    echo "$(date) - Failed to start bot" >> "$LOG_FILE"