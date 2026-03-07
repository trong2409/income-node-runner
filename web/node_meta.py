#!/usr/bin/env python3
"""Read/write node-meta.json. Usage: node_meta.py write <node_dir> <status>"""
import json
import os
import sys
from datetime import datetime, timezone

META_FILE = "node-meta.json"
PROXIES_FILE = "proxies.txt"
EARNAPP_FILE = "earnapp.txt"
CONTAINERS_FILE = "containernames.txt"


def read_proxy(node_dir):
    path = os.path.join(node_dir, PROXIES_FILE)
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                return line
    return ""


def read_earnapp(node_dir):
    path = os.path.join(node_dir, EARNAPP_FILE)
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read().strip().replace("\n", " ").replace("\r", "")


def read_containers(node_dir):
    path = os.path.join(node_dir, CONTAINERS_FILE)
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return [line.strip() for line in f if line.strip()]


def _read_existing_meta(node_dir):
    path = os.path.join(node_dir, META_FILE)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def write_meta(node_dir, status, name=None):
    existing = _read_existing_meta(node_dir)
    proxy = read_proxy(node_dir)
    earnapp = read_earnapp(node_dir)
    containers = read_containers(node_dir)
    if name is None:
        name = os.path.basename(node_dir.rstrip("/")) or "node-unknown"
    created_at = existing.get("created_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta = {
        "name": name,
        "proxy": proxy,
        "earnapp_link": earnapp,
        "containers": containers,
        "status": status,
        "created_at": created_at,
    }
    path = os.path.join(node_dir, META_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=0)


def migrate(runtime_dir):
    """Backfill created_at into all node-meta.json and build proxy-meta.json."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    proxy_meta_path = os.path.join(runtime_dir, "proxy-meta.json")

    proxy_meta = {}
    if os.path.isfile(proxy_meta_path):
        try:
            with open(proxy_meta_path, "r", encoding="utf-8") as f:
                proxy_meta = json.load(f)
        except Exception:
            pass

    node_count = 0
    proxy_count = 0

    for entry in sorted(os.listdir(runtime_dir)):
        node_dir = os.path.join(runtime_dir, entry)
        if not os.path.isdir(node_dir) or not entry.startswith("node-"):
            continue

        meta_path = os.path.join(node_dir, META_FILE)
        existing = _read_existing_meta(node_dir)

        if not existing.get("created_at"):
            existing["created_at"] = now
            if not existing.get("name"):
                existing["name"] = entry
            if not existing.get("proxy"):
                existing["proxy"] = read_proxy(node_dir)
            if not existing.get("status"):
                existing["status"] = "inactive"
            if "earnapp_link" not in existing:
                existing["earnapp_link"] = read_earnapp(node_dir)
            if "containers" not in existing:
                existing["containers"] = read_containers(node_dir)
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=0)
            node_count += 1

        proxy = existing.get("proxy") or read_proxy(node_dir)
        if proxy and proxy not in proxy_meta:
            proxy_meta[proxy] = {"created_at": existing.get("created_at") or now}
            proxy_count += 1

    with open(proxy_meta_path, "w", encoding="utf-8") as f:
        json.dump(proxy_meta, f, ensure_ascii=False, indent=0)

    print(f"[migrate] Backfilled created_at for {node_count} node(s).")
    print(f"[migrate] Added {proxy_count} proxy(ies) to proxy-meta.json.")
    print(f"[migrate] proxy-meta.json has {len(proxy_meta)} total entries.")


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "migrate":
        runtime_dir = sys.argv[2]
        if not os.path.isdir(runtime_dir):
            print(f"Error: runtime directory not found: {runtime_dir}", file=sys.stderr)
            sys.exit(1)
        migrate(runtime_dir)
        return

    if len(sys.argv) < 4 or sys.argv[1] != "write":
        print("Usage: node_meta.py write <node_dir> <status>", file=sys.stderr)
        print("       node_meta.py migrate <runtime_dir>", file=sys.stderr)
        sys.exit(1)
    _, _, node_dir, status = sys.argv[:4]
    if status not in ("active", "inactive"):
        status = "inactive"
    write_meta(node_dir, status)
    print("OK")


if __name__ == "__main__":
    main()
