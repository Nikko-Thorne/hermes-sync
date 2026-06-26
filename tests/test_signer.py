"""Tests for Ed25519 content signing and verification."""

import sys
from pathlib import Path

# Ensure plugin directory is importable
_PLUGIN_DIR = Path(__file__).resolve().parent.parent / "plugin"
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

import pytest

from security.signer import (
    generate_keypair,
    sign_content,
    verify_signature,
    load_keypair,
    ensure_keypair,
    sign_commit_message,
    verify_commit_message,
)


class TestEd25519Signer:
    """Test Ed25519 key generation, signing, and verification."""

    def test_generate_keypair_produces_valid_keys(self):
        priv, pub = generate_keypair()
        assert len(priv) == 64  # 32 bytes hex = 64 chars
        assert len(pub) == 64
        assert priv != pub

    def test_generate_keypair_unique_each_time(self):
        priv1, pub1 = generate_keypair()
        priv2, pub2 = generate_keypair()
        assert priv1 != priv2
        assert pub1 != pub2

    def test_sign_and_verify_valid(self):
        priv, pub = generate_keypair()
        content = "## test skill\nthis is content"
        sig = sign_content(content, priv)
        assert len(sig) == 128  # 64 bytes hex

        assert verify_signature(content, sig, pub) is True

    def test_wrong_public_key_fails(self):
        priv, pub = generate_keypair()
        _, other_pub = generate_keypair()
        content = "test content"
        sig = sign_content(content, priv)

        assert verify_signature(content, sig, other_pub) is False

    def test_tampered_content_fails(self):
        priv, pub = generate_keypair()
        content = "original content"
        sig = sign_content(content, priv)

        assert verify_signature("tampered content", sig, pub) is False

    def test_invalid_signature_fails(self):
        _, pub = generate_keypair()
        content = "test content"
        bad_sig = "00" * 64  # 64 bytes of zeros

        assert verify_signature(content, bad_sig, pub) is False

    def test_wrong_length_signature_fails(self):
        _, pub = generate_keypair()
        content = "test content"

        assert verify_signature(content, "aa", pub) is False

    def test_commit_message_signing_roundtrip(self):
        priv, pub = generate_keypair()
        message = "sync: added test skill\n\nCreated a new skill for testing"

        signed = message + "\n" + sign_commit_message(message, priv)
        assert verify_commit_message(signed, pub) is True

    def test_commit_verification_fails_without_signature(self):
        _, pub = generate_keypair()
        msg = "sync: plain commit"
        assert verify_commit_message(msg, pub) is False

    def test_commit_verification_fails_with_wrong_key(self):
        priv, _ = generate_keypair()
        _, other_pub = generate_keypair()
        msg = "sync: test"
        signed = msg + "\n" + sign_commit_message(msg, priv)
        assert verify_commit_message(signed, other_pub) is False

    def test_commit_verification_fails_tampered(self):
        priv, pub = generate_keypair()
        msg = "sync: original"
        signed = msg + "\n" + sign_commit_message(msg, priv)
        # Tamper with the message part
        tampered = "sync: tampered\n" + signed.split("\n", 1)[1]
        assert verify_commit_message(tampered, pub) is False

    def test_ensure_keypair_creates_and_reloads(self, monkeypatch, tmp_path):
        """ensure_keypair creates keypair, then reloads same keys."""
        import security.signer as signer_mod
        monkeypatch.setattr(signer_mod, "KEYPAIR_DIR", tmp_path)

        priv1, pub1 = ensure_keypair()
        assert (tmp_path / "sync.key").exists()
        assert (tmp_path / "sync.pub").exists()

        priv2, pub2 = ensure_keypair()
        assert priv1 == priv2
        assert pub1 == pub2

    def test_load_keypair_returns_none_when_missing(self, monkeypatch, tmp_path):
        import security.signer as signer_mod
        monkeypatch.setattr(signer_mod, "KEYPAIR_DIR", tmp_path / "nonexistent")
        assert load_keypair() is None

    def test_same_content_same_key_same_signature(self):
        """Same content + same key = deterministic signature (Ed25519 is deterministic)."""
        priv, pub = generate_keypair()
        content = "deterministic test"
        sig1 = sign_content(content, priv)
        sig2 = sign_content(content, priv)
        assert sig1 == sig2
        assert verify_signature(content, sig1, pub) is True


class TestSensitiveFiles:
    """Test .gitignore enforcement for blocked file patterns."""

    def test_blocks_env_file(self):
        from security.patterns import check_sensitive_files
        blocked = check_sensitive_files(["/path/.env"])
        assert blocked == ["/path/.env"]

    def test_blocks_auth_json(self):
        from security.patterns import check_sensitive_files
        blocked = check_sensitive_files(["/home/user/.hermes/auth.json"])
        assert len(blocked) == 1

    def test_blocks_pem_key(self):
        from security.patterns import check_sensitive_files
        blocked = check_sensitive_files(["my-cert.pem"])
        assert len(blocked) == 1

    def test_blocks_ssh_dir(self):
        from security.patterns import check_sensitive_files
        blocked = check_sensitive_files(["~/.ssh/id_rsa"])
        assert len(blocked) >= 1

    def test_allows_normal_files(self):
        from security.patterns import check_sensitive_files
        blocked = check_sensitive_files([
            "skills/devops/docker.md",
            "memories/USER.md",
            "skills/creative/ascii-art/SKILL.md",
        ])
        assert blocked == []

    def test_blocks_plugin_config(self):
        from security.patterns import check_sensitive_files
        blocked = check_sensitive_files(["config.yaml"])
        assert len(blocked) == 1

    def test_blocks_mixed_batch(self):
        from security.patterns import check_sensitive_files
        blocked = check_sensitive_files([
            "skills/devops/normal.md",
            ".env",
            "skills/creative/SKILL.md",
            "auth.json",
        ])
        assert len(blocked) == 2
        assert ".env" in blocked or any(".env" in b for b in blocked)
