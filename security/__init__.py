"""Hermes Sync security module.

Provides security scanning, secret redaction, and content signing
for skills before they leave the local machine.
"""

from .patterns import (
    scan_content,
    scan_secrets,
    scan_injections,
    scan_dangerous_commands,
    scan_entropy,
    redact_content,
    strip_env_refs,
    strip_sensitive_paths,
    check_sensitive_files,
    BLOCKED_FILE_PATTERNS,
    BLOCKED_DIR_PATTERNS,
    ScanResult,
)

from .signer import (
    generate_keypair,
    sign_content,
    verify_signature,
    load_keypair,
    ensure_keypair,
    sign_commit_message,
    verify_commit_message,
)

__all__ = [
    # Patterns
    "scan_content",
    "scan_secrets",
    "scan_injections",
    "scan_dangerous_commands",
    "scan_entropy",
    "redact_content",
    "strip_env_refs",
    "strip_sensitive_paths",
    "check_sensitive_files",
    "BLOCKED_FILE_PATTERNS",
    "BLOCKED_DIR_PATTERNS",
    "ScanResult",
    # Signer
    "generate_keypair",
    "sign_content",
    "verify_signature",
    "load_keypair",
    "ensure_keypair",
    "sign_commit_message",
    "verify_commit_message",
]
