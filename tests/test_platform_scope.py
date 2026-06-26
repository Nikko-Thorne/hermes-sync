"""Tests for platform scoping — filtering skills by OS requirements."""

import sys
import tempfile
from pathlib import Path

_PLUGIN_DIR = Path(__file__).resolve().parent.parent / "plugin"
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

import pytest
from sync import _skill_matches_platform, _copy_dir_platform_scoped, _parse_yaml_frontmatter


class TestYamlFrontmatter:
    """Test YAML frontmatter parsing from skill files."""

    def test_parse_with_platforms(self):
        content = "---\nplatforms: [linux, macos]\n---\n\n# Skill body"
        fm = _parse_yaml_frontmatter(content)
        assert fm == {"platforms": ["linux", "macos"]}

    def test_parse_empty_frontmatter(self):
        content = "---\n---\n\n# No fields"
        fm = _parse_yaml_frontmatter(content)
        assert fm == {}

    def test_parse_no_frontmatter(self):
        content = "# Just markdown, no frontmatter"
        fm = _parse_yaml_frontmatter(content)
        assert fm == {}

    def test_parse_with_name_and_platforms(self):
        content = "---\nname: test-skill\nplatforms: [linux]\ndescription: test\n---\n\nbody"
        fm = _parse_yaml_frontmatter(content)
        assert fm["name"] == "test-skill"
        assert fm["platforms"] == ["linux"]

    def test_parse_malformed_yaml_returns_empty(self):
        content = "---\n[[bad yaml!!!\n---\n\nbody"
        fm = _parse_yaml_frontmatter(content)
        assert fm == {}


class TestPlatformMatching:
    """Test platform requirement matching logic."""

    def test_linux_skill_matches_linux(self, tmp_path):
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nplatforms: [linux]\n---\n\n# Linux-only skill"
        )
        assert _skill_matches_platform(skill_dir, "linux") is True

    def test_linux_skill_rejects_macos(self, tmp_path):
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nplatforms: [linux]\n---\n\n# Linux-only skill"
        )
        assert _skill_matches_platform(skill_dir, "macos") is False

    def test_multi_platform_skill_matches_any(self, tmp_path):
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nplatforms: [linux, macos, windows]\n---\n\n# Cross-platform"
        )
        assert _skill_matches_platform(skill_dir, "linux") is True
        assert _skill_matches_platform(skill_dir, "macos") is True
        assert _skill_matches_platform(skill_dir, "windows") is True

    def test_no_platforms_field_matches_all(self, tmp_path):
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: universal\n---\n\n# No platform restriction"
        )
        assert _skill_matches_platform(skill_dir, "linux") is True
        assert _skill_matches_platform(skill_dir, "macos") is True
        assert _skill_matches_platform(skill_dir, "windows") is True

    def test_no_skill_md_matches_all(self, tmp_path):
        # Directory without SKILL.md is not a skill — always passes
        assert _skill_matches_platform(tmp_path, "linux") is True

    def test_empty_platforms_list_matches_all(self, tmp_path):
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nplatforms: []\n---\n\n# Empty platforms"
        )
        assert _skill_matches_platform(skill_dir, "linux") is True


class TestPlatformScopedCopy:
    """Test directory copy with platform filtering."""

    def test_filters_out_non_matching_skill(self, tmp_path):
        src = tmp_path / "src"
        dst = tmp_path / "dst"

        linux_skill = src / "linux-only"
        linux_skill.mkdir(parents=True)
        (linux_skill / "SKILL.md").write_text(
            "---\nplatforms: [linux]\n---\n\n# Linux only"
        )
        (linux_skill / "ref.md").write_text("reference")

        mac_skill = src / "mac-only"
        mac_skill.mkdir(parents=True)
        (mac_skill / "SKILL.md").write_text(
            "---\nplatforms: [macos]\n---\n\n# Mac only"
        )

        universal = src / "universal"
        universal.mkdir(parents=True)
        (universal / "SKILL.md").write_text(
            "---\nname: universal\n---\n\n# Works everywhere"
        )

        _copy_dir_platform_scoped(src, dst, "linux")

        assert (dst / "linux-only").exists()
        assert (dst / "linux-only" / "SKILL.md").exists()
        assert (dst / "linux-only" / "ref.md").exists()
        assert (dst / "universal").exists()
        assert not (dst / "mac-only").exists()

    def test_copies_non_skill_dirs_always(self, tmp_path):
        src = tmp_path / "src"
        dst = tmp_path / "dst"

        # A directory without SKILL.md is not a skill — always copied
        data_dir = src / "data"
        data_dir.mkdir(parents=True)
        (data_dir / "file.txt").write_text("data")

        _copy_dir_platform_scoped(src, dst, "linux")
        assert (dst / "data" / "file.txt").exists()

    def test_preserves_metadata_files_in_skill(self, tmp_path):
        src = tmp_path / "src"
        dst = tmp_path / "dst"

        skill = src / "my-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\nplatforms: [linux]\n---\n\n# Skill"
        )
        ref_dir = skill / "references"
        ref_dir.mkdir(parents=True, exist_ok=True)
        (ref_dir / "api.md").write_text("api ref")

        _copy_dir_platform_scoped(src, dst, "linux")

        assert (dst / "my-skill" / "SKILL.md").exists()
        assert (dst / "my-skill" / "references" / "api.md").exists()
