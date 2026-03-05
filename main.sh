#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE_DIR="$SCRIPT_DIR/source"
PROXY_FILE="$SCRIPT_DIR/proxies.txt"
PROPERTIES_FILE="$SCRIPT_DIR/properties.conf"
RUNTIME_DIR="$SCRIPT_DIR/runtime"

run_node() {
  local ACTION="$1"
  local INCOME_ARG="$2"
  local NODE_NUM="$3"
  local NODE_DIR="$RUNTIME_DIR/node-${NODE_NUM}"

  if [ ! -d "$NODE_DIR" ]; then
    echo "  [SKIP] node-${NODE_NUM} not found"
    return 1
  fi

  if [ ! -f "$NODE_DIR/internetIncome.sh" ]; then
    echo "  [SKIP] internetIncome.sh not found in node-${NODE_NUM}"
    return 1
  fi

  echo "  ${ACTION} node-${NODE_NUM}..."
  (cd "$NODE_DIR" && sudo bash internetIncome.sh "$INCOME_ARG")
  echo "  -> node-${NODE_NUM} done"

  if [ "$ACTION" == "start" ]; then
    local EARNAPP_FILE="$NODE_DIR/earnapp.txt"
    if [ -f "$EARNAPP_FILE" ]; then
      local CONTENT=$(cat "$EARNAPP_FILE" | tr -d '\n')
      echo "  [earnapp] node-${NODE_NUM} : $CONTENT"
      local OUTPUT_FILE="$SCRIPT_DIR/earnapp-links.txt"
      sed -i "/^node-${NODE_NUM} :/d" "$OUTPUT_FILE" 2>/dev/null
      echo "node-${NODE_NUM} : $CONTENT" >> "$OUTPUT_FILE"
    fi
  fi
}

run_nodes() {
  local ACTION="$1"
  local INCOME_ARG="$2"
  shift 2
  local NODES=("$@")

  if [ ${#NODES[@]} -eq 0 ]; then
    echo "Error: no node numbers provided"
    echo "Usage: $0 --${ACTION}-node <num> [num2 num3 ...]"
    exit 1
  fi

  echo "${ACTION^} ${#NODES[@]} node(s)..."
  local count=0
  for NODE_NUM in "${NODES[@]}"; do
    if run_node "$ACTION" "$INCOME_ARG" "$NODE_NUM"; then
      count=$((count + 1))
    fi
  done

  echo "Done! ${ACTION^} $count node(s)."
}

get_sorted_node_nums() {
  for NODE_DIR in "$RUNTIME_DIR"/node-*; do
    if [ -d "$NODE_DIR" ]; then
      basename "$NODE_DIR" | sed 's/node-//'
    fi
  done | sort -n
}

run_all_nodes() {
  local ACTION="$1"
  local INCOME_ARG="$2"

  local count=0
  for NODE_NUM in $(get_sorted_node_nums); do
    if run_node "$ACTION" "$INCOME_ARG" "$NODE_NUM"; then
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
  local NODE_NUM="$1"
  local PROXY="$2"
  local NODE_DIR="$RUNTIME_DIR/node-${NODE_NUM}"

  echo "Creating node-${NODE_NUM} with proxy: $PROXY"

  rm -rf "$NODE_DIR"
  cp -r "$SOURCE_DIR" "$NODE_DIR"
  rm -rf "$NODE_DIR/.git"

  cat > "$NODE_DIR/proxies.txt" << EOF
$PROXY
EOF

  if [ -f "$PROPERTIES_FILE" ]; then
    cp "$PROPERTIES_FILE" "$NODE_DIR/properties.conf"
  fi

  sed -i "s/^DEVICE_NAME=.*/DEVICE_NAME='node-${NODE_NUM}'/" "$NODE_DIR/properties.conf"

  echo "  -> node-${NODE_NUM} created"
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

  mapfile -t PROXIES < <(grep -v '^#' "$PROXY_FILE" | grep -v '^[[:space:]]*$')

  if [ ${#PROXIES[@]} -eq 0 ]; then
    echo "No proxies found in $PROXY_FILE"
    exit 1
  fi

  echo "Found ${#PROXIES[@]} proxies"

  mkdir -p "$RUNTIME_DIR"

  for i in "${!PROXIES[@]}"; do
    create_node "$((i + 1))" "${PROXIES[$i]}"
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

  mapfile -t EXISTING < <(grep -v '^#' "$PROXY_FILE" | grep -v '^[[:space:]]*$')
  local NEXT_NUM=$(( ${#EXISTING[@]} + 1 ))

  local count=0
  for PROXY in "${NEW_PROXIES[@]}"; do
    echo "$PROXY" >> "$PROXY_FILE"
    create_node "$NEXT_NUM" "$PROXY"
    NEXT_NUM=$((NEXT_NUM + 1))
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
  for NODE_NUM in $(get_sorted_node_nums); do
    local NODE_DIR="$RUNTIME_DIR/node-${NODE_NUM}"
    cp "$PROPERTIES_FILE" "$NODE_DIR/properties.conf"
    echo "  Updated node-${NODE_NUM}/properties.conf"
    count=$((count + 1))
  done

  if [ $count -eq 0 ]; then
    echo "No node directories found. Run --setup-node first."
  else
    echo "Done! Updated properties.conf in $count node(s)."
  fi
}

collect_earnapp() {
  local OUTPUT_FILE="$SCRIPT_DIR/earnapp-links.txt"
  > "$OUTPUT_FILE"

  local count=0
  for NODE_NUM in $(get_sorted_node_nums); do
    local EARNAPP_FILE="$RUNTIME_DIR/node-${NODE_NUM}/earnapp.txt"
    if [ -f "$EARNAPP_FILE" ]; then
      local CONTENT=$(cat "$EARNAPP_FILE" | tr -d '\n')
      echo "node-${NODE_NUM} : $CONTENT" >> "$OUTPUT_FILE"
      count=$((count + 1))
    else
      echo "  [SKIP] node-${NODE_NUM} — earnapp.txt not found"
    fi
  done

  if [ $count -eq 0 ]; then
    echo "No earnapp.txt found in any node."
    rm -f "$OUTPUT_FILE"
  else
    echo "Done! Collected $count earnapp link(s) into earnapp-links.txt"
    echo ""
    cat "$OUTPUT_FILE"
  fi
}

delete_node() {
  local NODE_NUM="$1"
  local NODE_DIR="$RUNTIME_DIR/node-${NODE_NUM}"

  if [ ! -d "$NODE_DIR" ]; then
    echo "  [SKIP] node-${NODE_NUM} not found"
    return 1
  fi

  run_node "stop" "--delete" "$NODE_NUM"
  echo "  Removing node-${NODE_NUM}..."
  sed -i "/^node-${NODE_NUM} :/d" "$SCRIPT_DIR/earnapp-links.txt" 2>/dev/null
  rm -rf "$NODE_DIR"
  echo "  -> node-${NODE_NUM} deleted"
}

delete_nodes() {
  shift
  local NODES=("$@")

  if [ ${#NODES[@]} -eq 0 ]; then
    echo "Error: no node numbers provided"
    echo "Usage: $0 --delete-node <num> [num2 num3 ...]"
    exit 1
  fi

  echo "Deleting ${#NODES[@]} node(s)..."
  local count=0
  for NODE_NUM in "${NODES[@]}"; do
    if delete_node "$NODE_NUM"; then
      count=$((count + 1))
    fi
  done

  echo "Done! Deleted $count node(s)."
}

delete_all_nodes() {
  local count=0
  for NODE_NUM in $(get_sorted_node_nums); do
    delete_node "$NODE_NUM"
    count=$((count + 1))
  done

  if [ $count -eq 0 ]; then
    echo "No node directories found."
  else
    echo "Done! Deleted $count node(s)."
  fi
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
  *)
    echo "Usage: $0 <command>"
    echo ""
    echo "Commands:"
    echo "  --setup-node                        Create node directories from proxies.txt"
    echo "  --add-proxy <proxy> [proxies...]    Add proxy(s) and create node(s)"
    echo "  --delete-node <num> [nums...]       Stop and delete one or more nodes"
    echo "  --delete-all                        Stop and delete all nodes"
    echo "  --start-node <num> [nums...]        Start one or more nodes"
    echo "  --start-all                         Start all nodes"
    echo "  --stop-node <num> [nums...]         Stop one or more nodes"
    echo "  --stop-all                          Stop all nodes"
    echo "  --update-properties                 Update properties.conf in all nodes"
    echo "  --collect-earnapp                   Collect earnapp links from all nodes"
    ;;
esac
