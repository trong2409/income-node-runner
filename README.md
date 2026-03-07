# Income Node Runner

A system to manage multiple nodes running in parallel, each using its own proxy. It includes a web UI to add proxies, create nodes, start/stop nodes, and view logs.

## Requirements

- **Bash** (Linux / WSL / macOS)
- **Python 3** (stdlib only, no extra packages)
- **sudo** (for running containers in each node; may be needed to fix `runtime/` permissions)

## Before first run: configure web login

Copy the example config and edit it with your credentials and a secure session secret:

```bash
cp web/config.json.example web/config.json
```

Then edit **`web/config.json`** and change at least:

- **`username`** / **`password`** — login for the web UI (use something other than the example `admin`/`admin`)
- **`session_secret`** — set to a long random string (e.g. `openssl rand -hex 32`); keep it private
- **`port`** (optional) — default is `8765`; change if you need another port

Do this before running the server. `web/config.json` is in `.gitignore`; never commit it.

## Running the system (recommended)

From the project directory:

```bash
./start.sh
```

The script will:

1. Fix ownership of `runtime/` for the current user (if it was owned by root)
2. Create `runtime/` if it does not exist
3. Start the web server

Open in browser: **http://127.0.0.1:8765**

**Login:** The app requires login. Use **`web/config.json`** as above (copy from `web/config.json.example` if needed). Session lasts 24 hours.

### Run options

| Command | Description |
|--------|-------------|
| `./start.sh` | Fix permissions (if needed) then run server (foreground) |
| `./start.sh --fix-only` | Only fix `runtime/` permissions; do not start server |
| `./start.sh --background` | Fix permissions then run server in background; log to `web/server.log` |

### Changing the port

Default port is **8765**. Override with:

```bash
PORT=3000 ./start.sh
```

Or run the server manually:

```bash
PORT=3000 python3 web/server.py
```

## Running the server manually (without start.sh)

If you already have write access to `runtime/`:

```bash
cd /path/to/income-node-runner
python3 web/server.py
```

If you get permission errors when managing nodes, run first:

```bash
./start.sh --fix-only
```

Then run `python3 web/server.py` or `./start.sh`.

## Quick guide (web UI)

1. **Add proxies** (**Manage proxies** tab)
   - Paste a list of proxies (one per line), click **Add**.
   - The system **creates nodes automatically**; you do not need to click "Setup nodes".

2. **Manage nodes** (**Manage nodes** tab)
   - **Setup nodes**: Recreate all nodes from `proxies.txt` (e.g. after editing the file or importing).
   - **Start all / Stop all / Delete all**: Act on all nodes.
   - **Update properties**: Copy `properties.conf` into all nodes.
   - **Collect EarnApp**: Write EarnApp links from all nodes to `earnapp-links.txt`.
   - Per row: **Start**, **Stop**, **Delete**, **Restart**; or select multiple nodes and use the **Select multiple** bar.

3. **Node details**
   - Click a node **ID** to open the modal: view proxy, status, EarnApp, containers; **Logs** and **Restart** per container.

4. **Output**
   - The **Output** section at the bottom shows command output; use **Clear** to clear it.

## Directory structure (summary)

```
income-node-runner/
├── start.sh           # Startup script (fix permissions + start web)
├── main.sh            # CLI script (used by web or run by hand)
├── proxies.txt        # Proxy list (one per line)
├── properties.conf    # Shared config for all nodes
├── source/            # Original template — do not edit
├── runtime/           # Auto-created — contains node-<id>/
├── docs/
│   ├── document.md    # Detailed command & structure docs
│   └── instruction.md # LLM agent instructions
├── web/
│   ├── config.json.example  # Example config — copy to config.json and edit
│   ├── server.py            # API + serve UI
│   ├── node_meta.py         # Read/write per-node meta
│   └── index.html           # Management UI
└── README.md          # This file — how to run the system
```

## CLI (main.sh)

You can run commands from the terminal instead of the web UI. Run with no arguments to see the command list:

```bash
./main.sh
```

Common commands:

| Command | Description |
|--------|-------------|
| `--list-nodes` | List nodes and proxies |
| `--add-proxy <proxy> [...]` | Add proxy and create node |
| `--setup-node` | Create nodes from all proxies in `proxies.txt` |
| `--start-all` / `--stop-all` | Start / stop all nodes |
| `--start-node <id> [...]` / `--stop-node <id> [...]` | Start / stop by ID |
| `--delete-node <id> [...]` / `--delete-all` | Delete nodes |
| `--update-properties` | Update `properties.conf` in all nodes |
| `--collect-earnapp` | Collect EarnApp links into `earnapp-links.txt` |

See **docs/document.md** for full details.

## Notes

- **runtime/** is created and overwritten when recreating nodes; avoid editing files there by hand.
- **source/** is the template; do not edit unless explicitly required.
- Node ID = first 8 characters of SHA256(proxy); same proxy always maps to the same node.
