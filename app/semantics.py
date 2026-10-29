"""Reference consumer for the deployment policy template semantics.

This mirrors how the platforms treat the owner config: the config is a
soft-policy layer only. An absent file, an empty file, or an empty entry
list means NO soft blocks at all. Entries only ever add soft blocks on top
of the (separate, hardcoded) hard floor, which this module never touches.
"""

from __future__ import annotations

from .classify import parse_entries


def soft_blocks(config_text: str | None, phrase: str) -> bool:
    """True when the soft policy blocks `phrase`. None/empty config: never."""
    if config_text is None:
        return False
    entries = parse_entries(config_text)
    if not entries:
        return False
    low = phrase.lower()
    return any(entry.lower() in low for entry in entries)
