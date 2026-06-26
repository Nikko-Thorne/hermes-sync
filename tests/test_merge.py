"""Tests for merge conflict detection and resolution."""

import sys
import tempfile
from pathlib import Path

_PLUGIN_DIR = Path(__file__).resolve().parent.parent / "plugin"
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

import pytest

from merge import (
    MergeConflict,
    detect_conflicts,
    resolve_conflict,
    resolve_all_ours,
    build_resolution_prompt,
    parse_resolution_response,
)


SIMPLE_CONFLICT = """# Test file

<<<<<<< HEAD
local line 1
local line 2
=======
remote line 1
remote line 2
>>>>>>> origin/main
"""

MULTIPLE_CONFLICTS = """# File with two conflicts

<<<<<<< HEAD
ours block 1
=======
theirs block 1
>>>>>>> origin/main

middle content

<<<<<<< HEAD
ours block 2
line 2
=======
theirs block 2
>>>>>>> origin/main
"""

NO_CONFLICT = "# Just a normal file\n\nwith some content\n"


class TestConflictDetection:
    """Test parsing git conflict markers."""

    def test_detect_single_conflict(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text(SIMPLE_CONFLICT)
        conflicts = detect_conflicts(tmp_path)
        assert len(conflicts) == 1
        assert conflicts[0].file_path == str(f)
        assert conflicts[0].ours == ["local line 1", "local line 2"]
        assert conflicts[0].theirs == ["remote line 1", "remote line 2"]

    def test_detect_multiple_conflicts(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text(MULTIPLE_CONFLICTS)
        conflicts = detect_conflicts(tmp_path)
        assert len(conflicts) == 2

    def test_no_conflicts_returns_empty(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text(NO_CONFLICT)
        conflicts = detect_conflicts(tmp_path)
        assert len(conflicts) == 0

    def test_ignores_git_dir(self, tmp_path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "conflicted").write_text(SIMPLE_CONFLICT)
        conflicts = detect_conflicts(tmp_path)
        assert len(conflicts) == 0

    def test_ignores_dotfiles(self, tmp_path):
        (tmp_path / ".conflicted").write_text(SIMPLE_CONFLICT)
        conflicts = detect_conflicts(tmp_path)
        assert len(conflicts) == 0

    def test_empty_dir(self, tmp_path):
        conflicts = detect_conflicts(tmp_path)
        assert len(conflicts) == 0


class TestConflictResolution:
    """Test applying resolutions to conflicts."""

    def test_resolve_ours(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text(SIMPLE_CONFLICT)
        conflicts = detect_conflicts(tmp_path)
        assert resolve_conflict(f, conflicts[0], "ours") is True
        content = f.read_text()
        assert "local line 1" in content
        assert "local line 2" in content
        assert "remote line 1" not in content
        assert "<<<<<<<" not in content

    def test_resolve_theirs(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text(SIMPLE_CONFLICT)
        conflicts = detect_conflicts(tmp_path)
        assert resolve_conflict(f, conflicts[0], "theirs") is True
        content = f.read_text()
        assert "remote line 1" in content
        assert "local line 1" not in content

    def test_resolve_custom_text(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text(SIMPLE_CONFLICT)
        conflicts = detect_conflicts(tmp_path)
        assert resolve_conflict(f, conflicts[0], "merged content here") is True
        content = f.read_text()
        assert "merged content here" in content
        assert "<<<<<<<" not in content

    def test_resolve_all_ours(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text(MULTIPLE_CONFLICTS)
        count = resolve_all_ours(tmp_path)
        assert count == 2
        content = f.read_text()
        assert "<<<<<<<" not in content
        assert "ours block 1" in content
        assert "ours block 2" in content
        assert "theirs block 1" not in content

    def test_resolve_multiple_conflicts_sequentially(self, tmp_path):
        """Resolve first conflict, then resolve_all_ours the rest."""
        f = tmp_path / "test.md"
        f.write_text(MULTIPLE_CONFLICTS)
        conflicts = detect_conflicts(tmp_path)
        assert len(conflicts) == 2

        # Resolve first individually, then use resolve_all_ours for cleanup
        resolve_conflict(f, conflicts[0], "ours")
        # resolve_all_ours handles any remaining
        resolve_all_ours(tmp_path)

        content = f.read_text()
        assert "ours block 1" in content
        assert "<<<<<<<" not in content
        assert ">>>>>>>" not in content


class TestConflictPrompt:
    """Test LLM prompt building and response parsing."""

    def test_build_prompt_for_single_conflict(self):
        conflict = MergeConflict(
            file_path="skills/test/SKILL.md",
            ours=["local change"],
            theirs=["remote change"],
            start_line=5,
        )
        prompt = build_resolution_prompt([conflict])
        assert "skills/test/SKILL.md" in prompt
        assert "local change" in prompt
        assert "remote change" in prompt
        assert "Line: 5" in prompt

    def test_build_prompt_empty(self):
        prompt = build_resolution_prompt([])
        assert "No conflicts" in prompt

    def test_parse_resolution_response_ours(self):
        response = "CONFLICT 1: ours\nCONFLICT 2: theirs"
        result = parse_resolution_response(response)
        assert result == {1: "ours", 2: "theirs"}

    def test_parse_resolution_response_merged(self):
        response = "CONFLICT 1: merged content here\nCONFLICT 2: ours"
        result = parse_resolution_response(response)
        assert result == {1: "merged content here", 2: "ours"}

    def test_parse_resolution_ignores_other_lines(self):
        response = "Here is my analysis:\nCONFLICT 1: ours\nMore commentary\nCONFLICT 2: theirs"
        result = parse_resolution_response(response)
        assert result == {1: "ours", 2: "theirs"}

    def test_parse_case_insensitive(self):
        response = "conflict 1: OURS\nConflict 2: THEIRS"
        result = parse_resolution_response(response)
        assert result == {1: "OURS", 2: "THEIRS"}


class TestMergeConflictProperties:
    """Test MergeConflict dataclass properties."""

    def test_ours_text(self):
        c = MergeConflict("f.md", ["a", "b"], ["c"], 1)
        assert c.ours_text == "a\nb"

    def test_theirs_text(self):
        c = MergeConflict("f.md", ["a"], ["c", "d"], 1)
        assert c.theirs_text == "c\nd"

    def test_describe(self):
        c = MergeConflict("f.md", ["local"], ["remote"], 42)
        desc = c.describe()
        assert "f.md" in desc
        assert "Line: 42" in desc
        assert "local" in desc
        assert "remote" in desc
