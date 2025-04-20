#!/bin/bash

# Configuration
BOT_SCRIPT="discordbot.py"
LOG_FILE="discordbot.log"

# Function to check if bot is running
check_bot() {
    pgrep -f "python3 $BOT_SCRIPT" > /dev/null
    return $?
}

# Function to start the bot
start_bot() {
    echo "Starting Discord bot..."
    nohup python3 $BOT_SCRIPT >> $LOG_FILE 2>&1 &
    echo "Discord bot started with PID: $!"
}

# Function to kill the bot
kill_bot() {
    pid=$(pgrep -f "python3 $BOT_SCRIPT")
    if [ -n "$pid" ]; then
        echo "Killing Discord bot (PID: $pid)..."
        kill -9 $pid
        echo "Discord bot killed"
        return 0
    else
        echo "Discord bot is not running"
        return 1
    fi
}

# Main script logic
case "$1" in
    start)
        if check_bot; then
            echo "Discord bot is already running"
        else
            start_bot
        fi
        ;;
    stop)
        kill_bot
        ;;
    restart)
        if kill_bot; then
            # Small delay to ensure process is fully terminated
            sleep 1
        fi
        start_bot
        ;;
    status)
        if check_bot; then
            pid=$(pgrep -f "python3 $BOT_SCRIPT")
            echo "Discord bot is running with PID: $pid"
        else
            echo "Discord bot is not running"
        fi
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac

exit 0