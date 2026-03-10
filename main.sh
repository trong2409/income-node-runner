#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE_DIR="$SCRIPT_DIR/source"
PROXY_FILE="$SCRIPT_DIR/proxies.txt"
PROPERTIES_FILE="$SCRIPT_DIR/properties.conf"
RUNTIME_DIR="$SCRIPT_DIR/runtime"

# Normalize proxy: trim, single line (for consistent storage and web migration)
normalize_proxy() {
  echo "$1" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | tr -d '\n\r'
}

get_node_id() {
  local NORM
  NORM=$(normalize_proxy "$1")
  echo -n "$NORM" | sha256sum | cut -c1-8
}

# Return 0 if normalized proxy already in PROXY_FILE
proxy_exists_in_file() {
  local NORM="$1"
  [[ -z "$NORM" ]] && return 1
  [[ ! -f "$PROXY_FILE" ]] && return 1
  while IFS= read -r line; do
    local T
    T=$(normalize_proxy "$line")
    [[ "$T" == \#* || -z "$T" ]] && continue
    if [[ "$T" == "$NORM" ]]; then
      return 0
    fi
  done < "$PROXY_FILE"
  return 1
}

# Append one proxy line to PROXY_FILE (no duplicate). Preserves header comment if first line is #
ensure_proxy_file_header() {
  if [[ ! -f "$PROXY_FILE" ]]; then
    echo "# Add one proxy per line. Format: protocol://user:pass@host:port" > "$PROXY_FILE"
  fi
}

append_proxy_to_file() {
  local NORM="$1"
  [[ -z "$NORM" ]] && return 1
  proxy_exists_in_file "$NORM" && return 0
  ensure_proxy_file_header
  echo "$NORM" >> "$PROXY_FILE"
  return 0
}

run_node() {
  local ACTION="$1"
  local INCOME_ARG="$2"
  local NODE_ID="$3"
  local NODE_DIR="$RUNTIME_DIR/node-${NODE_ID}"

  if [ ! -d "$NODE_DIR" ]; then
    echo "  [SKIP] node-${NODE_ID} not found"
    return 1
  fi

  if [ ! -f "$NODE_DIR/internetIncome.sh" ]; then
    echo "  [SKIP] internetIncome.sh not found in node-${NODE_ID}"
    return 1
  fi

  echo "  ${ACTION} node-${NODE_ID}..."
  (cd "$NODE_DIR" && sudo bash internetIncome.sh "$INCOME_ARG")
  echo "  -> node-${NODE_ID} done"

  if [ "$ACTION" == "start" ]; then
    local EARNAPP_FILE="$NODE_DIR/earnapp.txt"
    if [ -f "$EARNAPP_FILE" ]; then
      local CONTENT=$(cat "$EARNAPP_FILE" | tr -d '\n')
      echo "  [earnapp] node-${NODE_ID} : $CONTENT"
      local OUTPUT_FILE="$SCRIPT_DIR/earnapp-links.txt"
      sed -i "/^node-${NODE_ID} :/d" "$OUTPUT_FILE" 2>/dev/null
      echo "node-${NODE_ID} : $CONTENT" >> "$OUTPUT_FILE"
    fi
    python3 "$SCRIPT_DIR/web/node_meta.py" write "$NODE_DIR" active 2>/dev/null || true
  else
    python3 "$SCRIPT_DIR/web/node_meta.py" write "$NODE_DIR" inactive 2>/dev/null || true
  fi
}

run_nodes() {
  local ACTION="$1"
  local INCOME_ARG="$2"
  shift 2
  local NODES=("$@")

  if [ ${#NODES[@]} -eq 0 ]; then
    echo "Error: no node IDs provided"
    echo "Usage: $0 --${ACTION}-node <id> [id2 id3 ...]  (use --list-nodes to see IDs)"
    exit 1
  fi

  echo "${ACTION^} ${#NODES[@]} node(s)..."
  local count=0
  for NODE_ID in "${NODES[@]}"; do
    if run_node "$ACTION" "$INCOME_ARG" "$NODE_ID"; then
      count=$((count + 1))
    fi
  done

  echo "Done! ${ACTION^} $count node(s)."
}

ensure_runtime_writable() {
  mkdir -p "$RUNTIME_DIR"
  if ! [ -w "$RUNTIME_DIR" ]; then
    echo "Error: Cannot write to $RUNTIME_DIR (permission denied)."
    echo "  If runtime/ was created by root (e.g. when using sudo), run:"
    echo "  sudo chown -R \$(whoami) \"$RUNTIME_DIR\""
    exit 1
  fi
}

get_node_ids() {
  for NODE_DIR in "$RUNTIME_DIR"/node-*; do
    if [ -d "$NODE_DIR" ]; then
      basename "$NODE_DIR" | sed 's/^node-//'
    fi
  done | sort
}

run_all_nodes() {
  local ACTION="$1"
  local INCOME_ARG="$2"

  local count=0
  for NODE_ID in $(get_node_ids); do
    if run_node "$ACTION" "$INCOME_ARG" "$NODE_ID"; then
      count=$((count + 1))
    fi
  done

  if [ $count -eq 0 ]; then
    echo "No node directories found. Run --setup-node first."
  else
    echo "Done! ${ACTION^} $count node(s)."
  fi
}

create_node() {
  local NODE_ID="$1"
  local PROXY="$2"
  local NODE_DIR="$RUNTIME_DIR/node-${NODE_ID}"

  ensure_runtime_writable

  echo "Creating node-${NODE_ID} with proxy: $PROXY"

  rm -rf "$NODE_DIR"
  cp -r "$SOURCE_DIR" "$NODE_DIR"
  rm -rf "$NODE_DIR/.git"

  cat > "$NODE_DIR/proxies.txt" << EOF
$PROXY
EOF

  if [ -f "$PROPERTIES_FILE" ]; then
    cp "$PROPERTIES_FILE" "$NODE_DIR/properties.conf"
  fi

  sed -i "s/^DEVICE_NAME=.*/DEVICE_NAME='node-${NODE_ID}'/" "$NODE_DIR/properties.conf"

  python3 "$SCRIPT_DIR/web/node_meta.py" write "$NODE_DIR" inactive 2>/dev/null || true

  echo "  -> node-${NODE_ID} created"
}

setup_nodes() {
  if [ ! -d "$SOURCE_DIR" ]; then
    echo "Error: source directory not found at $SOURCE_DIR"
    exit 1
  fi

  if [ ! -f "$PROXY_FILE" ]; then
    echo "Error: proxies.txt not found at $PROXY_FILE"
    exit 1
  fi

  local RAW
  mapfile -t RAW < <(grep -v '^#' "$PROXY_FILE" 2>/dev/null | grep -v '^[[:space:]]*$')
  PROXIES=()
  for p in "${RAW[@]:-}"; do
    [[ -z "$p" ]] && continue
    PROXIES+=("$(normalize_proxy "$p")")
  done

  if [ ${#PROXIES[@]} -eq 0 ]; then
    echo "No proxies found in $PROXY_FILE"
    exit 1
  fi

  echo "Found ${#PROXIES[@]} proxies"

  mkdir -p "$RUNTIME_DIR"

  for PROXY in "${PROXIES[@]}"; do
    local NODE_ID
    NODE_ID=$(get_node_id "$PROXY")
    create_node "$NODE_ID" "$PROXY"
  done

  echo "Done! Created ${#PROXIES[@]} nodes."
}

add_proxy() {
  shift
  local NEW_PROXIES=("$@")

  if [ ${#NEW_PROXIES[@]} -eq 0 ]; then
    echo "Error: no proxy provided"
    echo "Usage: $0 --add-proxy <proxy> [proxy2 proxy3 ...]"
    exit 1
  fi

  if [ ! -d "$SOURCE_DIR" ]; then
    echo "Error: source directory not found at $SOURCE_DIR"
    exit 1
  fi

  mkdir -p "$RUNTIME_DIR"

  local count=0
  for PROXY in "${NEW_PROXIES[@]}"; do
    local NORM
    NORM=$(normalize_proxy "$PROXY")
    [[ -z "$NORM" || "$NORM" == \#* ]] && continue
    append_proxy_to_file "$NORM"
    local NODE_ID
    NODE_ID=$(get_node_id "$NORM")
    create_node "$NODE_ID" "$NORM"
    count=$((count + 1))
  done

  echo "Done! Added $count proxy(s) and created $count node(s)."
}

update_properties() {
  if [ ! -f "$PROPERTIES_FILE" ]; then
    echo "Error: properties.conf not found at $PROPERTIES_FILE"
    exit 1
  fi

  local count=0
  for NODE_ID in $(get_node_ids); do
    local NODE_DIR="$RUNTIME_DIR/node-${NODE_ID}"
    cp "$PROPERTIES_FILE" "$NODE_DIR/properties.conf"
    echo "  Updated node-${NODE_ID}/properties.conf"
    count=$((count + 1))
  done

  if [ $count -eq 0 ]; then
    echo "No node directories found. Run --setup-node first."
  else
    echo "Done! Updated properties.conf in $count node(s)."
  fi
}

collect_earnapp() {
  local OUTPUT_JSON="$SCRIPT_DIR/earnapp-links.json"
  local OUTPUT_TXT="$SCRIPT_DIR/earnapp-links.txt"
  local TMP_DATA="$SCRIPT_DIR/.earnapp-collect-tmp"

  > "$TMP_DATA"
  local count=0
  for NODE_ID in $(get_node_ids); do
    local NODE_DIR="$RUNTIME_DIR/node-${NODE_ID}"
    local EARNAPP_FILE="$NODE_DIR/earnapp.txt"
    if [ -f "$EARNAPP_FILE" ]; then
      local CONTENT
      CONTENT=$(cat "$EARNAPP_FILE" | tr -d '\n\r')
      local PROXY
      PROXY=$(grep -v '^#' "$NODE_DIR/proxies.txt" 2>/dev/null | grep -v '^[[:space:]]*$' | head -1)
      printf '%s\n' "$NODE_ID" "$PROXY" "$CONTENT" >> "$TMP_DATA"
      count=$((count + 1))
    else
      echo "  [SKIP] node-${NODE_ID} — earnapp.txt not found"
    fi
  done

  if [ $count -eq 0 ]; then
    echo "No earnapp.txt found in any node."
    rm -f "$OUTPUT_JSON" "$OUTPUT_TXT" "$TMP_DATA"
  else
    python3 -c "
import json
items = []
with open('$TMP_DATA') as f:
    lines = [l.rstrip('\n\r') for l in f.readlines()]
i = 0
while i + 2 < len(lines):
    items.append({
        'node_id': lines[i],
        'proxy': lines[i+1],
        'earnapp_link': lines[i+2]
    })
    i += 3
with open('$OUTPUT_JSON', 'w') as f:
    json.dump(items, f, ensure_ascii=False, indent=2)
" 2>/dev/null
    rm -f "$TMP_DATA"
    > "$OUTPUT_TXT"
    for NODE_ID in $(get_node_ids); do
      local NODE_DIR="$RUNTIME_DIR/node-${NODE_ID}"
      local EARNAPP_FILE="$NODE_DIR/earnapp.txt"
      if [ -f "$EARNAPP_FILE" ]; then
        local CONTENT
        CONTENT=$(cat "$EARNAPP_FILE" | tr -d '\n\r')
        local PROXY
        PROXY=$(grep -v '^#' "$NODE_DIR/proxies.txt" 2>/dev/null | grep -v '^[[:space:]]*$' | head -1)
        echo "node-${NODE_ID} : $CONTENT | proxy: $PROXY" >> "$OUTPUT_TXT"
      fi
    done
    echo "Done! Collected $count earnapp link(s) into earnapp-links.json and earnapp-links.txt"
    echo ""
    cat "$OUTPUT_JSON"
  fi
}

delete_node() {
  local NODE_ID="$1"
  local NODE_DIR="$RUNTIME_DIR/node-${NODE_ID}"

  if [ ! -d "$NODE_DIR" ]; then
    echo "  [SKIP] node-${NODE_ID} not found"
    return 1
  fi

  run_node "stop" "--delete" "$NODE_ID"
  echo "  Removing node-${NODE_ID}..."
  sed -i "/^node-${NODE_ID} :/d" "$SCRIPT_DIR/earnapp-links.txt" 2>/dev/null
  rm -rf "$NODE_DIR"
  echo "  -> node-${NODE_ID} deleted"
}

delete_nodes() {
  shift
  local NODES=("$@")

  if [ ${#NODES[@]} -eq 0 ]; then
    echo "Error: no node IDs provided"
    echo "Usage: $0 --delete-node <id> [id2 id3 ...]  (use --list-nodes to see IDs)"
    exit 1
  fi

  echo "Deleting ${#NODES[@]} node(s)..."
  local count=0
  for NODE_ID in "${NODES[@]}"; do
    if delete_node "$NODE_ID"; then
      count=$((count + 1))
    fi
  done

  echo "Done! Deleted $count node(s)."
}

delete_all_nodes() {
  local count=0
  for NODE_ID in $(get_node_ids); do
    delete_node "$NODE_ID"
    count=$((count + 1))
  done

  if [ $count -eq 0 ]; then
    echo "No node directories found."
  else
    echo "Done! Deleted $count node(s)."
  fi
}

list_nodes() {
  local count=0
  for NODE_ID in $(get_node_ids); do
    local NODE_DIR="$RUNTIME_DIR/node-${NODE_ID}"
    local PROXY
    PROXY=$(grep -v '^#' "$NODE_DIR/proxies.txt" 2>/dev/null | grep -v '^[[:space:]]*$' | head -1)
    echo "node-${NODE_ID}  $PROXY"
    count=$((count + 1))
  done
  if [ $count -eq 0 ]; then
    echo "No nodes found. Run --setup-node first."
  else
    echo ""
    echo "Use node ID (first column) with --start-node, --stop-node, --delete-node"
  fi
}

remove_proxy() {
  shift
  local PROXIES=("$@")

  if [ ${#PROXIES[@]} -eq 0 ]; then
    echo "Error: no proxy provided"
    echo "Usage: $0 --remove-proxy <proxy> [proxy2 proxy3 ...]"
    exit 1
  fi

  local count=0
  for PROXY in "${PROXIES[@]}"; do
    local NORMALIZED
    NORMALIZED=$(normalize_proxy "$PROXY")
    local NODE_ID
    NODE_ID=$(get_node_id "$PROXY")

    echo "Removing proxy -> node-${NODE_ID}"
    delete_node "$NODE_ID"

    if [ -f "$PROXY_FILE" ]; then
      local TMP_FILE
      TMP_FILE=$(mktemp)
      while IFS= read -r line; do
        local TRIMMED
        TRIMMED=$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        if [ "$TRIMMED" != "$NORMALIZED" ]; then
          echo "$line" >> "$TMP_FILE"
        fi
      done < "$PROXY_FILE"
      mv "$TMP_FILE" "$PROXY_FILE"
    fi

    count=$((count + 1))
  done

  echo "Done! Removed $count proxy(ies) and node(s)."
}

import_proxy() {
  local IMPORT_FILE="$1"

  if [[ -z "$IMPORT_FILE" || ! -f "$IMPORT_FILE" ]]; then
    echo "Error: file not found or not specified"
    echo "Usage: $0 --import-proxy <path-to-file>"
    echo "  File: one proxy per line, lines starting with # and empty lines are ignored"
    exit 1
  fi

  if [[ ! -d "$SOURCE_DIR" ]]; then
    echo "Error: source directory not found at $SOURCE_DIR"
    exit 1
  fi

  mkdir -p "$RUNTIME_DIR"
  ensure_proxy_file_header

  local count_new=0
  local count_skip=0

  while IFS= read -r line || [[ -n "$line" ]]; do
    local NORM
    NORM=$(normalize_proxy "$line")
    [[ -z "$NORM" || "$NORM" == \#* ]] && continue

    local NODE_ID
    NODE_ID=$(get_node_id "$NORM")

    if proxy_exists_in_file "$NORM"; then
      create_node "$NODE_ID" "$NORM"
      count_skip=$((count_skip + 1))
    else
      echo "$NORM" >> "$PROXY_FILE"
      create_node "$NODE_ID" "$NORM"
      count_new=$((count_new + 1))
    fi
  done < "$IMPORT_FILE"

  echo "Done! Imported $count_new new proxy(ies), $count_skip already in file (node updated)."
}

container_logs() {
  local NODE_ID="$1"
  local CONTAINER="$2"
  local TAIL="${3:-100}"
  local NODE_DIR="$RUNTIME_DIR/node-${NODE_ID}"

  if [[ -z "$NODE_ID" || -z "$CONTAINER" ]]; then
    echo "Usage: $0 --container-logs <node_id> <container_name> [--tail 100]"
    exit 1
  fi
  if [[ ! -d "$NODE_DIR" ]]; then
    echo "Error: node-${NODE_ID} not found"
    exit 1
  fi
  sudo docker logs --tail "$TAIL" "$CONTAINER" 2>&1
}

container_restart() {
  local NODE_ID="$1"
  local CONTAINER="$2"
  local NODE_DIR="$RUNTIME_DIR/node-${NODE_ID}"

  if [[ -z "$NODE_ID" || -z "$CONTAINER" ]]; then
    echo "Usage: $0 --container-restart <node_id> <container_name>"
    exit 1
  fi
  if [[ ! -d "$NODE_DIR" ]]; then
    echo "Error: node-${NODE_ID} not found"
    exit 1
  fi
  echo "Restarting container $CONTAINER..."
  sudo docker restart "$CONTAINER"
  echo "Done."
}

case "$1" in
  --setup-node)
    setup_nodes
    ;;
  --delete-node)
    delete_nodes "$@"
    ;;
  --delete-all)
    delete_all_nodes
    ;;
  --start-node)
    shift
    run_nodes "start" "--start" "$@"
    ;;
  --start-all)
    run_all_nodes "start" "--start"
    ;;
  --stop-node)
    shift
    run_nodes "stop" "--delete" "$@"
    ;;
  --stop-all)
    run_all_nodes "stop" "--delete"
    ;;
  --update-properties)
    update_properties
    ;;
  --add-proxy)
    add_proxy "$@"
    ;;
  --remove-proxy)
    remove_proxy "$@"
    ;;
  --import-proxy)
    import_proxy "$2"
    ;;
  --list-nodes)
    list_nodes
    ;;
  --collect-earnapp)
    collect_earnapp
    ;;
  --container-logs)
    TAIL=100
    if [[ "$4" == --tail && -n "$5" ]]; then TAIL="$5"; fi
    container_logs "$2" "$3" "$TAIL"
    ;;
  --container-restart)
    container_restart "$2" "$3"
    ;;
  *)
    echo "Usage: $0 <command>"
    echo ""
    echo "Commands:"
    echo "  --setup-node                        Create nodes from proxies.txt (node ID = hash of proxy)"
    echo "  --add-proxy <proxy> [proxies...]    Add proxy(s) and create node(s)"
    echo "  --import-proxy <file>               Import proxies from file (one per line)"
    echo "  --remove-proxy <proxy> [proxies...] Remove proxy(s) from file and delete node(s)"
    echo "  --list-nodes                        List all nodes (id + proxy)"
    echo "  --delete-node <id> [ids...]         Stop and delete one or more nodes"
    echo "  --delete-all                        Stop and delete all nodes"
    echo "  --start-node <id> [ids...]          Start one or more nodes"
    echo "  --start-all                         Start all nodes"
    echo "  --stop-node <id> [ids...]           Stop one or more nodes"
    echo "  --stop-all                          Stop all nodes"
    echo "  --update-properties                 Update properties.conf in all nodes"
    echo "  --collect-earnapp                   Collect earnapp links from all nodes"
    echo "  --container-logs <id> <container> [--tail N]  Show container logs"
    echo "  --container-restart <id> <container>          Restart container"
    ;;
esac
