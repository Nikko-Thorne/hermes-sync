# Hermes Sync — Installation Guide

Sync your Hermes skills, memory, and cron across all your devices.
Takes 2 minutes. Zero servers. Just GitHub.

---

## What you need

- A GitHub account
- A [GitHub Personal Access Token](https://github.com/settings/tokens)
  with `repo` scope
- Hermes installed on each device

---

## One-time setup (first device only)

### 1. Create your sync repo

Go to https://github.com/new and create a **private** repo called
`hermes-sync-state`. Empty — no README, no .gitignore.

### 2. Get your GitHub token

Go to https://github.com/settings/tokens → Generate new token (classic)
→ check `repo` scope. Copy the token — it starts with `ghp_`.

---

## Install on EVERY device

```bash
# 1. Install the plugin
git clone https://github.com/Nikko-Thorne/hermes-sync \
  ~/.hermes/plugins/hermes-sync/

# 2. Create config
cat > ~/.hermes/plugins/hermes-sync/config.yaml << 'EOF'
backend: github
repo_url: https://github.com/YOU/hermes-sync-state.git
sync_interval: 60
sync_skills: true
sync_memories: true
sync_cron: false
token: YOUR_GITHUB_TOKEN_HERE
EOF

# 3. Replace YOUR_GITHUB_TOKEN_HERE with your actual token
#    OR set it as an env var (safer):
#    export GH_TOKEN=***

# 4. Enable the plugin in Hermes
hermes config set plugins.enabled '[hermes-sync]'

# 5. Restart Hermes — plugin auto-starts on next session
```

---

## Verify it's working

```bash
# Check plugin status
hermes plugins list | grep sync

# Should show: hermes-sync | enabled | 0.1.0

# Check sync repo
ls ~/.hermes/sync-repo/
# Should show: skills/ memories/
```

---

## How it works

```
Device A                          GitHub                        Device B
─────────                         ──────                        ─────────
You create a skill
    ↓
~/.hermes/skills/
    ↓ (watcher detects change)
sync-repo/skills/
    ↓ (auto-commit + push)
                          →     hermes-sync-state (private)
                                                        ↓ (auto-pull every 60s)
                                                   sync-repo/skills/
                                                        ↓ (copied to ~/.hermes/)
                                                   ~/.hermes/skills/
                                                        ↓
                                                   Skill available on Device B
```

- **Startup pull** — latest skills from other devices available
  immediately
- **Every 60 seconds** — checks for changes from other devices
- **Local changes detected** — auto-committed and pushed within seconds
- **Offline-safe** — works without internet, catches up on reconnect
- **Platform scoped** — Linux skills stay on Linux, macOS skills stay
  on macOS

---

## Troubleshooting

**Plugin shows "not enabled"**
```bash
hermes config set plugins.enabled '[hermes-sync]'
```
Then restart Hermes.

**"Clone failed" in logs**
Check your token works:
```bash
GH_TOKEN=*** git clone https://github.com/YOU/hermes-sync-state.git /tmp/test-clone
```

**Nothing syncing?**
Force a manual sync:
```bash
cd ~/.hermes/plugins/hermes-sync
python3 -c "
import sys; sys.path.insert(0, '.')
from sync import HermesSync
s = HermesSync()
s.start()
p_ok, p_msg, push_ok, push_msg = s.sync_now()
print(f'Pull: {p_msg}')
print(f'Push: {push_msg}')
s.stop()
"
```

---

## Repos

- **Plugin:** https://github.com/Nikko-Thorne/hermes-sync
- **Sync state:** your private `hermes-sync-state` repo
