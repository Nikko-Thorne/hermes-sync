"""Test configuration for Hermes Sync."""

import sys
from pathlib import Path

# Make the plugin directory importable for tests
_PLUGIN_DIR = Path(__file__).resolve().parent.parent / "plugin"
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))
