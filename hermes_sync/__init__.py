"""Hermes Sync — Cross-device sync for Hermes Agent.

Sync your skills, memory, config, profiles, and cron jobs across all
your devices via a private GitHub repo. Zero infrastructure required.

This is a standalone library + CLI, not a Hermes plugin. It can be
integrated into Hermes core or used independently.

Usage as library:
    from hermes_sync import HermesSync, SyncConfig, load_config
    config = load_config()
    sync = HermesSync(config)
    sync.start()
    ...
    sync.stop()

Usage as CLI:
    hermes-sync start          # Start sync daemon
    hermes-sync status         # Show sync status
    hermes-sync push           # Manual push
    hermes-sync pull           # Manual pull
    hermes-sync setup          # Interactive config wizard
"""

from __future__ import annotations

__version__ = "0.2.0"
__all__ = [
    "HermesSync",
    "SyncConfig",
    "load_config",
    "get_token",
    "detect_platform",
    "GitBackend",
    "MergeConflict",
    "detect_conflicts",
    "resolve_all_ours",
    "build_resolution_prompt",
    "scan_content",
    "check_sensitive_files",
    "ensure_keypair",
    "sign_commit_message",
    "verify_commit_message",
]

from .sync import HermesSync
from .config import SyncConfig, load_config, get_token, detect_platform
from .backends.github import GitBackend
from .merge import MergeConflict, detect_conflicts, resolve_all_ours, build_resolution_prompt
from .security import scan_content, check_sensitive_files
from .security.signer import ensure_keypair, sign_commit_message, verify_commit_message
