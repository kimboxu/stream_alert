#!/bin/bash

# Configuration
APP_SCRIPT="my_app.py"
LOG_FILE="my_app.log"

# Function to check if the app is running
check_app() {
    pgrep -f "python3 $APP_SCRIPT" > /dev/null
    return $?
}

# Function to start the app
start_app() {
    echo "Starting my_app..."
    nohup python3 $APP_SCRIPT >> $LOG_FILE 2>&1 &
    echo "my_app started with PID: $!"
}

# Function to kill the app
kill_app() {
    pid=$(pgrep -f "python3 $APP_SCRIPT")
    if [ -n "$pid" ]; then
        echo "Killing my_app (PID: $pid)..."
        kill -9 $pid
        echo "my_app killed"
        return 0
    else
        echo "my_app is not running"
        return 1
    fi
}

# Main script logic
case "$1" in
    start)
        if check_app; then
            echo "my_app is already running"
        else
            start_app
        fi
        ;;
    stop)
        kill_app
        ;;
    restart)
        if kill_app; then
            sleep 1
        fi
        start_app
        ;;
    status)
        if check_app; then
            pid=$(pgrep -f "python3 $APP_SCRIPT")
            echo "my_app is running with PID: $pid"
        else
            echo "my_app is not running"
        fi
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac

exit 0
