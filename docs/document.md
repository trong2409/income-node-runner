# Income Node Runner

Script to manage multiple nodes running in parallel, each using its own proxy.

**Node-proxy relationship**: Each node has ID = first 8 characters of SHA256(proxy). Same proxy always maps to the same node; proxy order in `proxies.txt` does not matter.

## Directory structure

```
income-node-runner/
├── main.sh              # Main script
├── proxies.txt          # Proxy list (one per line)
├── properties.conf      # Shared config for all nodes
├── source/              # Template directory copied for each node
├── runtime/             # (auto-created) Contains all nodes
│   ├── node-7f3a9b2c/   # ID = hash of proxy
│   │   ├── node-meta.json   # meta: name, proxy, earnapp_link, containers[], status
│   │   ├── proxies.txt
│   │   ├── containernames.txt   # (after start) container list
│   │   └── ...
│   └── ...
```

## Config files

| File | Description |
|------|-------------|
| `proxies.txt` | Proxy list, **one proxy per line** (trimmed). Lines starting with `#` and empty lines are skipped. Format: `protocol://username:password@ip:port` |
| `properties.conf` | Shared config file, copied into each node on setup |
| `source/` | Original template directory, copied as-is for each node |

### Managing `proxies.txt` (web-ready)

- **Normalization**: Each proxy is trimmed when written (no leading/trailing spaces, no newline) — one proxy has a single canonical form in the file.
- **No duplicates**: `--add-proxy` and `--import-proxy` do not add if the proxy is already in the file (compare normalized content).
- **Format**: One line = one proxy. The web can read line by line, filter `#` and empty, and use as data source.

## Commands

### `--setup-node`

```bash
./main.sh --setup-node
```

Create nodes from the proxy list in `proxies.txt`:
- Creates `runtime/` if missing
- For each proxy: `node_id = hash(proxy)` (8 chars), create `runtime/node-<node_id>/`
- Copy `source/`, write proxy to node's `proxies.txt`, copy and set `DEVICE_NAME='node-<id>'` in `properties.conf`
- Line order in `proxies.txt` does not affect which node gets which proxy

### `--list-nodes`

```bash
./main.sh --list-nodes
```

Print `node-<id>  <proxy>`. Use the ID (first column) with `--start-node`, `--stop-node`, `--delete-node`.

### `--add-proxy <proxy> [proxy2 proxy3 ...]`

```bash
./main.sh --add-proxy socks5://user:pass@1.2.3.4:1080
./main.sh --add-proxy socks5://user:pass@1.2.3.4:1080 http://user:pass@5.6.7.8:8080
```

Add proxy to `proxies.txt` (no duplicate) and create the corresponding node (node ID = hash of proxy).

### `--import-proxy <file>`

```bash
./main.sh --import-proxy ./my-proxies.txt
./main.sh --import-proxy /path/to/list.txt
```

Import multiple proxies from a file at once:
- File: **one proxy per line**; lines starting with `#` and empty lines are skipped.
- Proxy already in `proxies.txt` (after normalization): only update node, do not add a new line.
- Proxy not in file: add to `proxies.txt` and create node.
- At the end, prints count of newly imported and already-present proxies.

### `--remove-proxy <proxy> [proxy2 proxy3 ...]`

```bash
./main.sh --remove-proxy socks5://user:pass@1.2.3.4:1080
./main.sh --remove-proxy "http://a:b@x:8080" "http://c:d@y:8080"
```

Remove proxy and its node:
- Stop and delete node (same logic as `--delete-node` with ID = hash of proxy)
- Remove all lines matching the proxy (after trim) from `proxies.txt`
- Can pass multiple proxies as separate arguments

### `--delete-node <id> [id2 id3 ...]`

```bash
./main.sh --delete-node 7f3a9b2c
./main.sh --delete-node 7f3a9b2c 8e2c1d4a
```

Stop and delete one or more nodes by ID (see `--list-nodes`). Removes the corresponding line from `earnapp-links.txt` and the node directory.

### `--delete-all`

```bash
./main.sh --delete-all
```

Stop and delete all nodes in `runtime/`.

### `--start-node <id> [id2 id3 ...]`

```bash
./main.sh --start-node 7f3a9b2c
./main.sh --start-node 7f3a9b2c 8e2c1d4a
```

Run `sudo bash internetIncome.sh --start` in one or more nodes (ID from `--list-nodes`).

### `--start-all`

```bash
./main.sh --start-all
```

Run `sudo bash internetIncome.sh --start` in all nodes in `runtime/`.

> **Note**: When starting a node, if `earnapp.txt` exists, its content is written to `earnapp-links.txt`.

### `--stop-node <id> [id2 id3 ...]`

```bash
./main.sh --stop-node 7f3a9b2c
```

Run `sudo bash internetIncome.sh --delete` in one or more nodes by ID.

### `--stop-all`

```bash
./main.sh --stop-all
```

Run `sudo bash internetIncome.sh --delete` in all nodes in `runtime/`.

### Per-node meta (`node-meta.json`)

Each node has **`node-meta.json`** (auto-created/updated):

- **name**: node name (e.g. `node-7f3a9b2c`)
- **proxy**: corresponding proxy
- **earnapp_link**: EarnApp link (if any, from `earnapp.txt`)
- **containers**: list of Docker container names (from `containernames.txt`)
- **status**: `active` or `inactive`

- On **start**: set `status=active`, reread `containernames.txt` and `earnapp.txt` and write to meta.
- On **stop**: set `status=inactive`.

Script `web/node_meta.py` is used to write/refresh meta (called from `main.sh`).

### `--container-logs <id> <container> [--tail N]`

```bash
./main.sh --container-logs 7f3a9b2c tun1a2b3c4d --tail 200
```

Print container logs (default last 100 lines). Container must belong to that node (in `containernames.txt`).

### `--container-restart <id> <container>`

```bash
./main.sh --container-restart 7f3a9b2c tun1a2b3c4d
```

Run `sudo docker restart <container>`.

### `--update-properties`

```bash
./main.sh --update-properties
```

Copy root `properties.conf` over `properties.conf` in all nodes in `runtime/`.

### `--collect-earnapp`

```bash
./main.sh --collect-earnapp
```

Collect earnapp links from all nodes into `earnapp-links.txt` in format `node-<id> : <earnapp.txt content>`.

---

## Web UI (lightweight)

The `web/` directory contains the server and management UI.

### Quick start (recommended)

```bash
./start.sh
```

The `start.sh` script will:
- Fix `runtime/` ownership for the current user (if owned by root)
- Create `runtime/` if missing
- Start the web server

Options:
- `./start.sh --fix-only` — Only fix `runtime/` permissions; do not start server
- `./start.sh --background` — Fix permissions then run server in background (log to `web/server.log`)

### Running the server manually

```bash
cd /path/to/income-node-runner
python3 web/server.py
```

Open in browser: **http://127.0.0.1:8765**

- **Requirements**: Python 3 (no extra packages).
- **Features**: View nodes & proxies; Setup / Start all / Stop all / Delete all; Start/Stop/Delete per node; Add/Remove proxy.
- **Port**: Default 8765; override with `PORT=3000 ./start.sh` or `PORT=3000 python3 web/server.py`.

---

## Migration (from node-1, node-2 to node-&lt;hash&gt;)

If you are on an older version (node-1, node-2, …): run `--delete-all` then run `--setup-node` again. New nodes will be named `node-<hash>`. `earnapp-links.txt` will be recreated when nodes are started.
