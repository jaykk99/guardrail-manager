"""HTTP API + access-code gate.

Auth: POST /api/login with the ACCESS_CODE returns a random session token
in an HttpOnly cookie. Every other /api/* route requires that session.
The code itself is only ever compared, never stored or logged.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from .service import GuardService

SESSIONS: set[str] = set()
ACCESS_CODE = ""  # set by server.py from env before serving


def _check_code(code: str) -> bool:
    return bool(ACCESS_CODE) and hmac.compare_digest(code or "", ACCESS_CODE)


class Handler(BaseHTTPRequestHandler):
    service: GuardService = None  # injected by make_server
    public_dir: str = ""

    # -- helpers ------------------------------------------------------------
    def log_message(self, *args):  # keep stdout clean
        pass

    def _send(self, status: int, body, ctype: str = "application/json",
              extra_headers: dict | None = None):
        if isinstance(body, (dict, list)):
            raw = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            raw = body.encode("utf-8")
        else:
            raw = body or b""
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if raw:
            self.wfile.write(raw)

    def _authed(self) -> bool:
        cookie = self.headers.get("Cookie") or ""
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith("gm_session="):
                return part[len("gm_session="):] in SESSIONS
        return False

    def _json_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    # -- routing --------------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/" or path == "/index.html":
            return self._static()
        if not path.startswith("/api/"):
            return self._send(404, {"error": "not found"})
        if not self._authed():
            return self._send(401, {"error": "sign in required"})
        qs = parse_qs(parsed.query)
        try:
            if path == "/api/repos":
                rescan = qs.get("rescan", ["0"])[0] == "1"
                return self._send(200, {"repos": self.service.list_repos(rescan)})
            if path == "/api/default":
                return self._send(200, {"text": self.service.get_default()})
            if path.startswith("/api/repos/"):
                parts = path.split("/")
                repo = parts[3]
                if len(parts) == 5 and parts[4] == "file":
                    fpath = qs.get("path", [""])[0]
                    return self._send(200, self.service.get_file(repo, fpath))
                if len(parts) == 4:
                    return self._send(200, self.service.scan_repo(repo))
            return self._send(404, {"error": "not found"})
        except LookupError as exc:
            return self._send(404, {"error": str(exc)})
        except Exception as exc:
            return self._send(500, {"error": str(exc)[:400]})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._json_body()
        if path == "/api/login":
            if _check_code(str(body.get("code", ""))):
                token = secrets.token_urlsafe(32)
                SESSIONS.add(token)
                return self._send(200, {"ok": True}, extra_headers={
                    "Set-Cookie": f"gm_session={token}; HttpOnly; Path=/; "
                                  f"SameSite=Lax; Max-Age=2592000"})
            return self._send(401, {"error": "wrong access code"})
        if not path.startswith("/api/"):
            return self._send(404, {"error": "not found"})
        if not self._authed():
            return self._send(401, {"error": "sign in required"})
        try:
            if path == "/api/default":
                self.service.set_default(str(body.get("text", "")))
                return self._send(200, {"ok": True})
            if path.startswith("/api/repos/"):
                parts = path.split("/")
                repo = parts[3]
                action = parts[4] if len(parts) > 4 else ""
                if action == "save":
                    return self._send(200, self.service.save_config(
                        repo, str(body.get("path", "")),
                        str(body.get("content", ""))))
                if action == "delete":
                    return self._send(200, self.service.delete_config(
                        repo, str(body.get("path", ""))))
                if action == "apply-default":
                    return self._send(200, self.service.apply_default(repo))
                if action == "add-entry":
                    return self._send(200, self.service.add_entry(
                        repo, str(body.get("path", "")),
                        str(body.get("entry", ""))))
                if action == "remove-entry":
                    return self._send(200, self.service.remove_entry(
                        repo, str(body.get("path", "")),
                        str(body.get("entry", ""))))
                if action == "clear-entries":
                    return self._send(200, self.service.clear_entries(
                        repo, str(body.get("path", ""))))
                if action == "create-config":
                    return self._send(200, self.service.create_config(repo))
            return self._send(404, {"error": "not found"})
        except PermissionError as exc:
            return self._send(403, {"error": str(exc)})
        except LookupError as exc:
            return self._send(404, {"error": str(exc)})
        except Exception as exc:
            return self._send(500, {"error": str(exc)[:400]})

    def _static(self):
        index = os.path.join(self.public_dir, "index.html")
        try:
            with open(index, "rb") as fh:
                raw = fh.read()
        except Exception:
            return self._send(500, "UI missing", "text/plain")
        return self._send(200, raw, "text/html; charset=utf-8")


def make_server(host: str, port: int, service: GuardService,
                public_dir: str, access_code: str) -> ThreadingHTTPServer:
    global ACCESS_CODE
    ACCESS_CODE = access_code
    Handler.service = service
    Handler.public_dir = public_dir
    return ThreadingHTTPServer((host, port), Handler)
