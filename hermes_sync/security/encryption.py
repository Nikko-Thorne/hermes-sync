"""Secrets encryption for Hermes Sync.

Encrypts sensitive files (.env, auth.json, credential pools) before
syncing to the remote repo. Uses age encryption (rage CLI or
age library) with a device-specific keypair.

Files are encrypted at rest in the sync repo. Each device has its own
age identity. On pull, encrypted files are decrypted with the local
identity and written to the appropriate Hermes paths.

Architecture:
    Local .env ──► encrypt ──► sync-repo/secrets/env.age ──► decrypt ──► Local .env
    Local auth.json ──► encrypt ──► sync-repo/secrets/auth.age ──► decrypt ──► Local auth.json

The age identity lives at ~/.hermes/sync/age.key (mode 0600).
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

AGE_KEY_PATH = Path(os.path.expanduser("~/.hermes/sync/age.key"))

# Files that should be encrypted before syncing
ENCRYPTED_FILE_MAP = {
    ".env": "env.age",
    "auth.json": "auth.age",
    "config.yaml": "config.age",  # if sync_config enabled, encrypt config
}


def ensure_age_keypair() -> Tuple[str, str]:
    """Ensure an age keypair exists for this device.

    Returns (public_key, private_key_path).
    Generates a new keypair if one doesn't exist.
    """
    AGE_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)

    if AGE_KEY_PATH.exists():
        # Read existing public key
        pubkey = _extract_public_key()
        if pubkey:
            return pubkey, str(AGE_KEY_PATH)

    # Generate new keypair
    result = subprocess.run(
        ["age-keygen", "-o", str(AGE_KEY_PATH)],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"age-keygen failed: {result.stderr}")

    # Set restrictive permissions
    try:
        AGE_KEY_PATH.chmod(0o600)
    except Exception:
        pass

    pubkey = _extract_public_key()
    if not pubkey:
        raise RuntimeError("Failed to extract public key from age-keygen output")

    logger.info("Generated new age keypair at %s (pubkey: %s)", AGE_KEY_PATH, pubkey[:20] + "...")
    return pubkey, str(AGE_KEY_PATH)


def _extract_public_key() -> Optional[str]:
    """Extract the public key from an age identity file."""
    try:
        output = subprocess.run(
            ["age-keygen", "-y", str(AGE_KEY_PATH)],
            capture_output=True, text=True, timeout=10,
        )
        if output.returncode == 0:
            return output.stdout.strip()
    except Exception:
        pass

    # Fallback: parse the identity file directly
    try:
        content = AGE_KEY_PATH.read_text()
        for line in content.split("\n"):
            if line.startswith("# public key: "):
                return line.split(": ", 1)[1].strip()
    except Exception:
        pass

    return None


def encrypt_file(source: Path, dest: Path, public_key: str) -> bool:
    """Encrypt a file with age for the given public key.

    Args:
        source: Path to the plaintext file.
        dest: Path to write the encrypted .age file.
        public_key: age public key (age1... format).

    Returns True on success.
    """
    try:
        result = subprocess.run(
            ["age", "-r", public_key, "-o", str(dest), str(source)],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            logger.error("age encrypt failed: %s", result.stderr)
            return False
        logger.debug("Encrypted %s -> %s", source.name, dest.name)
        return True
    except FileNotFoundError:
        logger.error("age CLI not found — install it: https://github.com/FiloSottile/age")
        return False
    except Exception as e:
        logger.error("Encryption error: %s", e)
        return False


def decrypt_file(source: Path, dest: Path, identity_path: Optional[str] = None) -> bool:
    """Decrypt an age-encrypted file.

    Args:
        source: Path to the .age file.
        dest: Path to write the decrypted plaintext.
        identity_path: Path to age identity file (defaults to ~/.hermes/sync/age.key).

    Returns True on success.
    """
    identity = identity_path or str(AGE_KEY_PATH)

    if not os.path.exists(identity):
        logger.error("age identity not found at %s", identity)
        return False

    try:
        result = subprocess.run(
            ["age", "-d", "-i", identity, "-o", str(dest), str(source)],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            logger.error("age decrypt failed: %s", result.stderr)
            return False
        logger.debug("Decrypted %s -> %s", source.name, dest.name)
        return True
    except FileNotFoundError:
        logger.error("age CLI not found")
        return False
    except Exception as e:
        logger.error("Decryption error: %s", e)
        return False


def encrypt_secrets_for_push(
    hermes_home: Path,
    repo_path: Path,
    public_key: str,
    sync_categories: dict,
) -> List[str]:
    """Encrypt secret files before pushing to the sync repo.

    Reads files from hermes_home, encrypts them, writes to repo_path/secrets/.

    Returns list of encrypted filenames.
    """
    secrets_dir = repo_path / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)

    encrypted = []

    file_map = {
        ".env": sync_categories.get("sync_config", False),
        "auth.json": sync_categories.get("sync_config", False),
        "config.yaml": sync_categories.get("sync_config", False),
    }

    for filename, should_sync in file_map.items():
        if not should_sync:
            continue

        source = hermes_home / filename
        if not source.exists():
            continue

        dest_name = ENCRYPTED_FILE_MAP.get(filename, f"{filename}.age")
        dest = secrets_dir / dest_name

        if encrypt_file(source, dest, public_key):
            encrypted.append(dest_name)

    return encrypted


def decrypt_secrets_after_pull(
    repo_path: Path,
    hermes_home: Path,
    sync_categories: dict,
    identity_path: Optional[str] = None,
) -> List[str]:
    """Decrypt secret files after pulling from the sync repo.

    Reads encrypted files from repo_path/secrets/, decrypts to hermes_home.

    Returns list of decrypted filenames.
    """
    secrets_dir = repo_path / "secrets"
    if not secrets_dir.is_dir():
        return []

    decrypted = []
    identity = identity_path or str(AGE_KEY_PATH)

    # Reverse map: encrypted name -> local name
    reverse_map = {v: k for k, v in ENCRYPTED_FILE_MAP.items()}

    for age_file in secrets_dir.iterdir():
        if not age_file.suffix == ".age":
            continue

        local_name = reverse_map.get(age_file.name)
        if local_name is None:
            continue

        # Only decrypt if this category is synced
        if local_name in (".env", "auth.json", "config.yaml"):
            if not sync_categories.get("sync_config", False):
                continue

        dest = hermes_home / local_name

        if decrypt_file(age_file, dest, identity):
            decrypted.append(local_name)
            # Set restrictive permissions on decrypted files
            try:
                dest.chmod(0o600)
            except Exception:
                pass

    return decrypted


def is_age_available() -> bool:
    """Check if the age CLI is installed."""
    try:
        result = subprocess.run(
            ["age", "-version"],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False
    except Exception:
        return False
