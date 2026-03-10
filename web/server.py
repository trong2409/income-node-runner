#!/usr/bin/env python3
"""
Lightweight web server for income-node-runner.
Python 3 stdlib only. Run from project root: python3 web/server.py
Login: credentials in web/config.json. Session 24h.
"""
import base64
import hashlib
import hmac
import json
import math
import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_SH = os.path.join(ROOT, "main.sh")
PROXY_FILE = os.path.join(ROOT, "proxies.txt")
PROXY_META_FILE = os.path.join(ROOT, "runtime", "proxy-meta.json")
RUNTIME_DIR = os.path.join(ROOT, "runtime")
WEB_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(WEB_DIR, "config.json")
META_FILE = "node-meta.json"
SESSION_COOKIE_NAME = "session"
SESSION_MAX_AGE = 86400  # 24 hours


def load_config():
    """Load config.json; create default if missing."""
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    default = {
        "username": "admin",
        "password": "admin",
        "session_secret": "change-me-to-a-random-string",
        "port": 8765,
    }
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2)
    except Exception:
        pass
    return default


def create_session(username, secret):
    """Return signed session cookie value (payload.base64.signature)."""
    exp = time.time() + SESSION_MAX_AGE
    payload = json.dumps({"u": username, "exp": exp}).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")
    return payload_b64 + "." + sig_b64


def verify_session(cookie_value, secret):
    """Return username if session valid and not expired, else None."""
    if not cookie_value or "." not in cookie_value:
        return None
    try:
        payload_b64, sig_b64 = cookie_value.split(".", 1)
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = base64.urlsafe_b64decode(payload_b64)
        sig_b64 += "=" * (4 - len(sig_b64) % 4)
        expected_sig = base64.urlsafe_b64decode(sig_b64)
        sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        data = json.loads(payload.decode("utf-8"))
        if data.get("exp", 0) <= time.time():
            return None
        return data.get("u")
    except Exception:
        return None


def get_cookie(headers, name):
    """Get cookie value by name from Cookie header."""
    cookie = headers.get("Cookie") or ""
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith(name + "="):
            return part[len(name) + 1 :].strip()
    return None


def read_node_meta(node_id):
    """Read node-meta.json; return dict or None."""
    path = os.path.join(RUNTIME_DIR, f"node-{node_id}", META_FILE)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def run_main(args):
    """Run main.sh with args; return (success, output)."""
    if not os.path.isfile(MAIN_SH):
        return False, "main.sh not found"
    try:
        r = subprocess.run(
            ["bash", MAIN_SH] + args,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60 * 60,
        )
        out = (r.stdout or "") + (r.stderr or "")
        return r.returncode == 0, out.strip()
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as e:
        return False, str(e)


def run_main_stream(args):
    """Run main.sh with args; yield (line, returncode). returncode is None until done."""
    if not os.path.isfile(MAIN_SH):
        yield "main.sh not found\n", 1
        return
    try:
        proc = subprocess.Popen(
            ["bash", MAIN_SH] + args,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in iter(proc.stdout.readline, ""):
            yield line, None
        proc.wait()
        yield "", proc.returncode
    except Exception as e:
        yield str(e) + "\n", 1


def parse_list_nodes(output):
    """Parse 'node-<id>  <proxy>' lines into [{id, proxy}]."""
    nodes = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("Use node ID"):
            continue
        if line.startswith("node-") and "  " in line:
            id_part, _, proxy = line.partition("  ")
            node_id = id_part.replace("node-", "", 1)
            nodes.append({"id": node_id, "proxy": proxy.strip()})
    return nodes


def read_proxies():
    """Return list of proxy lines (skip # and empty)."""
    if not os.path.isfile(PROXY_FILE):
        return []
    with open(PROXY_FILE, "r", encoding="utf-8", errors="replace") as f:
        lines = []
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                lines.append(line)
        return lines


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_proxy_meta():
    """Return dict: {proxy_string: {"created_at": "..."}, ...}."""
    if not os.path.isfile(PROXY_META_FILE):
        return {}
    try:
        with open(PROXY_META_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def write_proxy_meta(data):
    with open(PROXY_META_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=0)


def ensure_proxy_meta(proxies, meta=None):
    """Ensure every proxy in the list has an entry in proxy-meta. Returns updated meta dict."""
    if meta is None:
        meta = read_proxy_meta()
    changed = False
    now = _now_iso()
    for p in proxies:
        if p not in meta:
            meta[p] = {"created_at": now}
            changed = True
    if changed:
        write_proxy_meta(meta)
    return meta


def remove_proxy_meta(proxies):
    """Remove proxies from proxy-meta.json."""
    meta = read_proxy_meta()
    changed = False
    for p in proxies:
        norm = p.strip()
        if norm in meta:
            del meta[norm]
            changed = True
    if changed:
        write_proxy_meta(meta)


def paginate(items, page, per_page):
    """Return (page_items, total, pages)."""
    total = len(items)
    pages = max(1, math.ceil(total / per_page))
    page = max(1, min(page, pages))
    start = (page - 1) * per_page
    return items[start : start + per_page], total, page, pages


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # quiet

    def _config(self):
        if not hasattr(Handler, "_config_cache"):
            Handler._config_cache = load_config()
        return Handler._config_cache

    def _session_user(self):
        cookie = get_cookie(self.headers, SESSION_COOKIE_NAME)
        secret = self._config().get("session_secret") or ""
        return verify_session(cookie, secret)

    def send_json(self, data, status=200, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        if headers:
            for k, v in headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def send_text(self, text, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(text.encode("utf-8"))

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length:
            return self.rfile.read(length).decode("utf-8", errors="replace")
        return ""

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _send_unauthorized(self):
        self.send_json({"error": "Unauthorized"}, 401)

    def do_GET(self):
        path = urlparse(self.path).path
        user = self._session_user()

        if path == "/" or path == "/index.html":
            if not user:
                login_path = os.path.join(WEB_DIR, "login.html")
                if os.path.isfile(login_path):
                    with open(login_path, "r", encoding="utf-8") as f:
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(f.read().encode("utf-8"))
                else:
                    self.send_json({"error": "login.html not found"}, 404)
                return
            index_path = os.path.join(WEB_DIR, "index.html")
            if os.path.isfile(index_path):
                with open(index_path, "r", encoding="utf-8") as f:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(f.read().encode("utf-8"))
            else:
                self.send_json({"error": "index.html not found"}, 404)
            return

        if path.startswith("/api/"):
            if path != "/api/me" and not user:
                self._send_unauthorized()
                return
            if path == "/api/me":
                self.send_json(
                    {"ok": True, "user": user} if user else {"ok": False},
                    200 if user else 401,
                )
                return

        if path == "/api/nodes":
            qs = parse_qs(urlparse(self.path).query)
            ok, out = run_main(["--list-nodes"])
            nodes = parse_list_nodes(out) if ok else []
            for n in nodes:
                meta = read_node_meta(n["id"])
                n["meta"] = meta

            search = (qs.get("search") or [""])[0].strip().lower()
            if search:
                nodes = [n for n in nodes if search in n.get("proxy", "").lower()]

            earnapp_search = (qs.get("earnapp_search") or [""])[0].strip().lower()
            if earnapp_search:
                nodes = [
                    n
                    for n in nodes
                    if earnapp_search
                    in (n.get("meta") or {}).get("earnapp_link", "").lower()
                ]

            status_filter = (qs.get("status") or ["all"])[0]
            if status_filter in ("active", "inactive"):
                nodes = [
                    n
                    for n in nodes
                    if (n.get("meta") or {}).get("status") == status_filter
                ]

            sort_field = (qs.get("sort") or ["created_at"])[0]
            sort_desc = (qs.get("sort_dir") or ["desc"])[0] == "desc"
            if sort_field == "created_at":
                nodes.sort(
                    key=lambda n: (n.get("meta") or {}).get("created_at") or "",
                    reverse=sort_desc,
                )
            else:
                nodes.sort(key=lambda n: n.get("id", ""), reverse=sort_desc)

            page = int((qs.get("page") or ["1"])[0])
            per_page = int((qs.get("per_page") or ["20"])[0])
            page_nodes, total, page, pages = paginate(nodes, page, per_page)
            self.send_json(
                {
                    "nodes": page_nodes,
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                    "pages": pages,
                    "raw": out,
                }
            )
            return
        if path.startswith("/api/node/") and path.endswith("/meta"):
            parts = path.split("/")
            if len(parts) == 5 and parts[2] == "node" and parts[4] == "meta":
                node_id = parts[3]
                meta = read_node_meta(node_id)
                if meta is None:
                    self.send_json({"error": "Node or meta not found"}, 404)
                    return
                self.send_json(meta)
                return
        if path.startswith("/api/node/") and "/logs" in path:
            parts = path.split("/")
            if len(parts) >= 5 and parts[2] == "node" and parts[4] == "logs":
                node_id = parts[3]
                qs = parse_qs(urlparse(self.path).query)
                container = (qs.get("container") or [""])[0]
                tail = (qs.get("tail") or ["100"])[0]
                if not container:
                    self.send_json({"error": "container required"}, 400)
                    return
                ok, out = run_main(
                    ["--container-logs", node_id, container, "--tail", str(tail)]
                )
                self.send_text(out)
                return
        if path == "/api/proxies":
            qs = parse_qs(urlparse(self.path).query)
            raw_proxies = read_proxies()
            meta = ensure_proxy_meta(raw_proxies)
            items = [
                {"proxy": p, "created_at": meta.get(p, {}).get("created_at", "")}
                for p in raw_proxies
            ]
            search = (qs.get("search") or [""])[0].strip().lower()
            if search:
                items = [x for x in items if search in x["proxy"].lower()]
            sort_desc = (qs.get("sort_dir") or ["desc"])[0] == "desc"
            items.sort(key=lambda x: x.get("created_at") or "", reverse=sort_desc)
            page = int((qs.get("page") or ["1"])[0])
            per_page = int((qs.get("per_page") or ["20"])[0])
            page_items, total, page, pages = paginate(items, page, per_page)
            self.send_json(
                {
                    "proxies": page_items,
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                    "pages": pages,
                }
            )
            return
        self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        body = self.read_body()
        user = self._session_user()

        if path == "/api/login":
            try:
                data = json.loads(body) if body else {}
                username = (data.get("username") or "").strip()
                password = data.get("password") or ""
                cfg = self._config()
                if (
                    not username
                    or cfg.get("username") != username
                    or cfg.get("password") != password
                ):
                    self.send_json(
                        {"ok": False, "error": "Invalid username or password"}, 401
                    )
                    return
                secret = cfg.get("session_secret") or ""
                cookie_val = create_session(username, secret)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header(
                    "Set-Cookie",
                    f"{SESSION_COOKIE_NAME}={cookie_val}; Path=/; Max-Age={SESSION_MAX_AGE}; HttpOnly; SameSite=Lax",
                )
                self.end_headers()
                self.wfile.write(
                    json.dumps({"ok": True, "user": username}).encode("utf-8")
                )
            except json.JSONDecodeError:
                self.send_json({"ok": False, "error": "Invalid JSON"}, 400)
            return

        if path == "/api/logout":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header(
                "Set-Cookie",
                f"{SESSION_COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax",
            )
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
            return

        if path.startswith("/api/") and not user:
            self._send_unauthorized()
            return

        if path == "/api/exec":
            try:
                data = json.loads(body) if body else {}
                args = data.get("args") or []
                if not isinstance(args, list):
                    args = [str(args)]
                ok, out = run_main(args)
                if ok and "--setup-node" in args:
                    ensure_proxy_meta(read_proxies())
                if ok and "--add-proxy" in args:
                    ensure_proxy_meta(
                        [str(p).strip() for p in args[args.index("--add-proxy") + 1 :]]
                    )
                if ok and "--remove-proxy" in args:
                    remove_proxy_meta(
                        [str(p) for p in args[args.index("--remove-proxy") + 1 :]]
                    )
                self.send_json({"ok": ok, "output": out})
            except json.JSONDecodeError:
                self.send_json({"ok": False, "output": "Invalid JSON"}, 400)
            return

        if path == "/api/exec-stream":
            try:
                data = json.loads(body) if body else {}
                args = data.get("args") or []
                if not isinstance(args, list):
                    args = [str(args)]
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Transfer-Encoding", "chunked")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                exit_code = 1
                for chunk, code in run_main_stream(args):
                    if code is not None:
                        exit_code = code
                        chunk = chunk + "\n[Exit: " + str(code) + "]\n"
                    if chunk:
                        data_bytes = chunk.encode("utf-8")
                        self.wfile.write(
                            ("%x\r\n" % len(data_bytes)).encode() + data_bytes + b"\r\n"
                        )
                        self.wfile.flush()
                if exit_code == 0 and "--setup-node" in args:
                    ensure_proxy_meta(read_proxies())
                if exit_code == 0 and "--add-proxy" in args:
                    ensure_proxy_meta(
                        [str(p).strip() for p in args[args.index("--add-proxy") + 1 :]]
                    )
                if exit_code == 0 and "--remove-proxy" in args:
                    remove_proxy_meta(
                        [str(p) for p in args[args.index("--remove-proxy") + 1 :]]
                    )
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except json.JSONDecodeError:
                self.send_json({"ok": False, "output": "Invalid JSON"}, 400)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        if path == "/api/proxy/add":
            try:
                data = json.loads(body) or {}
                proxies = data.get("proxies") or []
                if not proxies:
                    self.send_json({"ok": False, "output": "No proxies"}, 400)
                    return
                ok, out = run_main(["--add-proxy"] + [str(p) for p in proxies])
                if ok:
                    ensure_proxy_meta([str(p).strip() for p in proxies])
                self.send_json({"ok": ok, "output": out})
            except json.JSONDecodeError:
                self.send_json({"ok": False, "output": "Invalid JSON"}, 400)
            return

        if path == "/api/proxy/remove":
            try:
                data = json.loads(body) or {}
                proxies = data.get("proxies") or []
                if not proxies:
                    self.send_json({"ok": False, "output": "No proxies"}, 400)
                    return
                ok, out = run_main(["--remove-proxy"] + [str(p) for p in proxies])
                if ok:
                    remove_proxy_meta([str(p) for p in proxies])
                self.send_json({"ok": ok, "output": out})
            except json.JSONDecodeError:
                self.send_json({"ok": False, "output": "Invalid JSON"}, 400)
            return

        if path == "/api/proxy/import":
            if not body or not body.strip():
                self.send_json({"ok": False, "output": "Empty file"}, 400)
                return
            imported_proxies = [
                line.strip()
                for line in body.splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False
            ) as f:
                f.write(body)
                tmp = f.name
            try:
                ok, out = run_main(["--import-proxy", tmp])
                if ok:
                    ensure_proxy_meta(imported_proxies)
                self.send_json({"ok": ok, "output": out})
            finally:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass
            return

        if path.startswith("/api/node/") and "/restart-container" in path:
            parts = path.split("/")
            if (
                len(parts) >= 5
                and parts[2] == "node"
                and parts[4] == "restart-container"
            ):
                node_id = parts[3]
                try:
                    data = json.loads(body) if body else {}
                    container = data.get("container") or ""
                    if not container:
                        self.send_json(
                            {"ok": False, "output": "container required"}, 400
                        )
                        return
                    ok, out = run_main(["--container-restart", node_id, container])
                    self.send_json({"ok": ok, "output": out})
                except json.JSONDecodeError:
                    self.send_json({"ok": False, "output": "Invalid JSON"}, 400)
                return

        self.send_json({"error": "Not found"}, 404)


def main():
    cfg = load_config()
    port = int(cfg.get("port") or os.environ.get("PORT", 8765))
    server = HTTPServer(("", port), Handler)
    print(f"Open http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
