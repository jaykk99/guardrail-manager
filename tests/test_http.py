"""HTTP tests: access-code gate, login, and floor-delete refusal (403)."""

import http.client
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import httpapi
from app.gitops import GitOps
from app.service import GuardService
from app.source import FixtureSource
from app.store import Store
from tests.test_service_gitops import Fixture, CONFIG_V1, CONFIG_V2, FLOOR_CONTENT

CODE = "test-access-code-123"


class Client:
    def __init__(self, port):
        self.port = port
        self.cookie = None

    def call(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        headers = {"Content-Type": "application/json"}
        if self.cookie:
            headers["Cookie"] = self.cookie
        conn.request(method, path,
                     json.dumps(body) if body is not None else None, headers)
        res = conn.getresponse()
        raw = res.read().decode("utf-8")
        set_cookie = res.getheader("Set-Cookie")
        if set_cookie:
            self.cookie = set_cookie.split(";")[0]
        conn.close()
        try:
            return res.status, json.loads(raw)
        except Exception:
            return res.status, raw


class TestHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="gm-http-")
        cls.fx = Fixture(cls.tmp)
        store = Store(os.path.join(cls.tmp, "data"))
        source = FixtureSource({"demo": dict(cls.fx.source_files)})
        gitops = GitOps(owner="jaykk99",
                        worktrees_dir=os.path.join(cls.tmp, "wt"),
                        clones_dir=os.path.join(cls.tmp, "clones"),
                        remote_template=os.path.join(cls.tmp, "{repo}.git"))
        service = GuardService(source, store, gitops)
        public = os.path.join(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))), "public")
        cls.server = httpapi.make_server("127.0.0.1", 0, service, public, CODE)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_ui_loads(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("GET", "/")
        res = conn.getresponse()
        body = res.read().decode("utf-8")
        conn.close()
        self.assertEqual(res.status, 200)
        self.assertIn("Guardrail Manager", body)
        self.assertIn("Deployment policy template", body)
        self.assertIn("hard floor", body.lower())

    def test_auth_gate_and_login(self):
        c = Client(self.port)
        status, _ = c.call("GET", "/api/repos")
        self.assertEqual(status, 401)
        status, _ = c.call("POST", "/api/login", {"code": "wrong"})
        self.assertEqual(status, 401)
        status, data = c.call("POST", "/api/login", {"code": CODE})
        self.assertEqual(status, 200)
        status, data = c.call("GET", "/api/repos")
        self.assertEqual(status, 200)
        names = [r["name"] for r in data["repos"]]
        self.assertIn("demo", names)

    def test_floor_delete_over_http_is_403(self):
        c = Client(self.port)
        c.call("POST", "/api/login", {"code": CODE})
        status, data = c.call("POST", "/api/repos/demo/delete",
                              {"path": "app/refusal.py"})
        self.assertEqual(status, 403)
        self.assertIn("hard floor", data["error"].lower())
        self.assertEqual(self.fx.remote_file("app/refusal.py"), FLOOR_CONTENT)

    def test_config_save_over_http(self):
        c = Client(self.port)
        c.call("POST", "/api/login", {"code": CODE})
        status, data = c.call("POST", "/api/repos/demo/save",
                              {"path": "guardrails.owner.json",
                               "content": CONFIG_V2})
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(self.fx.remote_file("guardrails.owner.json"),
                         CONFIG_V2)


class TestStartupGate(unittest.TestCase):
    def test_server_refuses_without_access_code(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env = {k: v for k, v in os.environ.items() if k != "ACCESS_CODE"}
        proc = subprocess.run([sys.executable, os.path.join(root, "server.py")],
                              capture_output=True, text=True, env=env,
                              timeout=30)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("ACCESS_CODE", proc.stderr)


if __name__ == "__main__":
    unittest.main()
