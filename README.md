# Claude Code Telegram Hooks

Control Claude Code from Telegram. Get notifications when Claude needs your attention — plans to approve and task completions.

## Features

- **IDE-first interaction** — plans show in IDE immediately; if you don't respond within a configurable delay, a notification is sent to Telegram
- **Completion notifications** — get a Telegram message when Claude finishes a task, with any generated `.md` files attached
- **Status line** — see context window usage %, 5-hour API limit %, and time until reset right in your terminal

Example status line:
```
skills · 12% ctx · 22% limit · 3h46m before reset
```

## Prerequisites

- **macOS** (uses `os.fork()` for background notifications and Keychain for OAuth in status line)
- **Python 3** (pre-installed on macOS)
- **jq** — `brew install jq`
- **Telegram bot** — create one via [@BotFather](https://t.me/BotFather)
- **Claude Code** with hooks support

## Installation

### 1. Create your Telegram bot

1. Open [@BotFather](https://t.me/BotFather) in Telegram
2. Send `/newbot`, follow the prompts
3. Copy the bot token
4. Send any message to your new bot
5. Get your chat ID:
   ```bash
   curl -s "https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates" | jq '.result[-1].message.chat.id'
   ```

### 2. Copy scripts

```bash
# Clone the repo
git clone https://github.com/yourusername/claude-code-telegram-hooks.git
cd claude-code-telegram-hooks

# Copy hooks
cp hooks/* ~/.claude/hooks/
chmod +x ~/.claude/hooks/session-marker.sh ~/.claude/hooks/telegram-notify.sh ~/.claude/hooks/telegram_interactive.py

# Copy status line
mkdir -p ~/.claude/utils
cp utils/statusline.sh ~/.claude/utils/
chmod +x ~/.claude/utils/statusline.sh
```

### 3. Configure credentials

```bash
# Create .env file (never commit this!)
cat > ~/.claude/.env << 'EOF'
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
NOTIFY_DELAY=120
EOF

chmod 600 ~/.claude/.env
```

### 4. Update Claude Code settings

Merge the hooks config into your `~/.claude/settings.json`. See [settings.example.json](settings.example.json) for the full example.

The key sections to add:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "ExitPlanMode",
        "hooks": [{ "type": "command", "command": "python3 ~/.claude/hooks/telegram_interactive.py" }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "ExitPlanMode",
        "hooks": [{ "type": "command", "command": "python3 ~/.claude/hooks/telegram_interactive.py" }]
      }
    ]
  }
}
```

### 5. Restart Claude Code

The hooks will be picked up on the next session.

## How It Works

```
┌─────────────┐     ┌──────────────────┐     ┌──────────┐
│ Claude Code  │────▶│  Hook Scripts     │     │ Telegram │
│              │     │                  │     │   Bot    │
│ SessionStart │────▶│ session-marker.sh│     │          │
│ ExitPlanMode │────▶│ PreToolUse: fork │     │          │
│              │     │   bg notifier    │     │          │
│ (user answers│────▶│ PostToolUse:     │     │          │
│  in IDE)     │     │   cancel signal  │     │          │
│              │     │                  │     │          │
│ (user AFK)   │     │ bg process wakes │────▶│ Notify   │
│              │     │   after delay    │     │          │
│ Stop         │────▶│ telegram-notify  │────▶│ Message  │
└─────────────┘     └──────────────────┘     └──────────┘
```

### Flow

1. Claude calls `ExitPlanMode`
2. **PreToolUse** hook fires → forks a background process with a timer → returns immediately
3. IDE shows the plan to the user (no delay)
4. **If user responds in IDE** → PostToolUse fires → writes cancel signal → background process is killed
5. **If user is AFK** → background process wakes up after `NOTIFY_DELAY` seconds → sends read-only notification to Telegram

### Hook events

| Event | Script | What happens |
|-------|--------|-------------|
| `SessionStart` | `session-marker.sh` | Creates a timestamp marker for tracking file changes |
| `PreToolUse` → `ExitPlanMode` | `telegram_interactive.py` | Forks background notifier, returns immediately for IDE |
| `PostToolUse` → `ExitPlanMode` | `telegram_interactive.py` | Cancels delayed Telegram notification |
| `Stop` | `telegram-notify.sh` | Sends completion notification + any new `.md` files as documents |

### Status line

`statusline.sh` runs as a status line command, showing:
- Current directory name (cyan)
- Context window usage % (green/yellow/red)
- 5-hour API usage limit % (green/yellow/red)
- Time until limit reset

Uses OAuth credentials from macOS Keychain (no tokens in files). Results are cached for 5 minutes.

## Security

- **No secrets in scripts** — all credentials are loaded from `~/.claude/.env`
- **`.env` is gitignored** — never committed to the repo
- **Status line uses Keychain** — OAuth tokens are accessed securely via `security` command
- **Set proper permissions**: `chmod 600 ~/.claude/.env`

## Customization

### Notification delay

Set the `NOTIFY_DELAY` environment variable (in seconds) to control how long to wait before sending a Telegram notification. Default: 120 seconds (2 minutes).

```bash
# In ~/.claude/.env
NOTIFY_DELAY=60  # notify after 1 minute
```

### Status line cache

Edit `CACHE_TTL` in `statusline.sh` to change the API cache duration (default: 300 seconds / 5 minutes).

## License

MIT
