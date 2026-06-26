"""Tests for GitBackend sync operations."""

import os
import sys
import tempfile
import subprocess
from pathlib import Path

# Ensure repo root is importable so `hermes_sync` package works
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pytest

from hermes_sync.backends.github import GitBackend
from hermes_sync.config import SyncConfig
from hermes_sync.sync import HermesSync


def _git(cmd: list, cwd: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command with user config set."""
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "test")
    env.setdefault("GIT_AUTHOR_EMAIL", "test@test.com")
    env.setdefault("GIT_COMMITTER_NAME", "test")
    env.setdefault("GIT_COMMITTER_EMAIL", "test@test.com")
    env["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        ["git"] + cmd, cwd=cwd, capture_output=True, text=True,
        env=env, check=check
    )


class TestGitBackend:
    """Test GitBackend in a local temp repo (no GitHub API needed)."""

    @pytest.fixture
    def local_repo(self):
        """Create a local bare repo and a working clone."""
        tmp = tempfile.mkdtemp(prefix="hermes-sync-test-")
        bare = Path(tmp) / "remote.git"

        # Create bare repo
        _git(["init", "--bare", str(bare)], cwd=tmp)

        # Clone into working dir with initial commit
        work = Path(tmp) / "work"
        _git(["clone", str(bare), str(work)], cwd=tmp)
        (work / "README.md").write_text("# Test Repo\n")
        _git(["add", "-A"], cwd=str(work))
        _git(["commit", "-m", "init"], cwd=str(work))
        # Push to master (default branch on older git)
        _git(["push", "origin", "HEAD"], cwd=str(work))

        # Clone for the test backend
        local = Path(tmp) / "local"
        _git(["clone", str(bare), str(local)], cwd=tmp)

        backend = GitBackend(
            repo_path=local,
            repo_url=str(bare),
            token=None,
        )

        yield backend, bare, local

        # Cleanup
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    def test_clone_if_needed_already_exists(self, local_repo):
        backend, bare, local = local_repo
        assert backend.clone_if_needed() is True

    def test_clone_if_needed_new(self, local_repo):
        backend, bare, local = local_repo
        new_path = local.parent / "fresh-clone"
        new_backend = GitBackend(
            repo_path=new_path,
            repo_url=str(bare),
            token=None,
        )
        assert new_backend.clone_if_needed() is True
        assert (new_path / ".git").exists()

    def test_pull_up_to_date(self, local_repo):
        backend, bare, local = local_repo
        success, message = backend.pull()
        assert success is True
        assert "up to date" in message.lower() or "already" in message.lower()

    def test_push_new_file(self, local_repo):
        backend, bare, local = local_repo
        (local / "test.md").write_text("# Test\n")
        success, message = backend.push("test: add test file")
        assert success is True

    def test_has_changes(self, local_repo):
        backend, bare, local = local_repo
        assert backend.has_changes() is False
        (local / "new.txt").write_text("hello")
        assert backend.has_changes() is True

    def test_push_and_pull_roundtrip(self, local_repo):
        backend_a, bare, local_a = local_repo

        # Clone a second working copy
        local_b = local_a.parent / "clone-b"
        _git(["clone", str(bare), str(local_b)], cwd=str(local_a.parent))

        backend_b = GitBackend(
            repo_path=local_b,
            repo_url=str(bare),
            token=None,
        )

        # Write and push from A
        (local_a / "from-a.md").write_text("# From A\n")
        success, _ = backend_a.push("from A")
        assert success is True

        # Pull on B
        success, message = backend_b.pull()
        assert success is True
        assert "1 commit" in message
        assert (local_b / "from-a.md").exists()
        assert (local_b / "from-a.md").read_text() == "# From A\n"


class TestSyncOrchestrator:
    """Test the HermesSync orchestrator."""

    def test_config_disabled_when_no_repo(self):
        config = SyncConfig(repo_url="")  # empty = disabled
        sync = HermesSync(config)
        assert sync.enabled is False
        assert sync.start() is False
