"""Security scanning patterns for Hermes Sync.

Regex patterns and entropy detection for:
- Secret/credential detection
- Prompt injection detection
- Dangerous command detection
- Environment isolation
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Secret detection patterns (aligned with Hermes core security.redact_secrets)
# ---------------------------------------------------------------------------

SECRET_PATTERNS: List[Tuple[str, str, re.Pattern]] = [
    # Name, description, compiled regex
    # More permissive: match sk- or sk-proj- followed by 40+ chars
    ("openai_key", "OpenAI API key", re.compile(
        r'sk-(?:proj-)?[A-Za-z0-9_\-]{40,}'
    )),
    ("github_pat", "GitHub Personal Access Token", re.compile(
        r'(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}'
    )),
    ("github_pat_classic", "GitHub classic PAT", re.compile(
        r'ghp_[A-Za-z0-9]{36,}'
    )),
    ("aws_access_key", "AWS Access Key ID", re.compile(
        r'(?:AKIA|ASIA)[A-Z0-9]{16}'
    )),
    ("aws_secret_key", "AWS Secret Access Key", re.compile(
        r'(?:"|\'|^)(?=.*[A-Z])(?=.*[a-z])(?=.*\d)[A-Za-z0-9+/]{40}(?:"|\'|$)'
    )),
    ("google_api_key", "Google API key", re.compile(
        r'AIza[0-9A-Za-z\-_]{35}'
    )),
    ("jwt_token", "JWT token", re.compile(
        r'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}'
    )),
    ("private_key_pem", "PEM private key", re.compile(
        r'-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----'
    )),
    ("slack_token", "Slack token", re.compile(
        r'xox[bpsar]-[A-Za-z0-9-]{10,}'
    )),
    ("discord_token", "Discord bot token", re.compile(
        r'[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27}'
    )),
    ("heroku_key", "Heroku API key", re.compile(
        r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
    )),
    ("stripe_live_key", "Stripe live key", re.compile(
        r'sk_live_[0-9a-zA-Z]{24,}'
    )),
    ("stripe_test_key", "Stripe test key", re.compile(
        r'sk_test_[0-9a-zA-Z]{24,}'
    )),
]


# ---------------------------------------------------------------------------
# Entropy-based detection
# ---------------------------------------------------------------------------

def shannon_entropy(data: str) -> float:
    """Calculate Shannon entropy of a string in bits per character.

    Uses collections.Counter for O(n) single-pass counting instead
    of O(256n) character-by-character scan.
    """
    if not data:
        return 0.0
    import math
    from collections import Counter
    counts = Counter(data)
    n = len(data)
    entropy = -sum(
        (count / n) * math.log2(count / n)
        for count in counts.values()
    )
    return entropy


def is_high_entropy(text: str, threshold: float = 4.2) -> bool:
    """Check if text has high entropy (potential secret)."""
    if len(text) < 20:
        return False
    return shannon_entropy(text) > threshold


# ---------------------------------------------------------------------------
# Prompt injection patterns (aligned with Hermes tirith scanner)
# ---------------------------------------------------------------------------

INJECTION_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("role_override", re.compile(
        r'(?:ignore|forget|disregard)\s+(?:all\s+)?(?:previous|above)\s+(?:instructions?|prompts?|context|directives?)',
        re.IGNORECASE
    )),
    ("system_impersonation", re.compile(
        r'(?:you are now|you are a|act as|pretend to be|you\'re now)',
        re.IGNORECASE
    )),
    ("role_reversal", re.compile(
        r'(?:system:\s*|\[system\]|\[SYSTEM\]|<system>)',
        re.IGNORECASE
    )),
    ("jailbreak_marker", re.compile(
        r'(?:DAN\s|jailbreak|developer\s*mode|god\s*mode)',
        re.IGNORECASE
    )),
    ("data_exfil", re.compile(
        r'(?:send|upload|post|curl|wget).{0,50}(?:\.ssh|\.aws|\.env|/etc/passwd|/etc/shadow)',
        re.IGNORECASE
    )),
]


# ---------------------------------------------------------------------------
# Dangerous command patterns
# ---------------------------------------------------------------------------

DANGEROUS_COMMANDS: List[Tuple[str, str, re.Pattern]] = [
    ("pipe_to_shell", "piped to shell execution", re.compile(
        r'curl\s+.{0,30}\|\s*(?:ba)?sh'
    )),
    ("eval_exec", "eval or exec usage", re.compile(
        r'(?:eval|exec)\s+[\"\']'
    )),
    ("destructive_rm", "recursive force remove", re.compile(
        r'rm\s+(?:-rf?|--recursive|--force)\s+(?:/|~|/)'
    )),
    ("chmod_dangerous", "dangerous permissions change", re.compile(
        r'chmod\s+(?:777|o\+w|a\+w)'
    )),
    ("raw_device_write", "raw device write", re.compile(
        r'>\s*/dev/sd[a-z]'
    )),
    ("curl_exfil", "data exfiltration via curl", re.compile(
        r'curl\s+.{0,40}(?:https?://).{0,40}(?:(?:\$\()|(?:`)|(?:\$\(.*\)))'
    )),
    ("wget_exfil", "data exfiltration via wget", re.compile(
        r'wget\s+.{0,40}(?:https?://).{0,40}(?:(?:\$\()|(?:`))'
    )),
    ("base64_decode_exec", "base64 decode and execute", re.compile(
        r'base64\s+(?:-d|--decode).{0,20}\|\s*(?:ba)?sh'
    )),
    ("dd_destructive", "disk destroy via dd", re.compile(
        r'dd\s+if=.{0,20}of=/dev/'
    )),
    ("fork_bomb", "fork bomb pattern", re.compile(
        r':\s*\(\s*\)\s*\{\s*:.*\|.*:.*&.*;\s*\}\s*;.*:'
    )),
]


# ---------------------------------------------------------------------------
# Environment isolation patterns
# ---------------------------------------------------------------------------

ENV_VAR_PATTERN = re.compile(
    r'\$(?:[A-Z_][A-Z0-9_]*|\{[A-Z_][A-Z0-9_]*\})'
)

SENSITIVE_PATH_PATTERNS = [
    re.compile(r'~/.ssh'),
    re.compile(r'~/.aws'),
    re.compile(r'/etc/passwd'),
    re.compile(r'/etc/shadow'),
    re.compile(r'~/.env'),
    re.compile(r'~/.hermes/\.env'),
    re.compile(r'~/.hermes/auth\.json'),
    re.compile(r'~/.config/'),
]


# ---------------------------------------------------------------------------
# Combined scan API
# ---------------------------------------------------------------------------

@dataclass
class ScanResult:
    """Result of scanning content for security issues."""
    passed: bool
    secrets: List[Dict[str, str]]   # [{pattern, match, location}]
    injections: List[Dict[str, str]]
    dangerous_commands: List[Dict[str, str]]
    high_entropy_strings: List[str]


def scan_content(content: str) -> ScanResult:
    """Run all security scans on content.

    Returns a ScanResult with any issues found. Use this before
    committing skills to the sync repo.
    """
    secrets = scan_secrets(content)
    injections = scan_injections(content)
    commands = scan_dangerous_commands(content)
    entropy_strings = scan_entropy(content)

    passed = not any([secrets, injections, commands, entropy_strings])

    return ScanResult(
        passed=passed,
        secrets=secrets,
        injections=injections,
        dangerous_commands=commands,
        high_entropy_strings=entropy_strings,
    )


def scan_secrets(content: str) -> List[Dict[str, str]]:
    """Scan for API keys, tokens, and other secrets."""
    findings = []
    for name, description, pattern in SECRET_PATTERNS:
        for match in pattern.finditer(content):
            line_num = content[:match.start()].count('\n') + 1
            findings.append({
                "pattern": name,
                "description": description,
                "match": match.group()[:12] + "...",
                "line": str(line_num),
            })
    return findings


def scan_injections(content: str) -> List[Dict[str, str]]:
    """Scan for prompt injection patterns."""
    findings = []
    for name, pattern in INJECTION_PATTERNS:
        for match in pattern.finditer(content):
            line_num = content[:match.start()].count('\n') + 1
            findings.append({
                "pattern": name,
                "match": match.group()[:80],
                "line": str(line_num),
            })
    return findings


def scan_dangerous_commands(content: str) -> List[Dict[str, str]]:
    """Scan for dangerous shell command patterns."""
    findings = []
    for name, description, pattern in DANGEROUS_COMMANDS:
        for match in pattern.finditer(content):
            line_num = content[:match.start()].count('\n') + 1
            findings.append({
                "pattern": name,
                "description": description,
                "match": match.group()[:80],
                "line": str(line_num),
            })
    return findings


def scan_entropy(content: str) -> List[str]:
    """Scan for high-entropy strings (potential secrets)."""
    # Split into tokens (words of 20+ chars)
    tokens = re.findall(r'[A-Za-z0-9+/=_-]{20,}', content)
    return [t for t in tokens if is_high_entropy(t)]


def strip_env_refs(content: str) -> str:
    """Replace environment variable references with [STRIPPED]."""
    return ENV_VAR_PATTERN.sub('[STRIPPED]', content)


def strip_sensitive_paths(content: str) -> str:
    """Replace references to sensitive file paths."""
    for pattern in SENSITIVE_PATH_PATTERNS:
        content = pattern.sub('[SENSITIVE_PATH]', content)
    return content


# ---------------------------------------------------------------------------
# Sensitive file patterns — files that MUST NOT be committed to the sync repo
# ---------------------------------------------------------------------------

BLOCKED_FILE_PATTERNS: List[str] = [
    ".env",
    "auth.json",
    "auth.yaml",
    "credentials",
    "credentials.json",
    "service-account.json",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "*.pem",
    "*.key",
    "*.pfx",
    "*.p12",
    "known_hosts",
    ".netrc",
    ".git-credentials",
    "config.yaml",  # plugin config with token
]

BLOCKED_DIR_PATTERNS: List[str] = [
    ".ssh",
    ".aws",
    ".gcloud",
    ".azure",
    ".config/gcloud",
]


def check_sensitive_files(file_paths: List[str]) -> List[str]:
    """Check file paths against blocked patterns.

    Returns deduplicated list of blocked file paths that should not be committed.
    """
    import fnmatch
    blocked: set[str] = set()
    for fp in file_paths:
        basename = Path(fp).name
        for pattern in BLOCKED_FILE_PATTERNS:
            if fnmatch.fnmatch(basename, pattern):
                blocked.add(fp)
                break
        # Also check for blocked directories in path
        for pattern in BLOCKED_DIR_PATTERNS:
            if pattern in fp:
                blocked.add(fp)
                break
    return list(blocked)


def redact_content(content: str) -> str:
    """Redact secrets and dangerous content for safe storage.

    Unlike scan_content which reports issues, this mutates the
    content to remove sensitive information before saving.
    """
    # Redact known secrets
    for name, description, pattern in SECRET_PATTERNS:
        content = pattern.sub(f'[REDACTED:{name}]', content)

    # Strip env vars
    content = strip_env_refs(content)

    # Strip sensitive paths
    content = strip_sensitive_paths(content)

    return content
