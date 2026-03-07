# Instruction for LLM Agents

You are working with the **income-node-runner** project — a system that manages multiple nodes running in parallel, each with its own proxy.

## Required rules

- **Use English only** for all project content: documentation (`README.md`, `docs/document.md`, `docs/instruction.md`), user-facing strings (web UI, CLI messages, comments), and any new text you add. Do not introduce other languages unless the user explicitly requests it.
- **Always read `docs/document.md`** before making any changes. It contains the full directory structure, config files, and current command list.
- **After each change, update `docs/document.md`** to reflect the current state of the project (new/changed/removed commands, structure changes, etc.).
- **Do not modify the `source/` directory** unless explicitly requested. It is the original template.
- **Do not edit files inside `runtime/` directly.** This directory is created by the script; changes will be overwritten when running `--setup-node`.

## Project structure

```
income-node-runner/
├── main.sh              # Main script — all logic lives here
├── proxies.txt          # Proxy list (user input)
├── properties.conf      # Shared config for all nodes
├── source/              # Original template — DO NOT EDIT
├── runtime/             # Auto-created — contains node-<hash>/
├── docs/
│   ├── document.md      # Feature documentation — UPDATE AFTER EACH CHANGE
│   └── instruction.md   # This file — instructions for LLM
└── web/                 # Web UI (Python stdlib + 1 HTML file)
    ├── server.py        # API + serve static
    ├── node_meta.py     # Read/write node-meta.json (name, proxy, earnapp_link, containers, status)
    └── index.html       # Management page for nodes & proxies (meta, logs, restart container)
```

## How `main.sh` works

The script uses a `case` to handle commands passed as arguments:

```bash
./main.sh <command>
```

### Current commands

Node ID = first 8 characters of SHA256(proxy). Node directory = `runtime/node-<id>`.

| Command                                        | Function                             | Description                                                                            |
| ---------------------------------------------- | ------------------------------------ | -------------------------------------------------------------------------------------- |
| `--setup-node`                                 | `setup_nodes()`                      | For each proxy: `get_node_id(proxy)` → `create_node(id, proxy)`                        |
| `--list-nodes`                                 | `list_nodes()`                       | Print node-<id> and proxy                                                              |
| `--add-proxy <proxy> [proxies...]`             | `add_proxy()`                        | Normalize proxy, `append_proxy_to_file` (no duplicate), `create_node`                  |
| `--import-proxy <file>`                        | `import_proxy()`                     | Read file (1 proxy/line, skip # and empty), add to file (no duplicate) and create node |
| `--remove-proxy <proxy> [proxies...]`          | `remove_proxy()`                     | Remove proxy from `proxies.txt` and delete node (stop + delete_node + remove line)     |
| `--delete-node <id> [ids...]`                  | `delete_nodes()`                     | Stop and delete node(s) by ID, remove earnapp link                                     |
| `--delete-all`                                 | `delete_all_nodes()`                 | Stop and delete all nodes                                                              |
| `--start-node <id> [ids...]`                   | `run_nodes("start", "--start", ...)` | Start node(s) by ID                                                                    |
| `--start-all`                                  | `run_all_nodes("start", "--start")`  | Start all nodes                                                                        |
| `--stop-node <id> [ids...]`                    | `run_nodes("stop", "--delete", ...)` | Stop node(s) by ID                                                                     |
| `--stop-all`                                   | `run_all_nodes("stop", "--delete")`  | Stop all nodes                                                                         |
| `--update-properties`                          | `update_properties()`                | Copy `properties.conf` into all nodes                                                  |
| `--collect-earnapp`                            | `collect_earnapp()`                  | Collect earnapp links into `earnapp-links.txt`                                         |
| `--container-logs <id> <container> [--tail N]` | `container_logs()`                   | Print container logs (docker logs)                                                     |
| `--container-restart <id> <container>`         | `container_restart()`                | Restart container (docker restart)                                                     |

### When adding a new command

1. Add a new function in `main.sh`
2. Add a new case in the `case "$1" in ... esac` block
3. Add a description line in the help (case `*`)
4. Update `docs/document.md` with the new command description

## Global variables in `main.sh`

| Variable          | Value                          |
| ----------------- | ------------------------------ |
| `SCRIPT_DIR`      | Directory containing `main.sh` |
| `SOURCE_DIR`      | `$SCRIPT_DIR/source`           |
| `PROXY_FILE`      | `$SCRIPT_DIR/proxies.txt`      |
| `PROPERTIES_FILE` | `$SCRIPT_DIR/properties.conf`  |
| `RUNTIME_DIR`     | `$SCRIPT_DIR/runtime`         |

## Conventions

- Command names: `--<action>-<target>` (e.g. `--setup-node`, `--delete-node`)
- Function names: `<action>_<target>s()` (e.g. `setup_nodes()`, `delete_nodes()`)
- Node ID: `get_node_id(proxy)` = first 8 chars of SHA256(trimmed proxy). Directory = `runtime/node-<id>`
- `get_node_ids()`: list all node IDs (sorted), used for run_all, delete_all, update_properties, collect_earnapp
- Proxy: `normalize_proxy(proxy)` (trim, no newline); `proxy_exists_in_file(norm)`; `append_proxy_to_file(norm)` (no duplicate). Stored one per line for easy web read/write.
- Proxy format: `protocol://username:password@ip:port` or `protocol://ip:port`
