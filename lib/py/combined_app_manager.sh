#!/bin/bash

# ==========================================

# Configuration

# ==========================================

APP_SCRIPT="combined_app.py"
LOG_FILE="combined_app.log"
WATCHDOG_LOG="combined_app_watchdog.log"
PID_FILE="combined_app_watchdog.pid"

RESTART_DELAY=5

# ==========================================

# Watchdog 실행

# ==========================================

watchdog_loop() {

```
while true; do

    echo "$(date '+%Y-%m-%d %H:%M:%S') Combined app starting..." >> "$WATCHDOG_LOG"

    # Python 프로그램 실행
    python3 -u "$APP_SCRIPT" >> "$LOG_FILE" 2>&1

    EXIT_CODE=$?

    echo "$(date '+%Y-%m-%d %H:%M:%S') Combined app stopped. Exit code: $EXIT_CODE" >> "$WATCHDOG_LOG"

    echo "$(date '+%Y-%m-%d %H:%M:%S') Restarting in $RESTART_DELAY seconds..." >> "$WATCHDOG_LOG"

    sleep "$RESTART_DELAY"

done
```

}

# ==========================================

# 앱 실행 여부 확인

# ==========================================

check_app() {

```
if [ -f "$PID_FILE" ]; then

    WATCHDOG_PID=$(cat "$PID_FILE")

    if ps -p "$WATCHDOG_PID" > /dev/null 2>&1; then
        return 0
    fi

fi

return 1
```

}

# ==========================================

# 프로그램 시작

# ==========================================

start_app() {

```
if check_app; then

    echo "Combined app is already running."
    echo "Watchdog PID: $(cat "$PID_FILE")"

    return 0

fi


echo "Starting combined app watchdog..."

nohup bash -c "
    echo \$\$ > '$PID_FILE'
    watchdog_loop() {
        while true; do

            echo \"\$(date '+%Y-%m-%d %H:%M:%S') Combined app starting...\" >> '$WATCHDOG_LOG'

            python3 -u '$APP_SCRIPT' >> '$LOG_FILE' 2>&1

            EXIT_CODE=\$?

            echo \"\$(date '+%Y-%m-%d %H:%M:%S') Combined app stopped. Exit code: \$EXIT_CODE\" >> '$WATCHDOG_LOG'

            echo \"\$(date '+%Y-%m-%d %H:%M:%S') Restarting in $RESTART_DELAY seconds...\" >> '$WATCHDOG_LOG'

            sleep '$RESTART_DELAY'

        done
    }

    watchdog_loop
" > /dev/null 2>&1 &


sleep 1


echo $! > "$PID_FILE"


echo "Combined app watchdog started."
echo "Watchdog PID: $(cat "$PID_FILE")"
```

}

# ==========================================

# 프로그램 종료

# ==========================================

stop_app() {

```
if ! check_app; then

    echo "Combined app is not running."

    rm -f "$PID_FILE"

    return 1

fi


WATCHDOG_PID=$(cat "$PID_FILE")


echo "Stopping watchdog (PID: $WATCHDOG_PID)..."

# watchdog 종료
kill "$WATCHDOG_PID" 2>/dev/null


# Python 프로그램도 종료
sleep 2

APP_PID=$(pgrep -f "python3 -u $APP_SCRIPT")

if [ -n "$APP_PID" ]; then

    echo "Stopping combined app (PID: $APP_PID)..."

    kill $APP_PID 2>/dev/null

    sleep 3


    if ps -p "$APP_PID" > /dev/null 2>&1; then

        echo "Force stopping combined app..."

        kill -9 "$APP_PID"

    fi

fi


rm -f "$PID_FILE"


echo "Combined app stopped."
```

}

# ==========================================

# 메인 명령 처리

# ==========================================

case "$1" in

```
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

    if check_app; then

        echo "Combined app is running."
        echo "Watchdog PID: $(cat "$PID_FILE")"

    else

        echo "Combined app is not running."

    fi

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
```

esac

exit 0
