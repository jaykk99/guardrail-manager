"""Git write path for deployment policy template files.

Per repo: a dedicated worktree under the worktrees dir (never a main
checkout). Edits land on the repo's default branch, are committed with a
clear message, and pushed fast-forward only. After push, the new head is
verified against origin. A failed push raises and is never retried blindly.
"""

from __future__ import annotations

import os
import subprocess


def _git(args: list[str], cwd: str | None = None, timeout: int = 120) -> str:
    proc = subprocess.run(["git"] + args, cwd=cwd, capture_output=True,
                          text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args[:3])} failed: {(proc.stderr or proc.stdout).strip()[:400]}")
    return proc.stdout.strip()


class GitOps:
    def __init__(self, owner: str = "jaykk99", worktrees_dir: str = "",
                 clones_dir: str = "",
                 remote_template: str = "https://github.com/{owner}/{repo}.git"):
        self.owner = owner
        self.worktrees_dir = worktrees_dir
        self.clones_dir = clones_dir
        self.remote_template = remote_template

    def remote_url(self, repo: str) -> str:
        return self.remote_template.format(owner=self.owner, repo=repo)

    # -- plumbing -----------------------------------------------------------
    def _default_branch(self, clone: str, repo: str) -> str:
        try:
            ref = _git(["symbolic-ref", "refs/remotes/origin/HEAD"], cwd=clone)
            return ref.rsplit("/", 1)[-1]
        except Exception:
            proc = subprocess.run(
                ["gh", "repo", "view", f"{self.owner}/{repo}",
                 "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name"],
                capture_output=True, text=True, timeout=60)
            name = (proc.stdout or "").strip()
            return name or "main"

    def ensure_worktree(self, repo: str) -> tuple[str, str]:
        """Return (worktree_path, default_branch), creating clone+worktree."""
        os.makedirs(self.clones_dir, exist_ok=True)
        os.makedirs(self.worktrees_dir, exist_ok=True)
        clone = os.path.join(self.clones_dir, repo)
        if not os.path.isdir(os.path.join(clone, ".git")):
            _git(["clone", "--quiet", self.remote_url(repo), clone],
                 timeout=300)
        _git(["fetch", "--quiet", "origin"], cwd=clone, timeout=180)
        branch = self._default_branch(clone, repo)
        wt = os.path.join(self.worktrees_dir, f"guardmgr-{repo}")
        if not os.path.isdir(wt):
            _git(["worktree", "add", "--quiet", wt, f"origin/{branch}"], cwd=clone)
        else:
            # The worktree is detached at origin/<branch> (the clone itself
            # holds the branch checkout), so re-sync by detaching again and
            # hard-resetting; never check the branch out by name here.
            _git(["checkout", "--quiet", "--detach", f"origin/{branch}"], cwd=wt)
            _git(["reset", "--quiet", "--hard", f"origin/{branch}"], cwd=wt)
        return wt, branch

    def commit_push(self, repo: str, worktree: str, branch: str,
                    rel_paths: list[str], message: str) -> str:
        """Commit the given paths and push fast-forward only. Returns head sha."""
        _git(["add", "--"] + rel_paths, cwd=worktree)
        staged = _git(["status", "--porcelain"], cwd=worktree)
        if not staged:
            raise RuntimeError("nothing to commit")
        _git(["-c", "user.name=Guardrail Manager",
              "-c", "user.email=guardrail-manager@localhost",
              "commit", "--quiet", "-m", message], cwd=worktree)
        head = _git(["rev-parse", "HEAD"], cwd=worktree)
        # Fast-forward only: plain push, no --force anywhere in this app.
        _git(["push", "origin", f"HEAD:{branch}"], cwd=worktree, timeout=180)
        remote = _git(["ls-remote", "origin", f"refs/heads/{branch}"],
                      cwd=worktree, timeout=60).split()[0]
        if remote != head:
            raise RuntimeError(f"push verification failed: origin {branch} is "
                               f"{remote}, expected {head}")
        return head

    # -- operations -----------------------------------------------------------
    def write_file(self, repo: str, path: str, content: str,
                   message: str) -> str:
        wt, branch = self.ensure_worktree(repo)
        dest = os.path.join(wt, path)
        os.makedirs(os.path.dirname(dest) or wt, exist_ok=True)
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(content)
        return self.commit_push(repo, wt, branch, [path], message)

    def delete_file(self, repo: str, path: str, message: str) -> str:
        wt, branch = self.ensure_worktree(repo)
        dest = os.path.join(wt, path)
        if not os.path.isfile(dest):
            raise RuntimeError(f"{path} not found in {repo}")
        os.remove(dest)
        return self.commit_push(repo, wt, branch, [path], message)
