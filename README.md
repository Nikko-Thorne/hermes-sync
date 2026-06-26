# Hermes Sync

Keep your Hermes together. Skills. Memory. Config. Profiles. Synced
across every device you run Hermes on. Zero servers. Just GitHub.

---

## What it does

- **Syncs skills** — install a skill once, it's everywhere
- **Syncs memory** — your agent remembers who you are, on every device
- **Syncs config** — config.yaml stays in sync (encrypted secrets)
- **Syncs profiles** — all your profiles, available on every machine
- **Syncs cron jobs** — optional, off by default
- **Platform-aware** — macOS-only skill never lands on your Linux server
- **Security-first** — every file scanned for secrets, Ed25519-signed
  commits, age-encrypted secrets channel
- **Offline-safe** — works fine without internet, catches up when you
  reconnect
- **Zero new infrastructure** — uses a private GitHub repo. No OAuth
  app, no central service, no tokens to buy.

---

## Quick start

### Install

```bash
pip install hermes-sync
# OR: pip install git+https://github.com/Nikko-Thorne/hermes-sync.git
```

### Setup

```bash
hermes-sync setup
```

This walks you through:
1. GitHub repo URL (create a private one first)
2. GitHub token
3. What to sync (skills, memories, config, profiles, cron)

### Start syncing

```bash
hermes-sync start
```

Runs in foreground. On systemd: `systemctl --user enable --now hermes-sync`.

### Check status

```bash
hermes-sync status
```

---

## CLI Reference

```
hermes-sync start       Start sync daemon (foreground)
hermes-sync status      Show sync status and config
hermes-sync push        Manual push
hermes-sync pull        Manual pull
hermes-sync setup       Interactive config wizard
```

---

## Configuration

```yaml
# ~/.hermes/sync/config.yaml

backend: github
repo_url: https://github.com/YOU/hermes-sync-state.git
sync_interval: 60
sync_skills: true
sync_memories: true
sync_cron: false
sync_config: false       # Sync config.yaml (encrypted with age)
sync_profiles: false     # Sync ~/.hermes/profiles/
auto_resolve_conflicts: true
platforms: [linux]       # Auto-detected if empty
```

Authentication: `GH_TOKEN` or `GITHUB_TOKEN` env var, or `token:` in config.

---

## Secrets encryption

When `sync_config: true`, sensitive files (`.env`, `auth.json`,
`config.yaml`) are encrypted with [age](https://age-encryption.org)
before syncing. Each device gets its own age keypair at
`~/.hermes/sync/age.key`.

```bash
# Install age
# macOS:   brew install age
# Linux:   apt install age
# Windows: choco install age

# Keypair is auto-generated on first run at ~/.hermes/sync/age.key
# To get your public key:
age-keygen -y ~/.hermes/sync/age.key

# On another device, generate a new keypair:
age-keygen -o ~/.hermes/sync/age.key
```

Encrypted files in the sync repo look like:
```
secrets/
  env.age
  auth.age
  config.age
```

---

## Architecture

```
Device A                          GitHub                          Device B
─────────                         ──────                          ─────────
~/.hermes/skills/   ──┐
~/.hermes/memories/ ──┤                                       ┌── ~/.hermes/skills/
~/.hermes/config.yaml ─┤  push ──►  hermes-sync-state  ◄── pull ─┤ ~/.hermes/memories/
~/.hermes/profiles/  ──┤           (private repo)              └── ~/.hermes/config.yaml
~/.hermes/.env ──► encrypt ──► secrets/env.age ◄── decrypt ◄── ~/.hermes/.env
```

- **Startup pull** — latest files available immediately
- **Every 60 seconds** — periodic pull check
- **File watcher** — local changes pushed within seconds (inotify on
  Linux, polling elsewhere)
- **Ed25519 signed commits** — every push cryptographically signed
- **age encrypted secrets** — `.env` and `auth.json` never in plaintext
  on the remote

---

## What gets synced

| Category | Toggle | Location |
|----------|--------|----------|
| Skills | `sync_skills` | `~/.hermes/skills/` |
| Memory | `sync_memories` | `~/.hermes/memories/` |
| Cron | `sync_cron` | `~/.hermes/cron/` |
| Config | `sync_config` | `~/.hermes/config.yaml` (encrypted) |
| Profiles | `sync_profiles` | `~/.hermes/profiles/` |

---

## Security

| Layer | What it catches |
|-------|----------------|
| Secret scanning | API keys, tokens, JWTs, private keys |
| Command auditing | `curl \| bash`, `rm -rf /`, `chmod 777` |
| Injection detection | Prompt injection patterns |
| File blocking | `.env`, `auth.json`, `.pem`, `.key` |
| Ed25519 signing | Every commit verifiable |
| age encryption | Secrets encrypted at rest on remote |

---

## Running tests

```bash
cd hermes-sync
pip install -e ".[dev]"
pytest tests/ -v
```

---

## From plugin to standalone

Hermes Sync was originally a Hermes plugin. It's now a standalone library
+ CLI that can be integrated into Hermes core or used independently.

Key changes from v0.1.0:
- Removed plugin architecture (no more `plugin.yaml`, hooks)
- Package renamed to `hermes_sync` (importable Python package)
- Added `hermes-sync` CLI command
- Added config and profiles sync categories
- Added age-based secrets encryption
- Fixed Windows compatibility (inotify guard)
- Fixed test imports and structure

---

## License

MIT
