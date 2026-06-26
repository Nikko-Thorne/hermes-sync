# Hermes Sync

<p align="center">
  <b>Keep your Hermes together.</b><br>
  Skills. Memory. Cron. Synced across every device you run Hermes on.<br>
  <i>Two minutes to set up. Zero servers. Just GitHub.</i>
</p>

---

You know that thing where your agent learns something useful on your
laptop, but your server has no idea? Or you install a skill on one
machine and have to remember to copy it to the other three?

This fixes that.

---

## What it does

- **Syncs skills** — install a skill once, it's everywhere
- **Syncs memory** — your agent remembers who you are, on every device
- **Syncs cron jobs** — optional, off by default (enabling is one line)
- **Platform-aware** — a macOS-only skill never lands on your Linux server
- **Security-first** — every file scanned for secrets, suspicious
  commands, and prompt injections before it leaves your machine
- **Offline-safe** — works fine without internet, catches up when you
  reconnect
- **Zero new infrastructure** — uses a private GitHub repo you already
  have. No OAuth app, no central service, no tokens to buy.

---

## Quick start

```bash
# 1. Install
git clone https://github.com/Nikko-Thorne/hermes-sync \
  ~/.hermes/plugins/hermes-sync/

# 2. Create a private GitHub repo for sync state
#    Go to https://github.com/new — call it "hermes-sync-state"
#    Empty, no README.

# 3. Configure
cat > ~/.hermes/plugins/hermes-sync/config.yaml << EOF
backend: github
repo_url: https://github.com/YOU/hermes-sync-state.git
sync_interval: 60
sync_skills: true
sync_memories: true
sync_cron: false
EOF

# 4. Set your GitHub token
export GH_TOKEN=ghp_your_token_here

# 5. Restart Hermes
#    Plugin auto-detected — starts syncing immediately.
```

---

## What gets synced

```
~/.hermes/skills/     ←→  sync-repo/skills/     ←→  ~/.hermes/skills/
~/.hermes/memories/   ←→  sync-repo/memories/   ←→  ~/.hermes/memories/
~/.hermes/cron/       ←→  sync-repo/cron/       ←→  ~/.hermes/cron/
      Device A               GitHub                    Device B
```

- **Startup pull** — latest files from other devices available
  immediately
- **Every 60 seconds** — checks for new changes from other devices
- **File watcher** — local changes detected and pushed within seconds
  (inotify on Linux, polling elsewhere)
- **Ed25519 signed commits** — every push is cryptographically signed,
  verifiable authorship without GPG

---

## Security

Every file is scanned before it leaves your machine.

| Layer | Catches |
|-------|---------|
| Secret scanning | API keys, tokens, JWTs, private keys |
| Command auditing | `curl \| bash`, `rm -rf /`, `chmod 777` |
| Injection detection | Prompt injection patterns, role-reversal attacks |
| File blocking | `.env`, `auth.json`, `.pem`, `.key` — never committed |

If a scan fails, the sync aborts — nothing sketchy leaves your machine.

---

## Configuration reference

```yaml
# ~/.hermes/plugins/hermes-sync/config.yaml

backend: github                    # Only backend right now
repo_url: ""                       # Your private sync repo URL (required)
sync_interval: 60                  # Seconds between pull checks
sync_skills: true                  # Sync ~/.hermes/skills/
sync_memories: true                # Sync ~/.hermes/memories/
sync_cron: false                   # Sync ~/.hermes/cron/
auto_resolve_conflicts: true       # Auto-resolve merge conflicts
platforms: []                      # Auto-detected — override if needed
```

Authentication: `GH_TOKEN` or `GITHUB_TOKEN` env var, or `token:` in
config. Token resolution order: env var → config.yaml → `gh auth token`
→ `git credential fill`.

---

## Verify it's working

```bash
# Plugin status
hermes plugins list | grep sync

# Should show: hermes-sync | enabled | 0.1.0

# Check the sync repo
ls ~/.hermes/sync-repo/
# Should show: skills/ memories/ .git/
```

---

## Troubleshooting

**"not enabled"**
```bash
hermes config set plugins.enabled '[hermes-sync]'
# Then restart Hermes.
```

**Clone failed**
```bash
# Your token might be wrong. Test it:
GH_TOKEN=your_token git clone https://github.com/YOU/hermes-sync-state.git /tmp/test-clone
```

**Nothing syncing?**
```bash
# Force a manual sync to see what's happening:
cd ~/.hermes/plugins/hermes-sync
python3 -c "
import sys; sys.path.insert(0, '.')
from sync import HermesSync
s = HermesSync()
s.start()
p, pm, push, pushm = s.sync_now()
print(f'Pull: {pm}\nPush: {pushm}')
s.stop()
"
```

---

## Running tests

```bash
cd ~/.hermes/plugins/hermes-sync
python3 -m pytest tests/ -v
```

90 tests. All green.

---

## License

MIT
