"""Hermes Sync — Cross-device sync plugin for Hermes Agent.

Sync your skills, memory, and cron jobs across all your devices
via a private GitHub repo. Zero infrastructure required — just
drop this plugin into ~/.hermes/plugins/hermes-sync/.

Usage:
    1. Clone this repo into ~/.hermes/plugins/hermes-sync/
    2. Configure ~/.hermes/plugins/hermes-sync/config.yaml
    3. Set GH_TOKEN environment variable (GitHub PAT with repo scope)
    4. Restart Hermes — plugin auto-detected and starts syncing
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

logger = logging.getLogger("hermes_sync")

_sync_instance = None


def register(ctx):
    global _sync_instance

    logger.info("Hermes Sync v0.1.0 — registering plugin")
    ctx.register_hook("on_session_start", _on_session_start)
    ctx.register_hook("on_session_end", _on_session_end)
    logger.info("Hermes Sync registered")


def _on_session_start(**kwargs):
    global _sync_instance

    try:
        from sync import HermesSync
        from config import load_config

        config = load_config()
        if not config.enabled:
            return

        if _sync_instance is not None:
            return

        _sync_instance = HermesSync(config)
        if _sync_instance.start():
            logger.info(
                "Hermes Sync: sync active (repo=%s, interval=%ds)",
                config.repo_url,
                config.sync_interval,
            )
        else:
            logger.warning("Hermes Sync: failed to start sync")

    except Exception as e:
        logger.error("Hermes Sync: startup error: %s", e, exc_info=True)


def _on_session_end(**kwargs):
    global _sync_instance

    if _sync_instance is not None:
        logger.info("Hermes Sync: stopping sync service...")
        _sync_instance.stop()
        _sync_instance = None


def get_status():
    global _sync_instance

    if _sync_instance is None:
        return {"status": "not_running", "enabled": False}

    return {
        "status": "running" if _sync_instance._running else "stopped",
        "enabled": _sync_instance.enabled,
        "backend": _sync_instance.config.backend,
        "repo_url": _sync_instance.config.repo_url,
        "pull_count": _sync_instance.pull_count,
        "push_count": _sync_instance.push_count,
        "last_pull": _sync_instance.last_pull,
        "last_push": _sync_instance.last_push,
    }


def sync_now():
    global _sync_instance
    if _sync_instance is None:
        return {"error": "sync service not running"}

    pull_ok, pull_msg, push_ok, push_msg = _sync_instance.sync_now()
    return {
        "pull_success": pull_ok,
        "pull_message": pull_msg,
        "push_success": push_ok,
        "push_message": push_msg,
    }
