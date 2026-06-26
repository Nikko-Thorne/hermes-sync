"""Ed25519 content signing and verification for Hermes Sync.

Generates keypairs, signs skill content hashes, and verifies
signatures. Integrates with git commits for verifiable authorship
without requiring GPG setup.

Uses PyNaCl (libsodium) for Ed25519 operations — the gold standard
for NaCl-based cryptography.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Optional, Tuple

import nacl.signing
import nacl.encoding

logger = logging.getLogger(__name__)

# Default location for the sync identity keypair
KEYPAIR_DIR = Path(os.path.expanduser("~/.hermes/sync"))


def generate_keypair() -> Tuple[str, str]:
    """Generate a new Ed25519 keypair.

    Returns (private_key_hex, public_key_hex).
    The private key is 64 hex chars (32 bytes seed).
    The public key is 64 hex chars (32 bytes).
    """
    signing_key = nacl.signing.SigningKey.generate()
    verify_key = signing_key.verify_key

    private_hex = signing_key.encode(encoder=nacl.encoding.HexEncoder).decode("ascii")
    public_hex = verify_key.encode(encoder=nacl.encoding.HexEncoder).decode("ascii")
    return private_hex, public_hex


def sign_content(content: str, private_key_hex: str) -> str:
    """Sign content with Ed25519 private key.

    Hashes content with SHA256 first, then signs the hash.
    Returns hex-encoded signature (128 hex chars).
    """
    content_hash = hashlib.sha256(content.encode("utf-8")).digest()
    signing_key = nacl.signing.SigningKey(
        private_key_hex, encoder=nacl.encoding.HexEncoder
    )
    signed = signing_key.sign(content_hash)
    # Return just the signature (last 64 bytes), not the signed message
    signature = signed.signature
    return signature.hex()


def verify_signature(content: str, signature_hex: str, public_key_hex: str) -> bool:
    """Verify an Ed25519 signature over content.

    Returns True if signature is valid for this content and public key.
    """
    try:
        content_hash = hashlib.sha256(content.encode("utf-8")).digest()
        verify_key = nacl.signing.VerifyKey(
            public_key_hex, encoder=nacl.encoding.HexEncoder
        )
        signature = bytes.fromhex(signature_hex)
        # PyNaCl format: signature (64 bytes) || message
        signed = signature + content_hash
        verify_key.verify(signed)
        return True
    except nacl.exceptions.BadSignatureError:
        return False
    except Exception as e:
        logger.warning("Signature verification error: %s", e)
        return False


def load_keypair() -> Optional[Tuple[str, str]]:
    """Load the sync identity keypair from disk.

    Returns (private_key_hex, public_key_hex) or None if no keypair exists.
    """
    private_path = KEYPAIR_DIR / "sync.key"
    public_path = KEYPAIR_DIR / "sync.pub"

    if not private_path.exists() or not public_path.exists():
        return None

    try:
        private_hex = private_path.read_text().strip()
        public_hex = public_path.read_text().strip()
        return private_hex, public_hex
    except Exception as e:
        logger.warning("Failed to load keypair: %s", e)
        return None


def ensure_keypair() -> Tuple[str, str]:
    """Load existing keypair or generate and save a new one.

    Returns (private_key_hex, public_key_hex).
    """
    existing = load_keypair()
    if existing is not None:
        return existing

    KEYPAIR_DIR.mkdir(parents=True, exist_ok=True)
    private_hex, public_hex = generate_keypair()

    private_path = KEYPAIR_DIR / "sync.key"
    public_path = KEYPAIR_DIR / "sync.pub"

    private_path.write_text(private_hex + "\n")
    private_path.chmod(0o600)

    public_path.write_text(public_hex + "\n")

    logger.info("Generated new Ed25519 keypair in %s", KEYPAIR_DIR)
    return private_hex, public_hex


def sign_commit_message(message: str, private_key_hex: str) -> str:
    """Sign a commit message and return the signature line.

    Returns a line like: 'Sync-Signature: <128 hex chars>'
    that can be appended to commit messages.
    """
    sig = sign_content(message, private_key_hex)
    return "Sync-Signature: {}".format(sig)


def verify_commit_message(message: str, public_key_hex: str) -> bool:
    """Verify a Sync-Signature embedded in a commit message.

    Extracts the 'Sync-Signature: <hex>' line from the message,
    verifies the rest of the message against it.
    """
    lines = message.split("\n")
    sig_line = None
    content_lines = []

    for line in lines:
        if line.startswith("Sync-Signature: "):
            sig_line = line
        else:
            content_lines.append(line)

    if sig_line is None:
        return False

    sig_hex = sig_line.split("Sync-Signature: ", 1)[1].strip()
    content = "\n".join(content_lines)

    return verify_signature(content, sig_hex, public_key_hex)
