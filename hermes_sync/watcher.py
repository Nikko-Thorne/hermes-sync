"""Filesystem watcher for Hermes Sync —  inotify-based change detection.

Uses Linux inotify for instant notification of skill/memory/cron
changes. Falls back to polling on non-Linux platforms.

When a change is detected, triggers a sync push via the callback.
Includes a debounce window to avoid rapid-fire pushes during
bulk operations (e.g., skill install, multi-file edits).
"""

from __future__ import annotations

import logging
import os
import select
import struct
import threading
import time
from ctypes import (
    CDLL,
    c_int,
    c_char_p,
    c_uint32,
    get_errno,
    addressof,
    create_string_buffer,
)
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ── inotify constants ──────────────────────────────────────────────

INOTIFY_AVAILABLE = False
try:
    _libc = CDLL("libc.so.6", use_errno=True)

    # inotify_init1
    _inotify_init1 = _libc.inotify_init1
    _inotify_init1.argtypes = [c_int]
    _inotify_init1.restype = c_int

    # inotify_add_watch
    _inotify_add_watch = _libc.inotify_add_watch
    _inotify_add_watch.argtypes = [c_int, c_char_p, c_uint32]
    _inotify_add_watch.restype = c_int

    # inotify_rm_watch
    _inotify_rm_watch = _libc.inotify_rm_watch
    _inotify_rm_watch.argtypes = [c_int, c_int]
    _inotify_rm_watch.restype = c_int

    IN_CLOSE_WRITE = 0x00000008
    IN_CREATE = 0x00000100
    IN_DELETE = 0x00000200
    IN_MOVED_TO = 0x00000080
    IN_MOVED_FROM = 0x00000040
    IN_DELETE_SELF = 0x00000400
    IN_MOVE_SELF = 0x00000800
    IN_ONLYDIR = 0x01000000
    IN_NONBLOCK = 0x00004000
    IN_CLOEXEC = 0x02000000

    INOTIFY_AVAILABLE = True
except (OSError, AttributeError):
    pass

# Events we care about for triggering sync (only meaningful when INOTIFY_AVAILABLE)
if INOTIFY_AVAILABLE:
    WATCH_MASK = (
        IN_CLOSE_WRITE | IN_CREATE | IN_DELETE
        | IN_MOVED_TO | IN_MOVED_FROM
    )
    EVENT_STRUCT_FORMAT = "iIII"
    EVENT_STRUCT_SIZE = struct.calcsize(EVENT_STRUCT_FORMAT)

DEBOUNCE_SECONDS = 2.0  # Wait after last change before triggering sync


class InotifyWatcher:
    """Linux inotify-based filesystem watcher."""

    def __init__(
        self,
        paths: List[Path],
        on_change: Callable[[], None],
        debounce: float = DEBOUNCE_SECONDS,
    ):
        if not INOTIFY_AVAILABLE:
            raise RuntimeError("inotify not available on this platform")

        self._paths = paths
        self._on_change = on_change
        self._debounce = debounce
        self._fd: Optional[int] = None
        self._wd_to_path: Dict[int, str] = {}  # watch descriptor -> path
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start watching in a background thread."""
        if self._running:
            return

        self._fd = _inotify_init1(IN_NONBLOCK | IN_CLOEXEC)
        if self._fd < 0:
            raise OSError(get_errno(), "inotify_init1 failed")

        # Add watches for all paths (recursive)
        for path in self._paths:
            self._add_watch_recursive(str(path))

        self._running = True
        self._thread = threading.Thread(
            target=self._watch_loop, daemon=True, name="hermes-sync-inotify"
        )
        self._thread.start()
        logger.info(
            "InotifyWatcher started — watching %d paths", len(self._wd_to_path)
        )

    def stop(self) -> None:
        """Stop watching."""
        self._running = False
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    def _add_watch_recursive(self, path: str) -> None:
        """Add inotify watch for a directory and all subdirectories."""
        try:
            wd = _inotify_add_watch(
                self._fd,
                path.encode("utf-8"),
                WATCH_MASK,
            )
            if wd >= 0:
                self._wd_to_path[wd] = path
        except Exception:
            return

        # Recurse into subdirectories
        try:
            for entry in os.scandir(path):
                if entry.is_dir() and not entry.name.startswith("."):
                    self._add_watch_recursive(entry.path)
        except PermissionError:
            pass

    def _watch_loop(self) -> None:
        """Main event loop — blocks on inotify fd, debounces, fires callback."""
        last_event_time = 0.0
        pending = False

        poll = select.poll()
        poll.register(self._fd, select.POLLIN)

        while self._running:
            try:
                events = poll.poll(1000)  # 1 second timeout
            except Exception:
                break

            if not events:
                # No events — if pending and past debounce, fire
                if pending and (time.monotonic() - last_event_time) >= self._debounce:
                    pending = False
                    self._fire_callback()
                continue

            try:
                # Read event buffer
                buf = os.read(self._fd, 4096)
            except (OSError, BlockingIOError):
                continue

            # Parse events
            pos = 0
            while pos + EVENT_STRUCT_SIZE <= len(buf):
                wd, mask, cookie, name_len = struct.unpack_from(
                    EVENT_STRUCT_FORMAT, buf, pos
                )
                pos += EVENT_STRUCT_SIZE + name_len

                # Ignore events we don't care about
                if mask & (IN_CREATE | IN_MOVED_TO):
                    # New directory created — add a watch for it
                    if mask & IN_ONLYDIR:
                        dirpath = self._wd_to_path.get(wd, "")
                        if dirpath and name_len > 0:
                            name = buf[pos - name_len : pos].rstrip(b"\x00").decode("utf-8", errors="replace")
                            new_path = os.path.join(dirpath, name)
                            if os.path.isdir(new_path) and not name.startswith("."):
                                self._add_watch_recursive(new_path)

                if mask & (IN_CLOSE_WRITE | IN_CREATE | IN_DELETE | IN_MOVED_TO | IN_MOVED_FROM):
                    last_event_time = time.monotonic()
                    pending = True

    def _fire_callback(self) -> None:
        """Fire the change callback (runs in watcher thread)."""
        try:
            self._on_change()
        except Exception as e:
            logger.error("Watcher callback error: %s", e)


class PollingWatcher:
    """Polling-based watcher for non-Linux platforms."""

    def __init__(
        self,
        paths: List[Path],
        on_change: Callable[[], None],
        interval: float = 60.0,
    ):
        self._paths = paths
        self._on_change = on_change
        self._interval = interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_mtimes: Dict[str, float] = {}

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="hermes-sync-poll-watch"
        )
        self._thread.start()
        logger.info("PollingWatcher started (interval=%ds)", self._interval)

    def stop(self) -> None:
        self._running = False

    def _poll_loop(self) -> None:
        while self._running:
            time.sleep(self._interval)
            if not self._running:
                break
            if self._scan_for_changes():
                try:
                    self._on_change()
                except Exception as e:
                    logger.error("Polling callback error: %s", e)

    def _scan_for_changes(self) -> bool:
        for watch_dir in self._paths:
            if not watch_dir.is_dir():
                continue
            for file_path in watch_dir.rglob("*"):
                if file_path.is_file() and not file_path.name.startswith("."):
                    try:
                        mtime = file_path.stat().st_mtime
                        key = str(file_path)
                        if key not in self._last_mtimes or self._last_mtimes[key] != mtime:
                            self._last_mtimes[key] = mtime
                            return True
                    except OSError:
                        pass
        return False


def create_watcher(
    paths: List[Path],
    on_change: Callable[[], None],
) -> InotifyWatcher | PollingWatcher:
    """Create the best available watcher for this platform.

    Returns an InotifyWatcher on Linux, PollingWatcher elsewhere.
    """
    if INOTIFY_AVAILABLE:
        return InotifyWatcher(paths, on_change)
    else:
        return PollingWatcher(paths, on_change)
