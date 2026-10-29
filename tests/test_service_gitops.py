"""End-to-end service tests against a local bare git fixture.

Covers: editor save round-trip (commit lands on the remote), create config,
delete config, and the hard rule: any write/delete attempt on a hard-floor
file is refused by the service and changes nothing.
"""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.gitops import GitOps
from app.service import GuardService
from app.source import FixtureSource
from app.store import Store

CONFIG_V1 = '{\n  "entries": ["spam"]\n}\n'
CONFIG_V2 = '{\n  "entries": ["spam", "scam"]\n}\n'
FLOOR_CONTENT = "# hard floor: stolen card, csam, check_hard_boundary\n"


def sh(args, cwd=None):
    proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    assert proc.returncode == 0, f"{args}: {proc.stderr}"
    return proc.stdout.strip()


class Fixture:
    """A bare 'remote' repo plus a FixtureSource mirroring its content."""

    def __init__(self, tmp: str):
        self.tmp = tmp
        self.remote = os.path.join(tmp, "demo.git")
        sh(["git", "init", "--bare", "--quiet", "-b", "main", self.remote])
        seed = os.path.join(tmp, "seed")
        sh(["git", "clone", "--quiet", self.remote, seed])
        self.write(seed, "guardrails.owner.json", CONFIG_V1)
        os.makedirs(os.path.join(seed, "app"), exist_ok=True)
        self.write(seed, "app/refusal.py", FLOOR_CONTENT)
        sh(["git", "add", "-A"], cwd=seed)
        sh(["git", "-c", "user.name=T", "-c", "user.email=t@t",
            "commit", "--quiet", "-m", "seed"], cwd=seed)
        sh(["git", "push", "--quiet", "origin", "main"], cwd=seed)
        self.source_files = {
            "guardrails.owner.json": CONFIG_V1,
            "app/refusal.py": FLOOR_CONTENT,
        }

    @staticmethod
    def write(root, rel, content):
        dest = os.path.join(root, rel)
        os.makedirs(os.path.dirname(dest) or root, exist_ok=True)
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(content)

    def remote_file(self, rel):
        proc = subprocess.run(
            ["git", "--git-dir", self.remote, "show", f"main:{rel}"],
            capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        return proc.stdout

    def remote_has(self, rel) -> bool:
        proc = subprocess.run(
            ["git", "--git-dir", self.remote, "cat-file", "-e", f"main:{rel}"],
            capture_output=True, text=True)
        return proc.returncode == 0


class TestServiceGitOps(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gm-test-")
        self.fx = Fixture(self.tmp)
        store = Store(os.path.join(self.tmp, "data"))
        source = FixtureSource({"demo": dict(self.fx.source_files)})
        gitops = GitOps(owner="jaykk99",
                        worktrees_dir=os.path.join(self.tmp, "wt"),
                        clones_dir=os.path.join(self.tmp, "clones"),
                        remote_template=os.path.join(self.tmp, "{repo}.git"))
        self.service = GuardService(source, store, gitops)

    def test_scan_classifies(self):
        scan = self.service.scan_repo("demo")
        kinds = {f["path"]: f["kind"] for f in scan["files"]}
        self.assertEqual(kinds["guardrails.owner.json"], "config")
        self.assertEqual(kinds["app/refusal.py"], "floor")
        self.assertEqual(scan["status"], "config")

    def test_save_round_trip(self):
        result = self.service.save_config(
            "demo", "guardrails.owner.json", CONFIG_V2)
        self.assertTrue(result["ok"])
        self.assertEqual(self.fx.remote_file("guardrails.owner.json"), CONFIG_V2)
        head = sh(["git", "--git-dir", self.fx.remote, "rev-parse", "main"])
        self.assertEqual(result["commit"], head)

    def test_second_save_same_repo(self):
        # Regression: re-entering an existing worktree must not try to check
        # out the branch by name (the clone already holds that checkout).
        self.service.save_config("demo", "guardrails.owner.json", CONFIG_V2)
        result = self.service.save_config(
            "demo", "guardrails.owner.json", CONFIG_V1)
        self.assertTrue(result["ok"])
        self.assertEqual(self.fx.remote_file("guardrails.owner.json"),
                         CONFIG_V1)

    def test_delete_config(self):
        result = self.service.delete_config("demo", "guardrails.owner.json")
        self.assertTrue(result["ok"])
        self.assertFalse(self.fx.remote_has("guardrails.owner.json"))

    def test_floor_delete_refused_and_unchanged(self):
        before = sh(["git", "--git-dir", self.fx.remote, "rev-parse", "main"])
        with self.assertRaises(PermissionError):
            self.service.delete_config("demo", "app/refusal.py")
        with self.assertRaises(PermissionError):
            self.service.save_config("demo", "app/refusal.py", "# wiped\n")
        after = sh(["git", "--git-dir", self.fx.remote, "rev-parse", "main"])
        self.assertEqual(before, after)
        self.assertEqual(self.fx.remote_file("app/refusal.py"), FLOOR_CONTENT)

    def test_code_path_write_refused(self):
        with self.assertRaises(PermissionError):
            self.service.save_config("demo", "app/main.py", "x = 1\n")

    def test_create_config_from_default(self):
        # A second fixture repo with a remote but no policy file yet.
        remote = os.path.join(self.tmp, "fresh.git")
        sh(["git", "init", "--bare", "--quiet", "-b", "main", remote])
        seed = os.path.join(self.tmp, "seed-fresh")
        sh(["git", "clone", "--quiet", remote, seed])
        self.fx.write(seed, "README.md", "# fresh\n")
        sh(["git", "add", "-A"], cwd=seed)
        sh(["git", "-c", "user.name=T", "-c", "user.email=t@t",
            "commit", "--quiet", "-m", "seed"], cwd=seed)
        sh(["git", "push", "--quiet", "origin", "main"], cwd=seed)

        result = self.service.create_config("fresh")
        self.assertTrue(result["ok"])
        self.assertEqual(result["path"], "guardrails.owner.json")
        content = sh(["git", "--git-dir", remote, "show",
                      "main:guardrails.owner.json"])
        self.assertEqual(content + "\n",
                         self.service.get_default())


if __name__ == "__main__":
    unittest.main()
