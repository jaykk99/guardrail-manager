#!/usr/bin/env python3
"""Guardrail Manager server (Python stdlib only).

Refuses to start without ACCESS_CODE in the environment: the code is set
by the owner at deploy time and is never stored in this repo.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.gitops import GitOps
from app.httpapi import make_server
from app.service import GuardService
from app.source import GhSource
from app.store import Store

BASE = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    access_code = os.environ.get("ACCESS_CODE", "").strip()
    if not access_code:
        print("Refusing to start: ACCESS_CODE env var is not set.", file=sys.stderr)
        return 2
    owner = os.environ.get("GH_OWNER", "jaykk99")
    port = int(os.environ.get("PORT", "8790"))
    host = os.environ.get("HOST", "0.0.0.0")
    data_dir = os.environ.get("GM_DATA_DIR", os.path.join(BASE, "data"))

    store = Store(data_dir)
    gitops = GitOps(
        owner=owner,
        worktrees_dir=os.environ.get(
            "GM_WORKTREES_DIR", os.path.expanduser("~/workspace/wt")),
        clones_dir=os.path.join(data_dir, "clones"),
    )
    service = GuardService(GhSource(owner), store, gitops)
    server = make_server(host, port, service,
                         os.path.join(BASE, "public"), access_code)
    print(f"Guardrail Manager on http://{host}:{port} (owner {owner})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
