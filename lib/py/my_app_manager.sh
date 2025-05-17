#!/bin/bash

# Configuration
APP_MODULE="my_app:app"  # flask app 모듈:객체
LOG_FILE="my_app.log"

# Function to check if the app is running
check_app() {
    pgrep -f "gunicorn .* $APP_MODULE" > /dev/null
    return $?
}

# Function to start the app using gunicorn
start_app() {
    echo "Starting my_app using gunicorn..."
    nohup gunicorn -w 2 -b 0.0.0.0:5000 $APP_MODULE >> $LOG_FILE 2>&1 &
    echo "my_app started with PID: $!"
}

# Function to kill the app
kill_app() {
    pid=$(pgrep -f "gunicorn .* $APP_MODULE")
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
            pid=$(pgrep -f "gunicorn .* $APP_MODULE")
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
