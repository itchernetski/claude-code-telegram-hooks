# Claude Code Telegram Hooks

Control Claude Code from Telegram. Get notifications, approve plans, and answer questions — all without leaving your phone.

## Features

- **Completion notifications** — get a Telegram message when Claude finishes a task, with any generated `.md` files attached
- **Interactive plan approval** — review plans in Telegram and approve, reject, or request changes via inline buttons
- **Remote question answering** — when Claude asks you a question (AskUserQuestion), answer it through Telegram buttons
- **Status line** — see context window usage %, 5-hour API limit %, and time until reset right in your terminal

Example status line:
```
skills · 12% ctx · 22% limit · 3h46m before reset
```

## Prerequisites

- **macOS** (uses Keychain for OAuth credentials in status line)
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
EOF

chmod 600 ~/.claude/.env
```

### 4. Update Claude Code settings

Merge the hooks config into your `~/.claude/settings.json`. See [settings.example.json](settings.example.json) for the full example.

The key sections to add:

```json
{
  "statusLine": {
    "type": "command",
    "command": "~/.claude/utils/statusline.sh"
  },
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [{ "type": "command", "command": "~/.claude/hooks/session-marker.sh" }]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "AskUserQuestion",
        "hooks": [{ "type": "command", "command": "python3 ~/.claude/hooks/telegram_interactive.py", "timeout": 180 }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "ExitPlanMode",
        "hooks": [{ "type": "command", "command": "python3 ~/.claude/hooks/telegram_interactive.py", "timeout": 180 }]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [{ "type": "command", "command": "~/.claude/hooks/telegram-notify.sh", "async": true }]
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
│ Claude Code  │────▶│  Hook Scripts     │────▶│ Telegram │
│              │     │                  │     │   Bot    │
│ SessionStart │────▶│ session-marker.sh│     │          │
│ AskQuestion  │────▶│ telegram_inter.. │◀───▶│ Buttons  │
│ ExitPlanMode │────▶│ telegram_inter.. │◀───▶│ Buttons  │
│ Stop         │────▶│ telegram-notify  │────▶│ Message  │
└─────────────┘     └──────────────────┘     └──────────┘
```

### Hook events

| Event | Script | What happens |
|-------|--------|-------------|
| `SessionStart` | `session-marker.sh` | Creates a timestamp marker for tracking file changes |
| `PreToolUse` → `AskUserQuestion` | `telegram_interactive.py` | Sends question + options as inline buttons, polls for answer |
| `PostToolUse` → `ExitPlanMode` | `telegram_interactive.py` | Sends plan text + Approve/Reject/Edit buttons, polls for decision |
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

### Poll timeout

Set the `POLL_TIMEOUT` environment variable to change how long the script waits for Telegram responses (default: 120 seconds).

### Status line cache

Edit `CACHE_TTL` in `statusline.sh` to change the API cache duration (default: 300 seconds / 5 minutes).

## License

MIT
