"""Sync orchestrator for Hermes Sync.

Manages the sync lifecycle: startup pull, periodic background sync,
file watcher for local changes, and platform-scoped syncing.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Optional

# Ensure importing from the same plugin directory works
_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

logger = logging.getLogger(__name__)

from config import SyncConfig, load_config, get_token, detect_platform  # noqa: E402
from backends.github import GitBackend  # noqa: E402
from security import scan_content, check_sensitive_files, ensure_keypair, sign_commit_message  # noqa: E402
from watcher import create_watcher  # noqa: E402
from merge import detect_conflicts, resolve_all_ours  # noqa: E402

try:
    from hermes_constants import get_hermes_home
except ImportError:
    def get_hermes_home() -> Path:
        return Path(os.path.expanduser("~/.hermes"))


class HermesSync:
    """Orchestrates the sync lifecycle."""

    def __init__(self, config: Optional[SyncConfig] = None):
        self.config = config or load_config()
        self.token = get_token()
        self.backend: Optional[GitBackend] = None
        self._running = False
        self._lock = threading.Lock()
        self._sync_thread: Optional[threading.Thread] = None
        self._watch_thread: Optional[threading.Thread] = None
        self._watcher = None  # InotifyWatcher or PollingWatcher

        # Ed25519 signing identity
        self._private_key, self._public_key = ensure_keypair()

        self.pull_count = 0
        self.push_count = 0
        self.last_pull: Optional[str] = None
        self.last_push: Optional[str] = None

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def start(self) -> bool:
        if not self.enabled:
            logger.info("Hermes Sync: not configured — sync disabled")
            return False

        with self._lock:
            if self._running:
                return True
            self._running = True

        repo_path = self.config.repo_path
        self.backend = GitBackend(repo_path, self.config.repo_url, self.token)

        if not self.backend.clone_if_needed():
            logger.error("Failed to clone sync repo — sync disabled")
            self._running = False
            return False

        success, message = self.backend.pull()
        self.pull_count += 1
        logger.info("Initial pull: %s", message)

        if success:
            self._apply_pulled_files()
        else:
            # Check for merge conflicts and auto-resolve
            conflicts = detect_conflicts(self.config.repo_path)
            if conflicts:
                logger.warning(
                    "Detected %d merge conflict(s) — auto-resolving (ours)",
                    len(conflicts),
                )
                resolved = resolve_all_ours(self.config.repo_path)
                logger.info("Resolved %d/%d conflicts", resolved, len(conflicts))

        self._sync_thread = threading.Thread(
            target=self._sync_loop, daemon=True, name="hermes-sync"
        )
        self._sync_thread.start()

        # Start filesystem watcher (inotify on Linux, polling elsewhere)
        watch_dirs = []
        hermes_home = get_hermes_home()
        if self.config.sync_skills:
            watch_dirs.append(hermes_home / "skills")
        if self.config.sync_memories:
            watch_dirs.append(hermes_home / "memories")
        if self.config.sync_cron:
            watch_dirs.append(hermes_home / "cron")

        self._watcher = create_watcher(watch_dirs, self._sync_local_changes)
        self._watcher.start()

        logger.info(
            "Hermes Sync started (interval=%ds, backend=%s)",
            self.config.sync_interval,
            self.config.backend,
        )
        return True

    def stop(self) -> None:
        with self._lock:
            self._running = False

        if self._watcher:
            self._watcher.stop()

        if self.backend and self.backend.has_changes():
            logger.info("Pushing final changes before shutdown...")
            self.backend.push(self._signed_commit_message("sync: shutdown save"))

    def sync_now(self) -> tuple:
        if not self.backend:
            return False, "No backend", False, "No backend"

        pull_ok, pull_msg = self.backend.pull()
        self.pull_count += 1
        if pull_ok:
            self._apply_pulled_files()

        push_ok, push_msg = self.backend.push()
        self.push_count += 1

        return pull_ok, pull_msg, push_ok, push_msg

    def _sync_loop(self) -> None:
        logger.debug("Sync loop started (interval=%ds)", self.config.sync_interval)

        while self._running:
            try:
                time.sleep(self.config.sync_interval)
                if not self._running:
                    break

                if self.backend:
                    success, message = self.backend.pull()
                    self.pull_count += 1
                    if success:
                        self._apply_pulled_files()
                        if "Already up to date" not in message:
                            logger.info("Pull: %s", message)
                    else:
                        logger.warning("Pull failed: %s", message)
                        # Check for conflicts
                        conflicts = detect_conflicts(self.config.repo_path)
                        if conflicts:
                            logger.warning(
                                "Detected %d merge conflict(s) — auto-resolving (ours)",
                                len(conflicts),
                            )
                            resolve_all_ours(self.config.repo_path)

            except Exception as e:
                logger.error("Sync loop error: %s", e)

    def _sync_local_changes(self) -> None:
        if not self.backend:
            return

        hermes_home = get_hermes_home()
        repo_path = self.config.repo_path

        sync_pairs = []
        if self.config.sync_skills:
            sync_pairs.append((hermes_home / "skills", repo_path / "skills"))
        if self.config.sync_memories:
            sync_pairs.append((hermes_home / "memories", repo_path / "memories"))
        if self.config.sync_cron:
            sync_pairs.append((hermes_home / "cron", repo_path / "cron"))

        # Collect files to copy and check for sensitive files
        files_to_copy: list[tuple[Path, Path]] = []
        for src, dst in sync_pairs:
            if not src.is_dir():
                continue
            dst.mkdir(parents=True, exist_ok=True)
            for item in src.rglob("*"):
                if item.is_file() and not item.name.startswith("."):
                    rel = item.relative_to(src)
                    files_to_copy.append((item, dst / rel))

        # Enforce .gitignore rules — refuse to sync blocked files
        blocked = check_sensitive_files([str(f[0]) for f in files_to_copy])
        if blocked:
            logger.warning(
                "Refusing to sync %d sensitive file(s): %s",
                len(blocked), ", ".join(blocked),
            )
            return

        # Perform the copy
        for src_file, dst_file in files_to_copy:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            if dst_file.exists():
                try:
                    if src_file.stat().st_mtime <= dst_file.stat().st_mtime:
                        continue
                except OSError:
                    pass
            shutil.copy2(src_file, dst_file)

        success, message = self.backend.push(
            self._signed_commit_message()
        )
        self.push_count += 1
        if success and "No changes" not in message:
            logger.info("Push: %s", message)
        elif not success:
            logger.warning("Push failed: %s", message)

    def _apply_pulled_files(self) -> None:
        hermes_home = get_hermes_home()
        repo_path = self.config.repo_path

        apply_pairs = []
        if self.config.sync_skills:
            apply_pairs.append((repo_path / "skills", hermes_home / "skills"))
        if self.config.sync_memories:
            apply_pairs.append((repo_path / "memories", hermes_home / "memories"))
        if self.config.sync_cron:
            apply_pairs.append((repo_path / "cron", hermes_home / "cron"))

        current_platform = detect_platform()

        for src, dst in apply_pairs:
            if src.is_dir():
                _copy_dir_platform_scoped(src, dst, current_platform)

    def _signed_commit_message(self, base_message: str = "sync: automatic update") -> str:
        """Build a commit message with Ed25519 signature embedded."""
        sig_line = sign_commit_message(base_message, self._private_key)
        return base_message + "\n\n" + sig_line


def _copy_dir(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)

    for item in src.iterdir():
        if item.name.startswith("."):
            continue

        dest = dst / item.name

        if item.is_dir():
            _copy_dir(item, dest)
        elif item.is_file():
            if dest.exists():
                try:
                    if item.stat().st_mtime <= dest.stat().st_mtime:
                        continue
                except OSError:
                    pass
            shutil.copy2(item, dest)


def _skill_matches_platform(skill_dir: Path, current_platform: str) -> bool:
    """Check if a skill's platform requirements match the current device.

    Reads the SKILL.md frontmatter for a 'platforms' field.
    If no platforms are specified, the skill applies everywhere.
    If platforms are specified, the current platform must be listed.

    Returns True if the skill should be applied to this device.
    """
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return True  # Not a skill directory — apply anyway

    try:
        frontmatter = _parse_yaml_frontmatter(skill_md.read_text())
    except Exception:
        return True  # Can't parse — apply anyway (safe default)

    platforms = frontmatter.get("platforms")
    if platforms is None or not isinstance(platforms, list):
        return True  # No platform restriction — apply everywhere

    if len(platforms) == 0:
        return True

    return current_platform in platforms


def _parse_yaml_frontmatter(content: str) -> dict:
    """Parse YAML frontmatter from a markdown file.

    Expects: ---\\nkey: value\\n---\\n\\nbody
    Returns empty dict if no frontmatter found.
    """
    import yaml

    if not content.startswith("---"):
        return {}

    try:
        end = content.index("---", 3)
        yaml_str = content[3:end].strip()
        if not yaml_str:
            return {}
        return yaml.safe_load(yaml_str) or {}
    except (ValueError, yaml.YAMLError):
        return {}


def _copy_dir_platform_scoped(src: Path, dst: Path, current_platform: str) -> None:
    """Copy directory with platform scoping for skill directories.

    Skill directories (those containing SKILL.md) are filtered by
    platform requirements. Non-skill directories are copied normally.
    """
    dst.mkdir(parents=True, exist_ok=True)

    for item in src.iterdir():
        if item.name.startswith("."):
            continue

        dest = dst / item.name

        if item.is_dir():
            # Check if this directory is a skill (has SKILL.md)
            if (item / "SKILL.md").exists():
                if not _skill_matches_platform(item, current_platform):
                    logger.debug(
                        "Skipping skill '%s' — platform mismatch (current: %s)",
                        item.name, current_platform,
                    )
                    continue
            _copy_dir_platform_scoped(item, dest, current_platform)
        elif item.is_file():
            if dest.exists():
                try:
                    if item.stat().st_mtime <= dest.stat().st_mtime:
                        continue
                except OSError:
                    pass
            shutil.copy2(item, dest)
