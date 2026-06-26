"""Hermes Sync configuration management.

Reads config from ~/.hermes/plugins/hermes-sync/config.yaml with
sensible defaults. Falls back to environment variables where appropriate.
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

try:
    import yaml
except ImportError:
    yaml = None

try:
    from hermes_constants import get_hermes_home
except ImportError:
    def get_hermes_home() -> Path:
        return Path(os.path.expanduser("~/.hermes"))


DEFAULT_CONFIG = {
    "backend": "github",
    "repo_url": "",
    "sync_interval": 60,
    "auto_resolve_conflicts": True,
    "platforms": [],
}


@dataclass
class SyncConfig:
    """Parsed configuration for the Hermes Sync plugin."""

    backend: str = "github"
    repo_url: str = ""
    sync_interval: int = 60
    auto_resolve_conflicts: bool = True
    platforms: List[str] = field(default_factory=list)
    sync_skills: bool = True
    sync_memories: bool = True
    sync_cron: bool = False

    @property
    def repo_path(self) -> Path:
        return get_hermes_home() / "sync-repo"

    @property
    def config_path(self) -> Path:
        return get_hermes_home() / "plugins" / "hermes-sync" / "config.yaml"

    @property
    def enabled(self) -> bool:
        return bool(self.repo_url)


def detect_platform() -> str:
    system = platform.system().lower()
    if system == "linux":
        return "linux"
    elif system == "darwin":
        return "macos"
    elif system == "windows":
        return "windows"
    return system


def load_config() -> SyncConfig:
    cfg = SyncConfig()

    config_path = cfg.config_path
    if config_path.exists() and yaml is not None:
        try:
            with open(config_path, encoding="utf-8-sig") as f:
                raw = yaml.safe_load(f) or {}
            cfg.backend = raw.get("backend", "github")
            cfg.repo_url = raw.get("repo_url", raw.get("repo", ""))
            cfg.sync_interval = int(raw.get("sync_interval", 60))
            cfg.auto_resolve_conflicts = bool(
                raw.get("auto_resolve_conflicts", True)
            )
            cfg.sync_skills = bool(raw.get("sync_skills", True))
            cfg.sync_memories = bool(raw.get("sync_memories", True))
            cfg.sync_cron = bool(raw.get("sync_cron", False))
            configured_platforms = raw.get("platforms", [])
            if configured_platforms:
                cfg.platforms = configured_platforms
        except Exception:
            pass

    env_repo = os.getenv("HERMES_SWARM_REPO", "")
    if env_repo:
        cfg.repo_url = env_repo

    if not cfg.platforms:
        cfg.platforms = [detect_platform()]

    return cfg


def get_token() -> Optional[str]:
    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if token:
        return token

    config_path = get_hermes_home() / "plugins" / "hermes-sync" / "config.yaml"
    if config_path.exists() and yaml is not None:
        try:
            with open(config_path, encoding="utf-8-sig") as f:
                raw = yaml.safe_load(f) or {}
            return raw.get("token") or raw.get("github_token")
        except Exception:
            pass

    return None
