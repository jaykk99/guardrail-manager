"""Local JSON store for the app's own data (gitignored data/ dir).

Holds: Jay's template default policy text, the repo scan cache, settings.
Never holds secrets.
"""

from __future__ import annotations

import json
import os
import threading
import time

DEFAULT_TEMPLATE = (
    "{\n"
    '  "entries": []\n'
    "}\n"
)


class Store:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.path = os.path.join(data_dir, "store.json")
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self) -> dict:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {}

    def _save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2)
        os.replace(tmp, self.path)

    # -- template default -------------------------------------------------
    def get_default_template(self) -> str:
        return self._data.get("default_template", DEFAULT_TEMPLATE)

    def set_default_template(self, text: str) -> None:
        with self._lock:
            self._data["default_template"] = text
            self._save()

    # -- scan cache ---------------------------------------------------------
    def get_scan(self, repo: str) -> dict | None:
        return self._data.get("scans", {}).get(repo)

    def set_scan(self, repo: str, scan: dict) -> None:
        with self._lock:
            scans = self._data.setdefault("scans", {})
            scan = dict(scan)
            scan["scanned_at"] = time.time()
            scans[repo] = scan
            self._save()

    def all_scans(self) -> dict:
        return dict(self._data.get("scans", {}))
