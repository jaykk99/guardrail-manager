"""Classification of refusal/guard artifacts found in a repo.

Classes:
  - "config":   deployment policy template file (data/config). Editable.
  - "floor":    hard-floor code. View-only, never editable/deletable here.
  - "detector": refusal DETECTOR / skip logic (not a block list). View-only.
  - "code":     other guard-adjacent code. View-only.
  - "test":     test files. View-only.
  - None:       not a guard artifact, ignored by the scanner.

Rule from the design brief: a file is OWNER CONFIG only if it is data/config
(lists / JSON / env-style policy). Code files are always view-only. When in
doubt, a file is treated as floor (view-only), never as config.
"""

from __future__ import annotations

import json
import os
import re

NAME_RE = re.compile(r"(refus|guard|polic|hard[-_]?block|safety)", re.IGNORECASE)

DATA_EXTS = {".json", ".yaml", ".yml", ".txt", ".list", ".cfg", ".ini", ".env"}
CODE_EXTS = {
    ".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".go", ".rs", ".java",
    ".rb", ".php", ".sh", ".ps1",
}

# Paths that are the canonical deployment policy template in a repo. The app
# creates the config at CANONICAL_CONFIG_PATH when a repo has none yet.
CANONICAL_CONFIG_PATH = "guardrails.owner.json"
CONFIG_CANDIDATE_PATHS = [
    CANONICAL_CONFIG_PATH,
    "guard-policy.json",
    "guardrails.json",
    "config/guardrails.json",
    "config/guard-policy.json",
    "lib/guard-policy.json",
    "app/guard-policy.json",
    "owner-guardrails.json",
    "refusal-policy.json",
    "lib/refusal-policy.json",
    "config/refusal-policy.json",
]

# Seed registry: exact repo/path -> forced classification. Built from the
# known state of Jay's agent platforms (verified 2026-10-29).
SEED = {
    "error-inbox": {
        "lib/safety/hard-block.ts": ("floor", "hard floor: deterministic hard-block gate"),
        "lib/safety.ts": ("floor", "hard floor: safety gate"),
        "lib/refusal-settings.ts": ("code", "owner refusal toggles module (code, values live in the app DB)"),
        "lib/llm/refusal-detect.ts": ("detector", "refusal detector: model refusals are skipped to the next model"),
    },
    "bro-agent": {
        "app/refusal.py": ("floor", "hard floor: the 7 hard-boundary guards (ported from Error Inbox)"),
        "app/guards.py": ("floor", "hard floor: re-export shim for app/refusal.py"),
    },
    "uncensored-harness": {
        "app/guards.py": ("floor", "hard floor: narrow hard-boundary pre-check"),
        "guards.py": ("floor", "hard floor: narrow hard-boundary pre-check"),
    },
    "termux-code": {
        "lib/refusal.mjs": ("detector", "refusal DETECTOR / skip logic: a model refusal counts as a failed attempt and the chain moves on. Not a block list."),
    },
}

# Content signals that mark a code file as hard floor even without a seed.
FLOOR_CONTENT_SIGNALS = [
    "hard-block", "hard_block", "hard boundary", "hard-boundary",
    "check_hard_boundary", "stolen card", "csam", "wallet theft",
    "doxxing", "weapons of mass harm",
]
DETECTOR_CONTENT_SIGNALS = [
    "isrefusal", "is_refusal", "refusal-detect", "refusal detect",
    "treatasrefusal", "treat_as_refusal", "skip_refusing",
]

# JSON keys that commonly hold the entry list inside an object-shaped config.
ENTRY_KEYS = ["blocklist", "block_list", "entries", "rules", "patterns",
              "blocked", "deny", "denylist", "deny_list", "phrases"]

# Code-embedded templates: the deployment policy lives in designated exported
# entry lists inside one code module (the guard-policy pass's design for
# error-inbox). For these files the ENTRY LISTS are the owner config and are
# editable; the surrounding code is not raw-editable or deletable from this
# app (the host app imports the module; deleting it would break the build,
# and the floor lives in other files regardless).
EMBEDDED_SEED = {("error-inbox", "lib/guard-policy.ts")}
EMBEDDED_LIST_NAMES = ["OWNER_REFUSAL_PATTERNS", "OWNER_BLOCKED_CHAT_TOOLS"]
_ARRAY_RE = re.compile(
    r"(export const (OWNER_REFUSAL_PATTERNS|OWNER_BLOCKED_CHAT_TOOLS)\b[^=]*=\s*)"
    r"\[(.*?)\]\s*;", re.DOTALL)
_STR_RE = re.compile(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"")


def is_embedded_config(repo: str, path: str) -> bool:
    return (repo, path) in EMBEDDED_SEED


def embedded_lists(content: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for match in _ARRAY_RE.finditer(content or ""):
        entries = []
        for sm in _STR_RE.finditer(match.group(3)):
            entries.append(sm.group(1) if sm.group(1) is not None else sm.group(2))
        out[match.group(2)] = entries
    return out


def set_embedded_list(content: str, name: str, entries: list[str]) -> str:
    """Rewrite one embedded entry list, leaving all other code untouched."""
    def repl(match: re.Match) -> str:
        if match.group(2) != name:
            return match.group(0)
        if not entries:
            return match.group(1) + "[];"
        inner = ",\n  ".join(
            "'" + e.replace("\\", "\\\\").replace("'", "\\'") + "'"
            for e in entries)
        return match.group(1) + "[\n  " + inner + ",\n];"
    new, count = _ARRAY_RE.subn(repl, content or "")
    if count == 0:
        raise ValueError(f"embedded list {name} not found")
    return new


def is_candidate_path(path: str) -> bool:
    base = os.path.basename(path)
    if "/tests/" in path or path.startswith("tests/") or "/test/" in path:
        return bool(NAME_RE.search(base))
    return bool(NAME_RE.search(base)) or path in CONFIG_CANDIDATE_PATHS


def _looks_like_data(content: str) -> bool:
    """True when the content reads as data/config, not source code."""
    text = content.strip()
    if not text:
        return True  # empty file: treat as data (empty config = no blocks)
    if text[0] in "[{":
        try:
            json.loads(text)
            return True
        except Exception:
            return False
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return True
    codey = 0
    for ln in lines:
        if ln.startswith("#") or ln.startswith("//"):
            continue
        if re.match(r"^[A-Za-z0-9_\-\.\*\/ ]+$", ln):  # bare entry line
            continue
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*=\s*\S+$", ln):  # KEY=value
            continue
        if ln.endswith((": ", ":", ",")) and (" " in ln or "=" in ln):
            continue  # yaml-ish
        codey += 1
    return codey == 0


def classify(repo: str, path: str, content: str | None) -> tuple[str, str] | None:
    """Return (kind, label) or None when the file is not a guard artifact."""
    base = os.path.basename(path)
    if not is_candidate_path(path):
        return None
    ext = os.path.splitext(base)[1].lower()

    seed = SEED.get(repo, {}).get(path)
    if seed:
        return seed

    if is_embedded_config(repo, path):
        return ("config",
                "deployment policy template (owner entry lists in this code "
                "module; lists editable, module itself view-only)")

    if "/tests/" in path or path.startswith("tests/") or base.startswith("test_") \
            or base.endswith((".test.ts", ".test.js", ".test.mjs", ".test.py")):
        return ("test", "test file (view-only)")

    text = content or ""
    low = text.lower()

    if ext in DATA_EXTS and _looks_like_data(text):
        return ("config", "deployment policy template (owner config)")

    if ext in CODE_EXTS or ext not in DATA_EXTS:
        if any(sig in low for sig in DETECTOR_CONTENT_SIGNALS) and "refus" in base.lower():
            return ("detector", "refusal detector / skip logic (not a block list)")
        if any(sig in low for sig in FLOOR_CONTENT_SIGNALS):
            return ("floor", "hard floor (content matches hard-boundary checks)")
        return ("code", "guard-adjacent code (view-only)")

    # Data extension but content did not parse as data: when unsure, floor.
    return ("floor", "unclassified guard file: treated as hard floor (view-only)")


def is_config_path(repo: str, path: str) -> bool:
    """True when a path is an allowed write target (existing or new config)."""
    if path in CONFIG_CANDIDATE_PATHS:
        return True
    ext = os.path.splitext(path)[1].lower()
    return ext in DATA_EXTS and bool(NAME_RE.search(os.path.basename(path)))


# ---------------------------------------------------------------- entries --

def _is_embedded_content(content: str) -> bool:
    return "OWNER_REFUSAL_PATTERNS" in (content or "") and \
        "export const" in (content or "")


def parse_entries(content: str) -> list[str]:
    """Extract the entry list from a config file's content."""
    if _is_embedded_content(content):
        return embedded_lists(content).get("OWNER_REFUSAL_PATTERNS", [])
    text = (content or "").strip()
    if not text:
        return []
    if text[0] in "[{":
        try:
            data = json.loads(text)
        except Exception:
            return []
        if isinstance(data, list):
            return [str(x) for x in data]
        if isinstance(data, dict):
            for key in ENTRY_KEYS:
                val = data.get(key)
                if isinstance(val, list):
                    return [str(x) for x in val]
            return []
        return []
    entries = []
    for ln in text.splitlines():
        s = ln.strip()
        if s and not s.startswith("#") and not s.startswith("//"):
            entries.append(s)
    return entries


def _dump_entries_like(original: str, entries: list[str]) -> str:
    """Rewrite content with a new entry list, keeping the original shape."""
    text = (original or "").strip()
    if text.startswith("["):
        return json.dumps(entries, indent=2) + "\n"
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except Exception:
            data = {}
        if isinstance(data, dict):
            for key in ENTRY_KEYS:
                if isinstance(data.get(key), list):
                    data[key] = entries
                    return json.dumps(data, indent=2) + "\n"
            data["entries"] = entries
            return json.dumps(data, indent=2) + "\n"
    if not entries:
        return ""
    return "\n".join(entries) + "\n"


def add_entry(content: str, entry: str) -> str:
    if _is_embedded_content(content):
        entries = parse_entries(content)
        if entry not in entries:
            entries.append(entry)
        return set_embedded_list(content, "OWNER_REFUSAL_PATTERNS", entries)
    entries = parse_entries(content)
    if entry not in entries:
        entries.append(entry)
    return _dump_entries_like(content, entries)


def remove_entry(content: str, entry: str) -> str:
    if _is_embedded_content(content):
        entries = [e for e in parse_entries(content) if e != entry]
        return set_embedded_list(content, "OWNER_REFUSAL_PATTERNS", entries)
    entries = [e for e in parse_entries(content) if e != entry]
    return _dump_entries_like(content, entries)


def clear_entries(content: str) -> str:
    """Empty the entry list, keeping the file and its shape. Zero = no blocks."""
    if _is_embedded_content(content):
        out = set_embedded_list(content, "OWNER_REFUSAL_PATTERNS", [])
        return set_embedded_list(out, "OWNER_BLOCKED_CHAT_TOOLS", [])
    return _dump_entries_like(content, [])
