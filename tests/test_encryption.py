"""Tests for age-based secrets encryption."""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pytest

from hermes_sync.security.encryption import (
    ensure_age_keypair,
    is_age_available,
    AGE_KEY_PATH,
    ENCRYPTED_FILE_MAP,
    _extract_public_key,
)


class TestEncryptionBasics:
    """Test encryption availability and key management."""

    def test_encrypted_file_map_coverage(self):
        """Ensure all expected sensitive files are in the map."""
        assert ".env" in ENCRYPTED_FILE_MAP
        assert "auth.json" in ENCRYPTED_FILE_MAP
        assert "config.yaml" in ENCRYPTED_FILE_MAP
        assert ENCRYPTED_FILE_MAP[".env"] == "env.age"
        assert ENCRYPTED_FILE_MAP["auth.json"] == "auth.age"

    def test_is_age_available(self):
        """is_age_available() should not raise."""
        result = is_age_available()
        assert isinstance(result, bool)

    def test_extract_public_key_nonexistent(self, monkeypatch, tmp_path):
        """_extract_public_key() returns None when no key exists."""
        import hermes_sync.security.encryption as enc_mod
        monkeypatch.setattr(enc_mod, "AGE_KEY_PATH", tmp_path / "nonexistent.age")
        result = _extract_public_key()
        assert result is None

    def test_ensure_age_keypair_creates_key(self, monkeypatch, tmp_path):
        """ensure_age_keypair() creates a new keypair."""
        if not is_age_available():
            pytest.skip("age CLI not installed")

        import hermes_sync.security.encryption as enc_mod
        key_path = tmp_path / "test_age.key"
        monkeypatch.setattr(enc_mod, "AGE_KEY_PATH", key_path)

        pubkey, path = ensure_age_keypair()
        assert key_path.exists()
        assert pubkey.startswith("age1")
        assert path == str(key_path)

    def test_ensure_age_keypair_reuses_existing(self, monkeypatch, tmp_path):
        """ensure_age_keypair() reuses an existing keypair."""
        if not is_age_available():
            pytest.skip("age CLI not installed")

        import hermes_sync.security.encryption as enc_mod
        key_path = tmp_path / "test_age.key"
        monkeypatch.setattr(enc_mod, "AGE_KEY_PATH", key_path)

        pubkey1, _ = ensure_age_keypair()
        pubkey2, _ = ensure_age_keypair()
        assert pubkey1 == pubkey2


class TestEncryptDecrypt:
    """Test round-trip encryption/decryption."""

    def test_encrypt_decrypt_roundtrip(self, monkeypatch, tmp_path):
        """Encrypt then decrypt should return original content."""
        if not is_age_available():
            pytest.skip("age CLI not installed")

        import hermes_sync.security.encryption as enc_mod
        key_path = tmp_path / "age.key"
        monkeypatch.setattr(enc_mod, "AGE_KEY_PATH", key_path)

        pubkey, ident_path = ensure_age_keypair()

        plaintext = tmp_path / "test.txt"
        encrypted = tmp_path / "test.txt.age"
        decrypted = tmp_path / "test_decrypted.txt"

        plaintext.write_text("API_KEY=secret123\nTOKEN=abc.def.ghi\n")

        from hermes_sync.security.encryption import encrypt_file, decrypt_file
        assert encrypt_file(plaintext, encrypted, pubkey) is True
        assert encrypted.exists()
        assert "secret123" not in encrypted.read_text()

        assert decrypt_file(encrypted, decrypted, ident_path) is True
        assert decrypted.read_text() == "API_KEY=secret123\nTOKEN=abc.def.ghi\n"

    def test_encrypt_nonexistent_source(self, monkeypatch, tmp_path):
        """Encrypting a non-existent file returns False."""
        if not is_age_available():
            pytest.skip("age CLI not installed")

        import hermes_sync.security.encryption as enc_mod
        key_path = tmp_path / "age.key"
        monkeypatch.setattr(enc_mod, "AGE_KEY_PATH", key_path)

        pubkey, _ = ensure_age_keypair()

        from hermes_sync.security.encryption import encrypt_file
        assert encrypt_file(tmp_path / "does_not_exist", tmp_path / "out.age", pubkey) is False

    def test_decrypt_with_wrong_key(self, monkeypatch, tmp_path):
        """Decrypting with the wrong identity returns False."""
        if not is_age_available():
            pytest.skip("age CLI not installed")

        import hermes_sync.security.encryption as enc_mod
        key_path_a = tmp_path / "age_a.key"
        key_path_b = tmp_path / "age_b.key"
        monkeypatch.setattr(enc_mod, "AGE_KEY_PATH", key_path_a)

        pubkey_a, _ = ensure_age_keypair()

        # Generate a second keypair
        monkeypatch.setattr(enc_mod, "AGE_KEY_PATH", key_path_b)
        _, ident_b = ensure_age_keypair()

        plaintext = tmp_path / "secret.txt"
        encrypted = tmp_path / "secret.txt.age"
        decrypted = tmp_path / "decrypted.txt"

        plaintext.write_text("secret data")

        from hermes_sync.security.encryption import encrypt_file, decrypt_file
        assert encrypt_file(plaintext, encrypted, pubkey_a) is True

        # Try to decrypt with key B — should fail
        assert decrypt_file(encrypted, decrypted, ident_b) is False


class TestSecretsFlow:
    """Test the bulk encrypt/decrypt workflow."""

    def test_encrypt_secrets_for_push(self, monkeypatch, tmp_path):
        """encrypt_secrets_for_push encrypts configured files."""
        if not is_age_available():
            pytest.skip("age CLI not installed")

        import hermes_sync.security.encryption as enc_mod
        key_path = tmp_path / "age.key"
        monkeypatch.setattr(enc_mod, "AGE_KEY_PATH", key_path)

        pubkey, _ = ensure_age_keypair()

        hermes_home = tmp_path / "hermes"
        hermes_home.mkdir()
        (hermes_home / ".env").write_text("SECRET=value")
        (hermes_home / "auth.json").write_text('{"token":"abc"}')

        repo_path = tmp_path / "repo"

        from hermes_sync.security.encryption import encrypt_secrets_for_push
        encrypted = encrypt_secrets_for_push(
            hermes_home, repo_path, pubkey,
            {"sync_config": True},
        )
        assert "env.age" in encrypted or ".env" in [e for e in encrypted]
        secrets_dir = repo_path / "secrets"
        assert secrets_dir.is_dir()
        assert len(list(secrets_dir.iterdir())) > 0

    def test_encrypt_secrets_skips_when_disabled(self, monkeypatch, tmp_path):
        """encrypt_secrets_for_push skips when sync_config=False."""
        if not is_age_available():
            pytest.skip("age CLI not installed")

        import hermes_sync.security.encryption as enc_mod
        key_path = tmp_path / "age.key"
        monkeypatch.setattr(enc_mod, "AGE_KEY_PATH", key_path)

        pubkey, _ = ensure_age_keypair()

        hermes_home = tmp_path / "hermes"
        hermes_home.mkdir()
        (hermes_home / ".env").write_text("SECRET=value")
        repo_path = tmp_path / "repo"

        from hermes_sync.security.encryption import encrypt_secrets_for_push
        encrypted = encrypt_secrets_for_push(
            hermes_home, repo_path, pubkey,
            {"sync_config": False},
        )
        assert encrypted == []

    def test_decrypt_secrets_after_pull(self, monkeypatch, tmp_path):
        """decrypt_secrets_after_pull decrypts and restores files."""
        if not is_age_available():
            pytest.skip("age CLI not installed")

        import hermes_sync.security.encryption as enc_mod
        key_path = tmp_path / "age.key"
        monkeypatch.setattr(enc_mod, "AGE_KEY_PATH", key_path)

        pubkey, ident = ensure_age_keypair()

        hermes_home = tmp_path / "hermes"
        hermes_home.mkdir()
        (hermes_home / ".env").write_text("SECRET=mysecret")

        repo_path = tmp_path / "repo"
        secrets_dir = repo_path / "secrets"
        secrets_dir.mkdir(parents=True)

        from hermes_sync.security.encryption import (
            encrypt_secrets_for_push, decrypt_secrets_after_pull,
        )
        encrypt_secrets_for_push(hermes_home, repo_path, pubkey, {"sync_config": True})

        # Remove original to simulate fresh pull
        (hermes_home / ".env").unlink()

        decrypted = decrypt_secrets_after_pull(
            repo_path, hermes_home, {"sync_config": True}, ident,
        )
        assert ".env" in decrypted or "env.age" in [d for d in decrypted]
        assert (hermes_home / ".env").exists()
        assert (hermes_home / ".env").read_text() == "SECRET=mysecret"
