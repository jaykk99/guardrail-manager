"""Code-embedded template (error-inbox lib/guard-policy.ts) tests.

The entry lists are the owner config and are editable; raw save and delete
of the module itself are refused, and entry rewrites must leave every other
byte of the module alone.
"""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import classify
from app.gitops import GitOps
from app.service import GuardService
from app.source import FixtureSource
from app.store import Store
from tests.test_service_gitops import sh

TS_V1 = (
    "/** guard-policy: owner soft policy */\n"
    "export const OWNER_REFUSAL_PATTERNS: readonly string[] = [];\n"
    "export const OWNER_BLOCKED_CHAT_TOOLS: readonly string[] = [\n"
    "  'send_money',\n"
    "];\n"
    "export function softRefusalBlocked(x: string) { return false; }\n"
)
SENTINEL = "export function softRefusalBlocked(x: string) { return false; }"


class TestEmbeddedClassify(unittest.TestCase):
    def test_classified_as_config(self):
        result = classify.classify("error-inbox", "lib/guard-policy.ts", TS_V1)
        self.assertEqual(result[0], "config")
        self.assertTrue(classify.is_embedded_config(
            "error-inbox", "lib/guard-policy.ts"))

    def test_parse_and_lists(self):
        self.assertEqual(classify.parse_entries(TS_V1), [])
        lists = classify.embedded_lists(TS_V1)
        self.assertEqual(lists["OWNER_BLOCKED_CHAT_TOOLS"], ["send_money"])

    def test_set_list_preserves_rest_of_file(self):
        out = classify.set_embedded_list(TS_V1, "OWNER_REFUSAL_PATTERNS",
                                         ["spam", "scam"])
        self.assertIn(SENTINEL, out)
        self.assertIn("'send_money'", out)
        self.assertEqual(classify.parse_entries(out), ["spam", "scam"])
        out2 = classify.set_embedded_list(out, "OWNER_REFUSAL_PATTERNS", [])
        self.assertEqual(classify.parse_entries(out2), [])
        self.assertIn(SENTINEL, out2)

    def test_add_remove_clear(self):
        out = classify.add_entry(TS_V1, "spam")
        self.assertEqual(classify.parse_entries(out), ["spam"])
        out = classify.remove_entry(out, "spam")
        self.assertEqual(classify.parse_entries(out), [])
        out = classify.add_entry(TS_V1, "x")
        out = classify.clear_entries(out)
        self.assertEqual(classify.parse_entries(out), [])
        self.assertEqual(classify.embedded_lists(out)
                         ["OWNER_BLOCKED_CHAT_TOOLS"], [])
        self.assertIn(SENTINEL, out)


class TestEmbeddedService(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gm-emb-")
        self.remote = os.path.join(self.tmp, "error-inbox.git")
        sh(["git", "init", "--bare", "--quiet", "-b", "main", self.remote])
        seed = os.path.join(self.tmp, "seed")
        sh(["git", "clone", "--quiet", self.remote, seed])
        os.makedirs(os.path.join(seed, "lib"), exist_ok=True)
        with open(os.path.join(seed, "lib", "guard-policy.ts"), "w") as fh:
            fh.write(TS_V1)
        sh(["git", "add", "-A"], cwd=seed)
        sh(["git", "-c", "user.name=T", "-c", "user.email=t@t",
            "commit", "--quiet", "-m", "seed"], cwd=seed)
        sh(["git", "push", "--quiet", "origin", "main"], cwd=seed)
        source = FixtureSource({"error-inbox": {"lib/guard-policy.ts": TS_V1}})
        gitops = GitOps(owner="jaykk99",
                        worktrees_dir=os.path.join(self.tmp, "wt"),
                        clones_dir=os.path.join(self.tmp, "clones"),
                        remote_template=os.path.join(self.tmp, "{repo}.git"))
        self.service = GuardService(source,
                                    Store(os.path.join(self.tmp, "data")),
                                    gitops)

    def remote_content(self):
        proc = subprocess.run(
            ["git", "--git-dir", self.remote, "show",
             "main:lib/guard-policy.ts"], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        return proc.stdout

    def test_add_entry_pushes_and_preserves_code(self):
        result = self.service.add_entry(
            "error-inbox", "lib/guard-policy.ts", "spam")
        self.assertTrue(result["ok"])
        content = self.remote_content()
        self.assertEqual(classify.parse_entries(content), ["spam"])
        self.assertIn(SENTINEL, content)

    def test_raw_save_and_delete_refused(self):
        before = self.remote_content()
        with self.assertRaises(PermissionError):
            self.service.save_config(
                "error-inbox", "lib/guard-policy.ts", "// wiped\n")
        with self.assertRaises(PermissionError):
            self.service.delete_config("error-inbox", "lib/guard-policy.ts")
        self.assertEqual(self.remote_content(), before)


if __name__ == "__main__":
    unittest.main()
