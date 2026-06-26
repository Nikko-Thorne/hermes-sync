#!/usr/bin/env python3
"""Git ASKPASS helper for Hermes Sync.

Reads the token from HERMES_SYNC_TOKEN env var and outputs it
in the format git expects. Never touches the URL — the token
only lives in env, not in .git/config.
"""
import os
import sys

token = os.environ.get("HERMES_SYNC_TOKEN", "")
if not token:
    sys.exit(1)

# git ASKPASS contract: echo the password to stdout
print(token)
