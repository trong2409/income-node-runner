#!/bin/bash
#
# Setup and start Income Node Runner:
#   - Fix runtime/ ownership for current user (if needed)
#   - Start web server
# Run from project dir: ./start.sh [--fix-only | --background | --stop]
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

RUNTIME_DIR="$SCRIPT_DIR/runtime"
PROXY_FILE="$SCRIPT_DIR/proxies.txt"
PROPERTIES_FILE="$SCRIPT_DIR/properties.conf"
PORT="${PORT:-8765}"

echo "[start.sh] Project: $SCRIPT_DIR"
echo ""


# --- Fix runtime ownership for current user ---
fix_runtime_permission() {
  if [ -d "$RUNTIME_DIR" ]; then
    if [ ! -w "$RUNTIME_DIR" ]; then
      echo "[start.sh] Fixing runtime/ ownership (chown $(whoami))..."
      sudo chown -R "$(whoami):" "$RUNTIME_DIR"
      echo "[start.sh] runtime/ ownership fixed."
    else
      echo "[start.sh] runtime/ is already writable."
    fi
  else
    echo "[start.sh] Creating runtime/..."
    mkdir -p "$RUNTIME_DIR"
    echo "[start.sh] runtime/ ready."
  fi
}

# --- Start web server ---
start_server() {
  if ! command -v python3 &>/dev/null; then
    echo "[start.sh] Error: python3 required."
    exit 1
  fi
  echo "[start.sh] Starting web server http://127.0.0.1:${PORT}"
  echo ""
  export PORT
  exec python3 "$SCRIPT_DIR/web/server.py"
}

# --- Migrate: backfill created_at for nodes and proxy-meta.json ---
run_migrate() {
  if [ ! -d "$RUNTIME_DIR" ]; then
    echo "[start.sh] No runtime/ directory found. Nothing to migrate."
    return
  fi
  echo "[start.sh] Running migration..."
  python3 "$SCRIPT_DIR/web/node_meta.py" migrate "$RUNTIME_DIR"
  echo "[start.sh] Migration complete."
}

# --- Main ---
case "${1:-}" in
  --fix-only)
    fix_runtime_permission
    echo ""
    echo "Done (permissions only). To start server: ./start.sh"
    ;;
  --migrate)
    fix_runtime_permission
    echo ""
    run_migrate
    ;;
  --background)
    fix_runtime_permission
    echo ""
    nohup python3 "$SCRIPT_DIR/web/server.py" </dev/null >"$SCRIPT_DIR/web/server.log" 2>&1 &
    echo "[start.sh] Server running in background. PID: $!"
    echo "[start.sh] Log: $SCRIPT_DIR/web/server.log"
    echo "[start.sh] Open: http://127.0.0.1:${PORT}"
    ;;
  --stop)
    # Only kill this project's server (full path), not other services on the host
    if pkill -f "$SCRIPT_DIR/web/server.py"; then
      echo "[start.sh] Background web server stopped."
    else
      echo "[start.sh] No background web server process found."
      exit 1
    fi
    ;;
  *)
    fix_runtime_permission
    echo ""
    start_server
    ;;
esac
