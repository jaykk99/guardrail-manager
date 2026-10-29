import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.semantics import soft_blocks


class TestEmptyConfigSemantics(unittest.TestCase):
    """Absent/empty deployment policy template means NO soft blocks."""

    def test_absent_config_never_blocks(self):
        self.assertFalse(soft_blocks(None, "anything at all"))

    def test_empty_file_never_blocks(self):
        self.assertFalse(soft_blocks("", "anything at all"))
        self.assertFalse(soft_blocks('{"entries": []}', "anything at all"))
        self.assertFalse(soft_blocks("[]", "anything at all"))

    def test_entry_blocks_matching_phrase(self):
        self.assertTrue(soft_blocks('{"entries": ["spam"]}', "this is Spam"))
        self.assertFalse(soft_blocks('{"entries": ["spam"]}', "clean text"))


if __name__ == "__main__":
    unittest.main()
