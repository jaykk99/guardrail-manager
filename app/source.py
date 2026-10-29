"""Repo content sources.

GhSource reads jaykk99's repos through the authenticated `gh` CLI.
FixtureSource serves an in-memory repo set for tests and local dry runs.
"""

from __future__ import annotations

import base64
import json
import subprocess


def _run(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


class GhSource:
    def __init__(self, owner: str = "jaykk99"):
        self.owner = owner

    def list_repos(self) -> list[dict]:
        proc = _run(["gh", "repo", "list", self.owner, "--limit", "300",
                     "--json", "name,description,isPrivate"])
        if proc.returncode != 0:
            raise RuntimeError(f"gh repo list failed: {proc.stderr.strip()[:300]}")
        repos = json.loads(proc.stdout or "[]")
        return [{"name": r["name"], "description": r.get("description") or "",
                 "private": bool(r.get("isPrivate"))} for r in repos]

    def list_paths(self, repo: str) -> list[str]:
        proc = _run(["gh", "api", f"repos/{self.owner}/{repo}/git/trees/HEAD",
                     "--method", "GET", "-f", "recursive=1"], timeout=90)
        if proc.returncode != 0:
            raise RuntimeError(f"gh tree failed for {repo}: {proc.stderr.strip()[:300]}")
        tree = json.loads(proc.stdout or "{}")
        return [item["path"] for item in tree.get("tree", [])
                if item.get("type") == "blob"]

    def get_file(self, repo: str, path: str) -> str | None:
        proc = _run(["gh", "api", f"repos/{self.owner}/{repo}/contents/{path}"],
                    timeout=60)
        if proc.returncode != 0:
            return None
        data = json.loads(proc.stdout or "{}")
        if data.get("encoding") == "base64" and data.get("content"):
            return base64.b64decode(data["content"]).decode("utf-8", "replace")
        return None


class FixtureSource:
    """repos: {name: {path: content}}"""

    def __init__(self, repos: dict[str, dict[str, str]]):
        self.repos = repos

    def list_repos(self) -> list[dict]:
        return [{"name": name, "description": "fixture", "private": False}
                for name in sorted(self.repos)]

    def list_paths(self, repo: str) -> list[str]:
        return sorted(self.repos.get(repo, {}))

    def get_file(self, repo: str, path: str) -> str | None:
        return self.repos.get(repo, {}).get(path)
