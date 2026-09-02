#!/bin/bash

# ==========================================
# Combined App Manager
# 자동 재시작(Watchdog) 기능 포함
# ==========================================

APP_SCRIPT="combined_app.py"
LOG_FILE="combined_app.log"
WATCHDOG_LOG="combined_app_watchdog.log"
PID_FILE="combined_app_watchdog.pid"
RESTART_DELAY=5

watchdog_loop() {
    while true; do
        echo "$(date '+%Y-%m-%d %H:%M:%S') Combined app starting..." >> "$WATCHDOG_LOG"

        python3 -u "$APP_SCRIPT" >> "$LOG_FILE" 2>&1
        EXIT_CODE=$?

        echo "$(date '+%Y-%m-%d %H:%M:%S') Combined app stopped. Exit code: $EXIT_CODE" >> "$WATCHDOG_LOG"
        echo "$(date '+%Y-%m-%d %H:%M:%S') Restarting in ${RESTART_DELAY} seconds..." >> "$WATCHDOG_LOG"

        sleep "$RESTART_DELAY"
    done
}

check_app() {
    if [ -f "$PID_FILE" ]; then
        WATCHDOG_PID=$(cat "$PID_FILE")

        if ps -p "$WATCHDOG_PID" > /dev/null 2>&1; then
            return 0
        fi

        rm -f "$PID_FILE"
    fi

    return 1
}

start_app() {
    if check_app; then
        echo "Combined app is already running."
        echo "Watchdog PID: $(cat "$PID_FILE")"
        return 0
    fi

    echo "Starting combined app watchdog..."

    nohup "$0" _watchdog > /dev/null 2>&1 &
    WATCHDOG_PID=$!

    echo "$WATCHDOG_PID" > "$PID_FILE"

    sleep 1

    if ps -p "$WATCHDOG_PID" > /dev/null 2>&1; then
        echo "Combined app watchdog started."
        echo "Watchdog PID: $WATCHDOG_PID"
    else
        echo "Failed to start combined app watchdog."
        rm -f "$PID_FILE"
        return 1
    fi
}

stop_app() {
    if ! check_app; then
        echo "Combined app is not running."
        return 1
    fi

    WATCHDOG_PID=$(cat "$PID_FILE")

    echo "Stopping watchdog (PID: $WATCHDOG_PID)..."
    kill "$WATCHDOG_PID" 2>/dev/null

    sleep 2

    APP_PIDS=$(pgrep -f "python3 -u $APP_SCRIPT")

    if [ -n "$APP_PIDS" ]; then
        echo "Stopping remaining combined app process(es): $APP_PIDS"
        kill $APP_PIDS 2>/dev/null

        sleep 3

        APP_PIDS=$(pgrep -f "python3 -u $APP_SCRIPT")

        if [ -n "$APP_PIDS" ]; then
            echo "Force stopping remaining combined app process(es)..."
            kill -9 $APP_PIDS 2>/dev/null
        fi
    fi

    rm -f "$PID_FILE"
    echo "Combined app stopped."
}

status_app() {
    if check_app; then
        WATCHDOG_PID=$(cat "$PID_FILE")

        echo "Combined app watchdog is running."
        echo "Watchdog PID: $WATCHDOG_PID"

        APP_PIDS=$(pgrep -f "python3 -u $APP_SCRIPT")

        if [ -n "$APP_PIDS" ]; then
            echo "Python app PID(s): $APP_PIDS"
        else
            echo "Python app is currently restarting or not running."
        fi
    else
        echo "Combined app is not running."
    fi
}

case "$1" in
    _watchdog)
        watchdog_loop
        ;;

    start)
        start_app
        ;;

    stop)
        stop_app
        ;;

    restart)
        stop_app
        sleep 2
        start_app
        ;;

    status)
        status_app
        ;;

    logs)
        echo "Showing application log..."
        tail -n 50 -f "$LOG_FILE"
        ;;

    watchdog-logs)
        echo "Showing watchdog log..."
        tail -n 50 -f "$WATCHDOG_LOG"
        ;;

    *)
        echo "Usage: $0 {start|stop|restart|status|logs|watchdog-logs}"
        exit 1
        ;;
esac

exit 0
