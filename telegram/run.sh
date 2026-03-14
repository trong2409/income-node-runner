#!/bin/bash
# Run the Telegram bot (foreground or background)
# Usage:
#   ./run.sh            - run in foreground
#   ./run.sh --background  - run in background (logs to bot.log)
#   ./run.sh --stop     - stop background process
#   ./run.sh --status   - check if running

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
PID_FILE="$SCRIPT_DIR/bot.pid"
LOG_FILE="$SCRIPT_DIR/bot.log"

setup_venv() {
  if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
  fi
  source "$VENV_DIR/bin/activate"
  if ! python3 -c "import telegram" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install -r "$SCRIPT_DIR/requirements.txt" --quiet
  fi
}

check_config() {
  if [ ! -f "$SCRIPT_DIR/config.json" ]; then
    echo "ERROR: config.json not found."
    echo "  cp $SCRIPT_DIR/config.example.json $SCRIPT_DIR/config.json"
    echo "  Then fill in bot_token and allowed_users."
    exit 1
  fi
}

case "${1:-}" in
  --background)
    check_config
    setup_venv
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "Bot is already running (PID $(cat "$PID_FILE"))."
      exit 0
    fi
    source "$VENV_DIR/bin/activate"
    nohup python3 "$SCRIPT_DIR/bot.py" >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "Bot started in background (PID $!). Logs: $LOG_FILE"
    ;;
  --stop)
    if [ -f "$PID_FILE" ]; then
      PID=$(cat "$PID_FILE")
      if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        rm -f "$PID_FILE"
        echo "Bot stopped (PID $PID)."
      else
        echo "Bot not running (stale PID file)."
        rm -f "$PID_FILE"
      fi
    else
      echo "Bot not running."
    fi
    ;;
  --status)
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "Bot is running (PID $(cat "$PID_FILE"))."
    else
      echo "Bot is NOT running."
    fi
    ;;
  *)
    check_config
    setup_venv
    source "$VENV_DIR/bin/activate"
    python3 "$SCRIPT_DIR/bot.py"
    ;;
esac
