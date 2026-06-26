# Hermes Sync — Installation Guide

Sync your Hermes skills, memory, config, and profiles across all your devices.
Takes 2 minutes. Zero servers. Just GitHub.

---

## What you need

- A GitHub account
- A [GitHub Personal Access Token](https://github.com/settings/tokens)
  with `repo` scope
- Python 3.11+

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
# 1. Install hermes-sync
pip install hermes-sync
# OR: pip install git+https://github.com/Nikko-Thorne/hermes-sync.git

# 2. Run the setup wizard
hermes-sync setup

# 3. Follow the prompts to enter:
#    - GitHub repo URL (https://github.com/YOU/hermes-sync-state.git)
#    - GitHub token (or set GH_TOKEN env var)
#    - What to sync (skills, memories, cron, config, profiles)

# 4. Start syncing
hermes-sync start
```

---

## Verify it's working

```bash
# Check sync status
hermes-sync status

# Should show:
#   Enabled:  True
#   Backend:  github
#   Repo:     https://github.com/YOU/hermes-sync-state.git
#   ...

# Check the sync repo
ls ~/.hermes/sync/repo/
# Should show: skills/ memories/ (and other enabled categories)
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
~/.hermes/sync/repo/skills/
    ↓ (auto-commit + push)
                          →     hermes-sync-state (private)
                                                        ↓ (auto-pull every 60s)
                                                   ~/.hermes/sync/repo/skills/
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

## Running as a service

### systemd (Linux)

```bash
# Create service file
cat > ~/.config/systemd/user/hermes-sync.service << 'EOF'
[Unit]
Description=Hermes Sync
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/env hermes-sync start
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF

# Enable and start
systemctl --user daemon-reload
systemctl --user enable --now hermes-sync

# Check status
systemctl --user status hermes-sync
```

### launchd (macOS)

```bash
# Create plist file
cat > ~/Library/LaunchAgents/com.hermes.sync.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.hermes.sync</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/hermes-sync</string>
        <string>start</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
EOF

# Load and start
launchctl load ~/Library/LaunchAgents/com.hermes.sync.plist

# Check status
launchctl list | grep hermes
```

---

## Troubleshooting

**"Not configured" error**
```bash
# Run setup first
hermes-sync setup
```

**"Clone failed" in logs**

Check your token works:
```bash
export GH_TOKEN=ghp_your_token_here
git clone https://github.com/YOU/hermes-sync-state.git /tmp/test-clone
```

If that fails, regenerate your token with `repo` scope.

**Nothing syncing?**

Force a manual sync:
```bash
hermes-sync push
hermes-sync pull
```

Check logs:
```bash
hermes-sync start
# Watch for errors in output
```

**Merge conflicts?**

Hermes Sync auto-resolves conflicts by preferring local changes ("ours" strategy).
The sync repo is just a cache — your local `~/.hermes/` is always the source of truth.

---

## Uninstall

```bash
# Stop the daemon
# systemd: systemctl --user stop hermes-sync
# launchd: launchctl unload ~/Library/LaunchAgents/com.hermes.sync.plist

# Remove hermes-sync
pip uninstall hermes-sync

# Optionally remove sync data
rm -rf ~/.hermes/sync/
```

---

## Links

- **GitHub:** https://github.com/Nikko-Thorne/hermes-sync
- **Issues:** https://github.com/Nikko-Thorne/hermes-sync/issues
