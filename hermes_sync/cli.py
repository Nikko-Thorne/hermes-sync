"""hermes-sync CLI — cross-device sync for Hermes Agent."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Ensure package is importable
_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT.parent))

from hermes_sync import HermesSync, SyncConfig, load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("hermes-sync")


def cmd_start(args):
    """Start sync daemon (foreground)."""
    config = load_config()
    if not config.enabled:
        print("hermes-sync: not configured — create config.yaml first or run 'hermes-sync setup'")
        sys.exit(1)

    sync = HermesSync(config)
    if not sync.start():
        print("hermes-sync: failed to start (check logs)")
        sys.exit(1)

    print(f"hermes-sync: running (repo={config.repo_url}, interval={config.sync_interval}s, "
          f"skills={config.sync_skills}, memories={config.sync_memories}, "
          f"cron={config.sync_cron}, config={config.sync_config}, "
          f"profiles={config.sync_profiles})")
    print("Press Ctrl+C to stop")

    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nhermes-sync: stopping...")
        sync.stop()
        print("hermes-sync: stopped")


def cmd_status(args):
    """Show sync status."""
    config = load_config()
    print(f"hermes-sync v0.2.0")
    print(f"  Enabled:     {config.enabled}")
    print(f"  Backend:     {config.backend}")
    print(f"  Repo:        {config.repo_url or '(not set)'}")
    print(f"  Interval:    {config.sync_interval}s")
    print(f"  Skills:      {config.sync_skills}")
    print(f"  Memories:    {config.sync_memories}")
    print(f"  Cron:        {config.sync_cron}")
    print(f"  Config:      {config.sync_config}")
    print(f"  Profiles:    {config.sync_profiles}")
    print(f"  Platform:    {config.platforms}")


def cmd_push(args):
    """Manual push."""
    config = load_config()
    if not config.enabled:
        print("hermes-sync: not configured")
        sys.exit(1)
    sync = HermesSync(config)
    sync.start()
    _, _, ok, msg = sync.sync_now()
    print(f"Push: {msg}")
    sync.stop()


def cmd_pull(args):
    """Manual pull."""
    config = load_config()
    if not config.enabled:
        print("hermes-sync: not configured")
        sys.exit(1)
    sync = HermesSync(config)
    sync.start()
    ok, msg, _, _ = sync.sync_now()
    print(f"Pull: {msg}")
    sync.stop()


def cmd_setup(args):
    """Interactive setup wizard."""
    from hermes_sync.config import detect_platform
    plat = detect_platform()

    print("hermes-sync setup")
    print("=" * 50)
    print()

    repo_url = input("GitHub repo URL (e.g. https://github.com/YOU/hermes-sync-state.git): ").strip()
    if not repo_url:
        print("Repo URL is required.")
        sys.exit(1)

    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        token = input("GitHub token (or set GH_TOKEN env var): ").strip()

    sync_skills = input("Sync skills? [Y/n]: ").strip().lower() != "n"
    sync_memories = input("Sync memories? [Y/n]: ").strip().lower() != "n"
    sync_cron = input("Sync cron jobs? [y/N]: ").strip().lower() == "y"
    sync_config = input("Sync config.yaml? [y/N]: ").strip().lower() == "y"
    sync_profiles = input("Sync profiles? [y/N]: ").strip().lower() == "y"

    config_path = Path(os.path.expanduser("~/.hermes/sync/config.yaml"))
    config_path.parent.mkdir(parents=True, exist_ok=True)

    import yaml
    cfg = {
        "backend": "github",
        "repo_url": repo_url,
        "sync_interval": 60,
        "sync_skills": sync_skills,
        "sync_memories": sync_memories,
        "sync_cron": sync_cron,
        "sync_config": sync_config,
        "sync_profiles": sync_profiles,
        "auto_resolve_conflicts": True,
        "platforms": [plat],
    }
    if token:
        cfg["token"] = token

    with open(config_path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)

    print(f"\nConfig written to {config_path}")
    print("Run 'hermes-sync start' to begin syncing.")


def main():
    parser = argparse.ArgumentParser(
        prog="hermes-sync",
        description="Cross-device sync for Hermes Agent — sync skills, memory, config, and profiles via GitHub.",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("start", help="Start sync daemon")
    sub.add_parser("status", help="Show sync status")
    sub.add_parser("push", help="Manual push")
    sub.add_parser("pull", help="Manual pull")
    sub.add_parser("setup", help="Interactive config wizard")

    args = parser.parse_args()

    commands = {
        "start": cmd_start,
        "status": cmd_status,
        "push": cmd_push,
        "pull": cmd_pull,
        "setup": cmd_setup,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
