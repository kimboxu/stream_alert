#!/bin/bash

# Flutter 앱 실행 스크립트

APP_NAME="stream_alert_flutter"
MAIN_FILE="lib/main.dart"
LOG_FILE="flutter_app.log"

check_running() {
  pid=$(ps -ef | grep "flutter run" | grep "$MAIN_FILE" | grep -v grep | awk '{print $2}')
  echo "$pid"
}

start_app() {
  echo "Flutter 앱을 실행합니다..."
  nohup flutter run -d chrome -t $MAIN_FILE >> $LOG_FILE 2>&1 &
  echo "실행 로그는 $LOG_FILE 에 저장됩니다."
}

stop_app() {
  pid=$(check_running)
  if [ -n "$pid" ]; then
    echo "Flutter 앱을 종료합니다. (PID: $pid)"
    kill -9 $pid
  else
    echo "실행 중인 Flutter 앱이 없습니다."
  fi
}

case "$1" in
  start)
    start_app
    ;;
  stop)
    stop_app
    ;;
  restart)
    stop_app
    sleep 1
    start_app
    ;;
  status)
    pid=$(check_running)
    if [ -n "$pid" ]; then
      echo "Flutter 앱이 실행 중입니다. (PID: $pid)"
    else
      echo "Flutter 앱이 실행되고 있지 않습니다."
    fi
    ;;
  *)
    echo "사용법: $0 {start|stop|restart|status}"
    ;;
esac
