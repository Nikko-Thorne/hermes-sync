"""Merge conflict resolution for Hermes Sync.

Handles git merge conflicts in the sync repo by:
1. Detecting conflicts after a pull/rebase
2. Providing structured conflict descriptions for LLM resolution
3. Applying LLM-chosen resolutions

The key insight: the sync repo is a cache — we can safely
resolve conflicts by preferring one side or merging intelligently
without data loss risk. The source of truth is always the local
~/.hermes/skills/ and ~/.hermes/memories/ directories.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Git conflict markers
CONFLICT_START = "<<<<<<< "
CONFLICT_MID = "======="
CONFLICT_END = ">>>>>>> "


class MergeConflict:
    """A single merge conflict in a file."""

    def __init__(
        self,
        file_path: str,
        ours: List[str],
        theirs: List[str],
        start_line: int,
    ):
        self.file_path = file_path
        self.ours = ours  # Lines from our branch (local changes)
        self.theirs = theirs  # Lines from their branch (remote changes)
        self.start_line = start_line

    @property
    def ours_text(self) -> str:
        return "\n".join(self.ours)

    @property
    def theirs_text(self) -> str:
        return "\n".join(self.theirs)

    def describe(self) -> str:
        """Human-readable conflict description for LLM resolution."""
        return (
            "File: {}\n"
            "Line: {}\n"
            "\n--- OURS (local changes) ---\n"
            "{}\n"
            "--- THEIRS (remote changes) ---\n"
            "{}\n"
        ).format(
            self.file_path,
            self.start_line,
            self.ours_text,
            self.theirs_text,
        )


def detect_conflicts(repo_path: Path) -> List[MergeConflict]:
    """Scan the repo for git merge conflict markers.

    Returns list of MergeConflict objects found.
    """
    conflicts: List[MergeConflict] = []

    for file_path in repo_path.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.name.startswith("."):
            continue
        if ".git" in file_path.parts:
            continue

        try:
            content = file_path.read_text()
        except Exception:
            continue

        if CONFLICT_START not in content:
            continue

        conflicts.extend(_parse_conflicts(str(file_path), content))

    return conflicts


def _parse_conflicts(file_path: str, content: str) -> List[MergeConflict]:
    """Parse git conflict markers from file content."""
    conflicts = []
    lines = content.split("\n")
    i = 0

    while i < len(lines):
        if lines[i].startswith(CONFLICT_START):
            start_line = i + 1
            ours: List[str] = []
            theirs: List[str] = []
            side = "ours"
            i += 1

            while i < len(lines):
                line = lines[i]
                if line.startswith(CONFLICT_END):
                    break
                elif line == CONFLICT_MID:
                    side = "theirs"
                    i += 1
                    continue
                elif line.startswith(CONFLICT_START):
                    # Nested conflict — treat as ours content
                    ours.append(line)
                else:
                    if side == "ours":
                        ours.append(line)
                    else:
                        theirs.append(line)
                i += 1

            conflicts.append(MergeConflict(
                file_path=file_path,
                ours=ours,
                theirs=theirs,
                start_line=start_line,
            ))
            i += 1  # Skip the >>>>>>> line
        else:
            i += 1

    return conflicts


def resolve_conflict(
    file_path: Path,
    conflict: MergeConflict,
    resolution: str,  # "ours", "theirs", or merged content
) -> bool:
    """Apply a resolution to a merge conflict in a file.

    resolution can be:
    - "ours": keep our changes
    - "theirs": keep their changes
    - Any other string: replace the conflicted section with this content

    Returns True on success.
    """
    try:
        content = file_path.read_text()
    except Exception:
        return False

    # Build the conflict block as it appears in the file
    conflict_block = (
        CONFLICT_START + "\n"
        + "\n".join(conflict.ours) + "\n"
        + CONFLICT_MID + "\n"
        + "\n".join(conflict.theirs) + "\n"
        + CONFLICT_END
    )

    if resolution == "ours":
        replacement = "\n".join(conflict.ours)
    elif resolution == "theirs":
        replacement = "\n".join(conflict.theirs)
    else:
        replacement = resolution

    # Try exact match first, then with trailing newline
    if conflict_block in content:
        new_content = content.replace(conflict_block, replacement, 1)
    elif conflict_block + "\n" in content:
        new_content = content.replace(conflict_block + "\n", replacement, 1)
    else:
        # Fallback: line-by-line resolution of ALL conflicts
        lines = content.split("\n")
        out_lines = []
        in_conflict = False
        for line in lines:
            if line.startswith(CONFLICT_START):
                in_conflict = True
                if resolution == "ours":
                    out_lines.extend(conflict.ours)
                elif resolution == "theirs":
                    out_lines.extend(conflict.theirs)
                else:
                    out_lines.append(resolution)
                continue
            elif line == CONFLICT_MID and in_conflict:
                continue
            elif line.startswith(CONFLICT_END) and in_conflict:
                in_conflict = False
                continue
            elif not in_conflict:
                out_lines.append(line)
        new_content = "\n".join(out_lines)

    try:
        file_path.write_text(new_content)
        return True
    except Exception:
        return False


def resolve_all_ours(repo_path: Path) -> int:
    """Resolve all conflicts by taking 'ours' (local) version.

    This is the safe default — local changes always win.
    Returns number of conflicts resolved.
    """
    conflicts = detect_conflicts(repo_path)
    if not conflicts:
        return 0

    # Group conflicts by file
    by_file: Dict[str, List[MergeConflict]] = {}
    for c in conflicts:
        by_file.setdefault(c.file_path, []).append(c)

    resolved = 0
    for file_path_str, file_conflicts in by_file.items():
        file_path = Path(file_path_str)
        try:
            content = file_path.read_text()
        except Exception:
            continue

        lines = content.split("\n")
        out_lines = []
        in_conflict = False
        conflict_idx = -1

        for line in lines:
            if line.startswith(CONFLICT_START):
                in_conflict = True
                conflict_idx += 1
                if conflict_idx < len(file_conflicts):
                    out_lines.extend(file_conflicts[conflict_idx].ours)
                continue
            elif line == CONFLICT_MID and in_conflict:
                continue
            elif line.startswith(CONFLICT_END) and in_conflict:
                in_conflict = False
                continue
            elif not in_conflict:
                out_lines.append(line)

        try:
            file_path.write_text("\n".join(out_lines))
            resolved += len(file_conflicts)
            logger.info(
                "Resolved %d conflicts in %s (ours)",
                len(file_conflicts), file_path_str,
            )
        except Exception:
            pass

    return resolved


def build_resolution_prompt(conflicts: List[MergeConflict]) -> str:
    """Build an LLM prompt to resolve merge conflicts intelligently.

    The prompt describes each conflict and asks the LLM to choose
    ours, theirs, or a merge for each one.
    """
    if not conflicts:
        return "No conflicts to resolve."

    parts = [
        "The following merge conflicts were detected in the Hermes Sync sync repo. "
        "For each conflict, indicate whether to use OURS (local), THEIRS (remote), "
        "or provide a merged version.\n",
    ]

    for i, conflict in enumerate(conflicts, 1):
        parts.append("--- Conflict {} ---\n{}".format(i, conflict.describe()))

    parts.append(
        "\nRespond with one line per conflict: "
        "'CONFLICT N: ours', 'CONFLICT N: theirs', or 'CONFLICT N: <merged text>'"
    )

    return "\n".join(parts)


def parse_resolution_response(response: str) -> Dict[int, str]:
    """Parse LLM resolution response into {conflict_index: resolution}.

    Expects lines like:
        CONFLICT 1: ours
        CONFLICT 2: theirs
        CONFLICT 3: merged content here
    """
    resolutions: Dict[int, str] = {}

    pattern = re.compile(r"CONFLICT\s+(\d+):\s*(.+)", re.IGNORECASE)

    for line in response.strip().split("\n"):
        match = pattern.match(line.strip())
        if match:
            idx = int(match.group(1))
            resolution = match.group(2).strip()
            resolutions[idx] = resolution

    return resolutions
