#!/usr/bin/env python3
"""Read/write node-meta.json. Usage: node_meta.py write <node_dir> <status>"""
import json
import os
import sys

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


def write_meta(node_dir, status, name=None):
    proxy = read_proxy(node_dir)
    earnapp = read_earnapp(node_dir)
    containers = read_containers(node_dir)
    if name is None:
        name = os.path.basename(node_dir.rstrip("/")) or "node-unknown"
    meta = {
        "name": name,
        "proxy": proxy,
        "earnapp_link": earnapp,
        "containers": containers,
        "status": status,
    }
    path = os.path.join(node_dir, META_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=0)


def main():
    if len(sys.argv) < 4 or sys.argv[1] != "write":
        print("Usage: node_meta.py write <node_dir> <status>", file=sys.stderr)
        sys.exit(1)
    _, _, node_dir, status = sys.argv[:4]
    if status not in ("active", "inactive"):
        status = "inactive"
    write_meta(node_dir, status)
    print("OK")


if __name__ == "__main__":
    main()
