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
import os
import subprocess
import tempfile
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_SH = os.path.join(ROOT, "main.sh")
PROXY_FILE = os.path.join(ROOT, "proxies.txt")
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
            timeout=120,
        )
        out = (r.stdout or "") + (r.stderr or "")
        return r.returncode == 0, out.strip()
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as e:
        return False, str(e)


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
                self.send_json({"ok": True, "user": user} if user else {"ok": False}, 200 if user else 401)
                return

        if path == "/api/nodes":
            ok, out = run_main(["--list-nodes"])
            nodes = parse_list_nodes(out) if ok else []
            for n in nodes:
                meta = read_node_meta(n["id"])
                n["meta"] = meta
            self.send_json({"nodes": nodes, "raw": out})
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
                ok, out = run_main(["--container-logs", node_id, container, "--tail", str(tail)])
                self.send_text(out)
                return
        if path == "/api/proxies":
            self.send_json({"proxies": read_proxies()})
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
                password = (data.get("password") or "")
                cfg = self._config()
                if not username or cfg.get("username") != username or cfg.get("password") != password:
                    self.send_json({"ok": False, "error": "Invalid username or password"}, 401)
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
                self.wfile.write(json.dumps({"ok": True, "user": username}).encode("utf-8"))
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
                self.send_json({"ok": ok, "output": out})
            except json.JSONDecodeError:
                self.send_json({"ok": False, "output": "Invalid JSON"}, 400)
            return

        if path == "/api/proxy/add":
            try:
                data = json.loads(body) or {}
                proxies = data.get("proxies") or []
                if not proxies:
                    self.send_json({"ok": False, "output": "No proxies"}, 400)
                    return
                ok, out = run_main(["--add-proxy"] + [str(p) for p in proxies])
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
                self.send_json({"ok": ok, "output": out})
            except json.JSONDecodeError:
                self.send_json({"ok": False, "output": "Invalid JSON"}, 400)
            return

        if path == "/api/proxy/import":
            if not body or not body.strip():
                self.send_json({"ok": False, "output": "Empty file"}, 400)
                return
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
                f.write(body)
                tmp = f.name
            try:
                ok, out = run_main(["--import-proxy", tmp])
                self.send_json({"ok": ok, "output": out})
            finally:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass
            return

        if path.startswith("/api/node/") and "/restart-container" in path:
            parts = path.split("/")
            if len(parts) >= 5 and parts[2] == "node" and parts[4] == "restart-container":
                node_id = parts[3]
                try:
                    data = json.loads(body) if body else {}
                    container = data.get("container") or ""
                    if not container:
                        self.send_json({"ok": False, "output": "container required"}, 400)
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
