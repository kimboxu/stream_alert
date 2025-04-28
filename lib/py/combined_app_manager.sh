#!/bin/bash

# Configuration
APP_SCRIPT="combined_app.py"
LOG_FILE="combined_app.log"

# Function to check if app is running
check_app() {
    pgrep -f "python3 $APP_SCRIPT" > /dev/null
    return $?
}

# Function to start the app
start_app() {
    echo "Starting combined app..."
    nohup python3 $APP_SCRIPT >> $LOG_FILE 2>&1 &
    echo "Combined app started with PID: $!"
}

# Function to kill the app
kill_app() {
    pid=$(pgrep -f "python3 $APP_SCRIPT")
    if [ -n "$pid" ]; then
        echo "Stopping combined app (PID: $pid)..."
        kill $pid  # 우선 정상 종료 시도(SIGTERM)
        sleep 3
        if ps -p $pid > /dev/null; then
            echo "프로세스가 아직 종료되지 않았으므로 강제 종료합니다. (kill -9)"
            kill -9 $pid
        fi
        echo "Combined app stopped"
        return 0
    else
        echo "Combined app is not running"
        return 1
    fi
}

# Main script logic
case "$1" in
    start)
        if check_app; then
            echo "Combined app is already running"
        else
            start_app
        fi
        ;;
    stop)
        kill_app
        ;;
    restart)
        if kill_app; then
            # Small delay to ensure process is fully terminated
            sleep 1
        fi
        start_app
        ;;
    status)
        if check_app; then
            pid=$(pgrep -f "python3 $APP_SCRIPT")
            echo "Combined app is running with PID: $pid"
        else
            echo "Combined app is not running"
        fi
        ;;
    logs)
        echo "Showing last 50 lines of log file and following..."
        tail -n 50 -f $LOG_FILE
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        exit 1
        ;;
esac

exit 0