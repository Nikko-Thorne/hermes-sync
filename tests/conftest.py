"""Test configuration for Hermes Sync."""

import sys
from pathlib import Path

# Ensure the repo root is on sys.path so hermes_sync is importable
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
