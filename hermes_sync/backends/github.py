"""GitHub backend for Hermes Sync —  git pull/push operations.

Uses git CLI for all operations — no API calls needed.
Git protocol avoids REST rate limits entirely.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class GitBackend:
    """Git operations for syncing the sync repo."""

    def __init__(self, repo_path: Path, repo_url: str, token: Optional[str] = None):
        self.repo_path = repo_path
        self.repo_url = repo_url
        self.token = token
        self._authenticated_url: Optional[str] = None

    @property
    def auth_url(self) -> str:
        """Get the repo URL — token handled via GIT_ASKPASS, never in URL."""
        if self._authenticated_url is not None:
            return self._authenticated_url

        url = self.repo_url
        # Convert SSH to HTTPS (ASKPASS only works with HTTPS)
        if url.startswith("git@github.com:"):
            path = url.split("github.com:")[1]
            url = "https://github.com/" + path

        self._authenticated_url = url
        return url

    def _run_git(
        self, args: List[str], timeout: int = 120, capture: bool = True,
        cwd_override: Optional[Path] = None,
    ) -> Tuple[int, str, str]:
        """Run a git command in the repo directory.

        Returns (exit_code, stdout, stderr).
        """
        cmd = ["git"] + args
        cwd = str(cwd_override) if cwd_override else str(self.repo_path)
        env = os.environ.copy()
        # Prevent interactive prompts
        env["GIT_TERMINAL_PROMPT"] = "0"
        # Use ASKPASS for token auth — never embeds token in URL (avoids .git/config leak)
        if self.token:
            askpass_path = Path(__file__).resolve().parent.parent / "git_askpass.py"
            env["GIT_ASKPASS"] = str(askpass_path)
            env["HERMES_SYNC_TOKEN"] = self.token
        else:
            env["GIT_ASKPASS"] = "echo"

        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=capture,
                text=True,
                timeout=timeout,
                env=env,
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            logger.error("Git command timed out: %s", " ".join(cmd))
            return -1, "", "Command timed out"
        except Exception as e:
            logger.error("Git command failed: %s — %s", " ".join(cmd), e)
            return -1, "", str(e)

    def clone_if_needed(self) -> bool:
        """Clone the repo if it doesn't exist locally.

        Returns True if repo is ready (cloned or already exists).
        """
        if not self.repo_url:
            logger.warning("No repo URL configured — skipping clone")
            return False

        if self.repo_path.exists() and (self.repo_path / ".git").exists():
            logger.debug("Repo already cloned at %s", self.repo_path)
            return True

        logger.info("Cloning %s -> %s", self.repo_url, self.repo_path)
        self.repo_path.parent.mkdir(parents=True, exist_ok=True)

        # Clone doesn't use repo_path as cwd (it doesn't exist yet)
        code, stdout, stderr = self._run_git(
            ["clone", "--depth", "1", self.auth_url, str(self.repo_path)],
            timeout=300,
            capture=True,
            cwd_override=self.repo_path.parent,  # Clone into parent dir
        )

        if code != 0:
            logger.error("Clone failed: %s", stderr)
            return False

        logger.info("Clone successful")
        return True

    def pull(self) -> Tuple[bool, str]:
        """Pull latest changes from remote.

        Returns (success, message).
        """
        if not self._repo_ready():
            return False, "Repo not ready"

        # Get the current branch name
        code, stdout, stderr = self._run_git(
            ["rev-parse", "--abbrev-ref", "HEAD"], timeout=30
        )
        branch = stdout.strip() if code == 0 else "main"

        # Reset local changes before pull (repo is just a cache)
        code, stdout, stderr = self._run_git(
            ["reset", "--hard", "HEAD"], timeout=30
        )

        # Fetch first (lightweight, doesn't modify working tree)
        code, stdout, stderr = self._run_git(
            ["fetch", "origin"], timeout=60
        )
        if code != 0:
            return False, f"Fetch failed: {stderr.strip()}"

        # Check if we're behind (use FETCH_HEAD to handle any branch name)
        code, stdout, stderr = self._run_git(
            ["rev-list", "--count", f"HEAD..origin/{branch}"], timeout=30
        )
        if code != 0:
            # Try FETCH_HEAD
            code, stdout, stderr = self._run_git(
                ["rev-list", "--count", "HEAD..FETCH_HEAD"], timeout=30
            )
        if code != 0:
            return False, f"Rev-list failed: {stderr.strip()}"

        behind = int(stdout.strip()) if stdout.strip().isdigit() else 0
        if behind == 0:
            return True, "Already up to date"

        # Pull with rebase
        code, stdout, stderr = self._run_git(
            ["pull", "--rebase", "origin", branch], timeout=120
        )

        if code == 0:
            return True, f"Pulled {behind} commit(s)"
        else:
            return False, f"Pull failed: {stderr.strip()}"

    def push(self, commit_message: str = "sync: automatic update") -> Tuple[bool, str]:
        """Stage, commit, and push changes.

        Returns (success, message).
        """
        if not self._repo_ready():
            return False, "Repo not ready"

        # Check if there are changes to commit
        code, stdout, stderr = self._run_git(
            ["status", "--porcelain"], timeout=30
        )
        if code != 0:
            return False, "Status check failed: {}".format(stderr.strip())

        if not stdout.strip():
            return True, "No changes to push"

        # Pre-commit gate: check for sensitive files
        from hermes_sync.security import check_sensitive_files
        changed_paths = []
        for line in stdout.strip().split("\n"):
            if line.strip():
                # git status --porcelain format: "XY filename"
                path = line[3:].strip()
                changed_paths.append(str(self.repo_path / path))

        blocked = check_sensitive_files(changed_paths)
        if blocked:
            msg = "Blocked {} sensitive file(s): {}".format(
                len(blocked), ", ".join(blocked)
            )
            logger.warning("GitBackend: %s", msg)
            return False, msg

        # Stage all changes
        code, stdout, stderr = self._run_git(
            ["add", "-A"], timeout=30
        )
        if code != 0:
            return False, "Git add failed: {}".format(stderr.strip())

        # Commit
        code, stdout, stderr = self._run_git(
            ["commit", "-m", commit_message], timeout=30
        )
        if code != 0:
            return False, "Commit failed: {}".format(stderr.strip())

        # Get the current branch name
        code, stdout, stderr = self._run_git(
            ["rev-parse", "--abbrev-ref", "HEAD"], timeout=30
        )
        branch = stdout.strip() if code == 0 else "main"

        # Push
        code, stdout, stderr = self._run_git(
            ["push", "origin", branch], timeout=120
        )

        if code == 0:
            return True, "Pushed successfully"
        else:
            return False, "Push failed: {}".format(stderr.strip())

    def has_changes(self) -> bool:
        """Check if there are uncommitted changes."""
        if not self._repo_ready():
            return False
        code, stdout, stderr = self._run_git(
            ["status", "--porcelain"], timeout=30
        )
        return bool(stdout.strip())

    def _repo_ready(self) -> bool:
        """Check if the repo is initialized and ready."""
        return self.repo_path.exists() and (self.repo_path / ".git").exists()
