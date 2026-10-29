"""GuardService: scan, read, and (config-only) write operations.

Permission rule enforced HERE, server-side, never trusting the client:
write/delete is allowed only for files classified as the deployment
policy template (owner config). Hard-floor, detector, code and test files
raise PermissionError on any write attempt. There is no code path in this
app that edits or deletes a floor file.
"""

from __future__ import annotations

import os

from . import classify
from .gitops import GitOps
from .source import GhSource
from .store import Store


class GuardService:
    def __init__(self, source, store: Store, gitops: GitOps | None,
                 template_path: str = classify.CANONICAL_CONFIG_PATH):
        self.source = source
        self.store = store
        self.gitops = gitops
        self.template_path = template_path

    # -- scanning ---------------------------------------------------------
    def scan_repo(self, repo: str) -> dict:
        files = []
        try:
            paths = self.source.list_paths(repo)
        except Exception as exc:  # empty repo, no HEAD, etc.
            scan = {"repo": repo, "status": "none", "files": [],
                    "error": str(exc)[:200]}
            self.store.set_scan(repo, scan)
            return scan
        for path in paths:
            if not classify.is_candidate_path(path):
                continue
            content = self.source.get_file(repo, path)
            result = classify.classify(repo, path, content)
            if result is None:
                continue
            kind, label = result
            files.append({"path": path, "kind": kind, "label": label,
                          "editable": kind == "config"})
        kinds = {f["kind"] for f in files}
        if "config" in kinds:
            status = "config"
        elif "floor" in kinds:
            status = "floor-only"
        elif files:
            status = "guard-code"
        else:
            status = "none"
        scan = {"repo": repo, "status": status, "files": files}
        self.store.set_scan(repo, scan)
        return scan

    def list_repos(self, rescan_missing: bool = False) -> list[dict]:
        out = []
        scans = self.store.all_scans()
        for repo in self.source.list_repos():
            name = repo["name"]
            scan = scans.get(name)
            if scan is None and rescan_missing:
                scan = self.scan_repo(name)
            out.append({
                "name": name,
                "description": repo.get("description", ""),
                "status": scan["status"] if scan else "unscanned",
                "files": scan["files"] if scan else [],
                "scanned_at": scan.get("scanned_at") if scan else None,
            })
        return out

    def get_file(self, repo: str, path: str) -> dict:
        content = self.source.get_file(repo, path)
        result = classify.classify(repo, path, content)
        if result is None:
            # A canonical config path that does not exist yet is creatable.
            if path == self.template_path:
                return {"repo": repo, "path": path, "kind": "config",
                        "label": "deployment policy template (not created yet)",
                        "editable": True, "embedded": False, "exists": False,
                        "content": "", "entries": []}
            raise LookupError(f"{path} is not a guard artifact in {repo}")
        kind, label = result
        return {"repo": repo, "path": path, "kind": kind, "label": label,
                "editable": kind == "config",
                "embedded": classify.is_embedded_config(repo, path),
                "exists": content is not None,
                "content": content or "",
                "entries": classify.parse_entries(content or "")
                if kind == "config" else []}

    # -- write guard --------------------------------------------------------
    def _require_config(self, repo: str, path: str) -> None:
        """Raise PermissionError unless the target is the config layer."""
        content = self.source.get_file(repo, path)
        result = classify.classify(repo, path, content)
        if result is not None:
            kind, label = result
            if kind != "config":
                raise PermissionError(
                    f"{path} is {label}: hard floor / view-only files cannot "
                    f"be edited or deleted in Guardrail Manager.")
            return
        if classify.is_config_path(repo, path):
            return  # new config file at an allowed data path
        raise PermissionError(
            f"{path} is not a deployment policy template path; writes are "
            f"limited to the owner config layer.")

    def _require_gitops(self) -> GitOps:
        if self.gitops is None:
            raise RuntimeError("git write path is not configured on this server")
        return self.gitops

    # -- write operations (config layer only) -------------------------------
    def _require_not_embedded(self, repo: str, path: str, action: str) -> None:
        if classify.is_embedded_config(repo, path):
            raise PermissionError(
                f"{path} is a code module the host app imports: {action} is "
                f"disabled here so the app keeps building. Its policy entry "
                f"lists are editable (add/remove/clear) from this app.")

    def save_config(self, repo: str, path: str, content: str) -> dict:
        self._require_config(repo, path)
        self._require_not_embedded(repo, path, "raw save")
        sha = self._require_gitops().write_file(
            repo, path, content,
            f"guardrail-manager: update deployment policy template {path}")
        self.scan_repo(repo)
        return {"ok": True, "commit": sha}

    def _entry_op(self, repo: str, path: str, fn, message: str) -> dict:
        self._require_config(repo, path)
        current = self.source.get_file(repo, path)
        if current is None:
            raise LookupError(f"{path} not found in {repo}")
        new_content = fn(current)
        sha = self._require_gitops().write_file(repo, path, new_content, message)
        self.scan_repo(repo)
        return {"ok": True, "commit": sha}

    def add_entry(self, repo: str, path: str, entry: str) -> dict:
        return self._entry_op(
            repo, path, lambda c: classify.add_entry(c, entry),
            f"guardrail-manager: add policy entry to {path}")

    def remove_entry(self, repo: str, path: str, entry: str) -> dict:
        return self._entry_op(
            repo, path, lambda c: classify.remove_entry(c, entry),
            f"guardrail-manager: remove policy entry from {path}")

    def clear_entries(self, repo: str, path: str) -> dict:
        return self._entry_op(
            repo, path, classify.clear_entries,
            f"guardrail-manager: clear all policy entries in {path}")

    def apply_default(self, repo: str) -> dict:
        path = self._existing_config_path(repo) or self.template_path
        if classify.is_embedded_config(repo, path):
            entries = classify.parse_entries(self.store.get_default_template())
            return self._entry_op(
                repo, path,
                lambda c: classify.set_embedded_list(
                    c, "OWNER_REFUSAL_PATTERNS", entries),
                f"guardrail-manager: apply template default entries to {path}")
        return self.save_config(repo, path, self.store.get_default_template())

    def create_config(self, repo: str) -> dict:
        path = self.template_path
        self._require_config(repo, path)
        sha = self._require_gitops().write_file(
            repo, path, self.store.get_default_template(),
            f"guardrail-manager: add deployment policy template {path}")
        self.scan_repo(repo)
        return {"ok": True, "commit": sha, "path": path}

    def delete_config(self, repo: str, path: str) -> dict:
        self._require_config(repo, path)
        self._require_not_embedded(repo, path, "delete")
        sha = self._require_gitops().delete_file(
            repo, path,
            f"guardrail-manager: remove deployment policy template {path}")
        self.scan_repo(repo)
        return {"ok": True, "commit": sha}

    def _existing_config_path(self, repo: str) -> str | None:
        scan = self.store.get_scan(repo) or self.scan_repo(repo)
        for f in scan.get("files", []):
            if f["kind"] == "config":
                return f["path"]
        return None

    # -- template default -----------------------------------------------------
    def get_default(self) -> str:
        return self.store.get_default_template()

    def set_default(self, text: str) -> None:
        self.store.set_default_template(text)
