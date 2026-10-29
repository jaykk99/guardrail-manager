import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import classify


class TestClassifier(unittest.TestCase):
    def kind(self, repo, path, content=""):
        result = classify.classify(repo, path, content)
        return result[0] if result else None

    def test_json_list_config_is_config(self):
        self.assertEqual(
            self.kind("some-repo", "guardrails.owner.json", '["spam", "scam"]'),
            "config")

    def test_json_object_config_is_config(self):
        self.assertEqual(
            self.kind("some-repo", "config/refusal-policy.json",
                      '{"entries": ["x"]}'),
            "config")

    def test_line_list_config_is_config(self):
        self.assertEqual(
            self.kind("some-repo", "guardrails.txt", "spam\nscam\n# note\n"),
            "config")

    def test_error_inbox_hard_block_is_floor(self):
        content = ("// Deterministic hard-block for the build path: malware, "
                   "phishing / credential theft, stolen cards, CSAM.")
        self.assertEqual(
            self.kind("error-inbox", "lib/safety/hard-block.ts", content),
            "floor")

    def test_bro_agent_refusal_is_floor(self):
        self.assertEqual(
            self.kind("bro-agent", "app/refusal.py", "GUARDS = []"), "floor")

    def test_bro_agent_guards_shim_is_floor(self):
        self.assertEqual(
            self.kind("bro-agent", "app/guards.py", "# shim"), "floor")

    def test_harness_guards_is_floor(self):
        self.assertEqual(
            self.kind("uncensored-harness", "app/guards.py", "_BOUNDARIES = []"),
            "floor")

    def test_termux_refusal_is_detector_not_blocklist(self):
        result = classify.classify(
            "termux-code", "lib/refusal.mjs",
            "export function isRefusalReply(t) { return false; }")
        self.assertEqual(result[0], "detector")
        self.assertIn("not a block list", result[1].lower())

    def test_unseeded_floor_content_code_is_floor(self):
        content = "def check_hard_boundary(x):\n    # stolen card, csam\n    pass"
        self.assertEqual(
            self.kind("other-repo", "app/refusal.py", content), "floor")

    def test_python_list_file_is_code_not_config(self):
        # A .py file is code even if it holds a list: view-only, never config.
        self.assertNotEqual(
            self.kind("other-repo", "app/guardrails.py", 'BLOCKED = ["x"]'),
            "config")

    def test_unrelated_file_ignored(self):
        self.assertIsNone(classify.classify("r", "src/index.ts", "hello"))

    def test_test_files_are_view_only(self):
        self.assertEqual(
            self.kind("bro-agent", "tests/test_guards.py", "def test_x(): pass"),
            "test")


class TestEntries(unittest.TestCase):
    def test_parse_json_forms(self):
        self.assertEqual(classify.parse_entries('["a", "b"]'), ["a", "b"])
        self.assertEqual(classify.parse_entries('{"entries": ["a"]}'), ["a"])
        self.assertEqual(classify.parse_entries('{"blocklist": ["z"]}'), ["z"])
        self.assertEqual(classify.parse_entries(""), [])
        self.assertEqual(classify.parse_entries("{}"), [])

    def test_parse_lines(self):
        self.assertEqual(classify.parse_entries("a\n# note\nb\n"), ["a", "b"])

    def test_add_remove_round_trip(self):
        content = '{\n  "entries": []\n}\n'
        content = classify.add_entry(content, "spam")
        self.assertEqual(classify.parse_entries(content), ["spam"])
        content = classify.add_entry(content, "spam")  # no dupes
        self.assertEqual(classify.parse_entries(content), ["spam"])
        content = classify.remove_entry(content, "spam")
        self.assertEqual(classify.parse_entries(content), [])

    def test_clear_keeps_shape(self):
        cleared = classify.clear_entries('{"entries": ["a"], "other": 1}')
        data = classify.json.loads(cleared)
        self.assertEqual(data["entries"], [])
        self.assertEqual(data["other"], 1)
        self.assertEqual(classify.clear_entries('["a"]'), "[]\n")


if __name__ == "__main__":
    unittest.main()
