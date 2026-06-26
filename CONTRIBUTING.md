# Contributing to Hermes Sync

Thank you for considering contributing to Hermes Sync! This document provides guidelines and instructions for contributing.

---

## Development Setup

### Prerequisites

- Python 3.11+
- Git
- age CLI (optional, for encryption tests)

### Clone and Install

```bash
# Clone the repo
git clone https://github.com/Nikko-Thorne/hermes-sync.git
cd hermes-sync

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

---

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_security.py -v

# Run with coverage
pytest tests/ --cov=hermes_sync --cov-report=html
```

### Test Requirements

- Tests should be self-contained and use `tmp_path` fixtures
- Use `monkeypatch` to avoid modifying global state
- Security tests should include both positive (catches threats) and negative (no false positives) cases
- Integration tests should use local bare git repos, not real GitHub

---

## Code Style

### General Guidelines

- Follow PEP 8
- Use type hints for function signatures
- Maximum line length: 100 characters (soft limit)
- Use `from __future__ import annotations` for forward references

### Naming Conventions

- Functions: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private methods: `_leading_underscore`

### Docstrings

Use Google-style docstrings:

```python
def my_function(arg1: str, arg2: int) -> bool:
    """Short description of the function.

    Longer description if needed, explaining behavior,
    edge cases, and important notes.

    Args:
        arg1: Description of first argument.
        arg2: Description of second argument.

    Returns:
        Description of return value.

    Raises:
        ExceptionType: When this exception is raised.
    """
    pass
```

---

## Making Changes

### Before You Start

1. Check existing issues to avoid duplicate work
2. For major changes, open an issue first to discuss
3. Create a feature branch: `git checkout -b feature/your-feature-name`

### Commit Messages

Use clear, descriptive commit messages:

```
type: brief description (50 chars or less)

More detailed explanation if needed (wrap at 72 chars).
Explain what and why, not how.

Fixes #123
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `chore`

Examples:
- `feat: add age-pubkey CLI command`
- `fix: handle SSH URLs in github backend`
- `docs: update INSTALL.md for standalone CLI`
- `test: add coverage for entropy detection`

---

## Pull Request Process

1. **Update tests**: Add or update tests for your changes
2. **Run tests**: Ensure all tests pass locally
3. **Update docs**: Update README.md, INSTALL.md, or docstrings if needed
4. **Clean commits**: Squash fixup commits before submitting
5. **PR description**: Clearly describe what your PR does and why

### PR Checklist

- [ ] Tests added/updated and passing
- [ ] Documentation updated if behavior changed
- [ ] No hard-coded secrets or tokens
- [ ] Code follows style guidelines
- [ ] Commit messages are clear

---

## Security Considerations

### What to Check

When adding new code that handles:
- **File I/O**: Use `check_sensitive_files()` before syncing
- **User content**: Use `scan_content()` to detect secrets/injections
- **Credentials**: Never log or print tokens/keys
- **File permissions**: Use `0o600` for sensitive files

### Security Scanning

All contributed code will be scanned for:
- Hardcoded secrets (API keys, tokens)
- Dangerous command patterns
- Prompt injection vectors
- Entropy analysis for potential secrets

---

## Adding New Features

### New Security Patterns

When adding detection patterns to `security/patterns.py`:

1. Add the pattern to the appropriate list (`SECRET_PATTERNS`, `INJECTION_PATTERNS`, etc.)
2. Include a descriptive name and docstring
3. Add positive test (detects the threat)
4. Add negative test (no false positive on legitimate code)

Example:
```python
# In patterns.py
("new_secret_type", "Description", re.compile(r'pattern')),

# In test_security.py
def test_detect_new_secret_type():
    findings = scan_secrets("example with secret")
    assert len(findings) > 0

def test_no_false_positive_new_secret():
    findings = scan_secrets("legitimate code that looks similar")
    assert len(findings) == 0
```

### New Backends

To add a backend beyond GitHub:

1. Create `hermes_sync/backends/your_backend.py`
2. Implement same interface as `GitBackend`: `clone_if_needed()`, `pull()`, `push()`, `has_changes()`
3. Add backend name to valid options in `config.py`
4. Add tests in `tests/test_your_backend.py`
5. Update documentation

---

## Reporting Issues

### Bug Reports

Include:
- Hermes Sync version (`hermes-sync status`)
- Python version
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Relevant logs (redact any tokens!)

### Feature Requests

Include:
- Clear description of the feature
- Use case / motivation
- Example of how it would work
- Any security implications

---

## Release Process

(For maintainers)

1. Update version in `pyproject.toml` and `hermes_sync/__init__.py`
2. Update README.md and CHANGELOG.md
3. Create release tag: `git tag -a v0.X.0 -m "Release v0.X.0"`
4. Push tag: `git push origin v0.X.0`
5. Build and publish to PyPI:
   ```bash
   python -m build
   python -m twine upload dist/*
   ```

---

## Questions?

- Open an issue for questions
- Check existing issues and PRs first
- Be respectful and constructive

---

## License

By contributing to Hermes Sync, you agree that your contributions will be licensed under the MIT License.
