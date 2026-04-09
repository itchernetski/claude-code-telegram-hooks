#!/usr/bin/env python3
"""
Claude Code hook: Telegram delayed notifications.
IDE shows plans/questions immediately. If user doesn't respond within NOTIFY_DELAY,
a read-only notification is sent to Telegram.
"""

import json
import os
import signal
import sys
import glob
import urllib.request
import urllib.parse
import urllib.error

# --- Config ---
ENV_FILE = os.path.expanduser("~/.claude/.env")
NOTIFY_DELAY = int(os.environ.get("NOTIFY_DELAY", "120"))  # seconds before Telegram notification
MAX_MSG_LEN = 4096  # Telegram message limit
CANCEL_DIR = "/tmp"


def load_env():
    """Load bot token and chat id from .env file."""
    env = {}
    if not os.path.exists(ENV_FILE):
        return env
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, val = line.split("=", 1)
                env[key.strip()] = val.strip()
    return env


def tg_request(token, method, data=None):
    """Make a Telegram Bot API request."""
    url = f"https://api.telegram.org/bot{token}/{method}"
    if data:
        payload = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    else:
        req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def send_message(token, chat_id, text, reply_markup=None):
    """Send a message to Telegram, splitting if needed."""
    messages = []
    chunks = []
    while len(text) > MAX_MSG_LEN:
        split_at = text.rfind("\n", 0, MAX_MSG_LEN)
        if split_at == -1:
            split_at = MAX_MSG_LEN
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    chunks.append(text)

    for i, chunk in enumerate(chunks):
        data = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "Markdown",
        }
        if reply_markup and i == len(chunks) - 1:
            data["reply_markup"] = reply_markup
        result = tg_request(token, "sendMessage", data)
        if result and result.get("ok"):
            messages.append(result["result"])
    return messages


def find_plan_file(cwd):
    """Find the most recently modified plan file."""
    plan_dirs = [
        os.path.expanduser("~/.claude/plans/"),
    ]
    if cwd:
        plan_dirs.append(os.path.join(cwd, ".claude/plans/"))

    candidates = []
    for d in plan_dirs:
        candidates.extend(glob.glob(os.path.join(d, "*.md")))

    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


def cancel_signal_path(tool_name, session_id):
    """Get the path for the cancel signal file."""
    safe_session = session_id.replace("/", "_") if session_id else "default"
    return os.path.join(CANCEL_DIR, f".claude_tg_{tool_name}_{safe_session}")


def pid_file_path(tool_name, session_id):
    """Get the path for storing the background process PID."""
    safe_session = session_id.replace("/", "_") if session_id else "default"
    return os.path.join(CANCEL_DIR, f".claude_tg_{tool_name}_{safe_session}.pid")


def handle_exit_plan_mode_pre(token, chat_id, hook_input):
    """PreToolUse: fork background notifier, return immediately for IDE."""
    cwd = hook_input.get("cwd", "")
    session_id = hook_input.get("session_id", "default")

    # Read plan text
    tool_input = hook_input.get("tool_input", {})
    plan_text = tool_input.get("plan", "")
    if not plan_text:
        plan_file = find_plan_file(cwd)
        if not plan_file:
            sys.exit(0)
        with open(plan_file) as f:
            plan_text = f.read()

    # Clean up any previous cancel signal
    sig_path = cancel_signal_path("plan", session_id)
    if os.path.exists(sig_path):
        os.remove(sig_path)

    # Fork background process
    pid = os.fork()
    if pid > 0:
        # Parent: save child PID and return immediately
        pid_path = pid_file_path("plan", session_id)
        with open(pid_path, "w") as f:
            f.write(str(pid))
        sys.exit(0)

    # Child: detach and become background notifier
    os.setsid()
    try:
        _background_notify_plan(token, chat_id, plan_text, sig_path)
    except Exception:
        pass
    os._exit(0)


def _background_notify_plan(token, chat_id, plan_text, sig_path):
    """Background process: sleep, then send plan notification if not cancelled."""
    import time
    time.sleep(NOTIFY_DELAY)

    # Check cancel signal
    if os.path.exists(sig_path):
        os.remove(sig_path)
        return

    # Escape markdown special chars for Telegram
    safe_text = plan_text.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")
    if len(safe_text) > MAX_MSG_LEN * 3:
        safe_text = safe_text[:MAX_MSG_LEN * 3] + "\n\n... (truncated)"

    header = "📋 *Claude Code ждёт одобрения плана*\n\n"
    send_message(token, chat_id, header + safe_text)


def handle_post_tool(hook_input):
    """PostToolUse: write cancel signal to prevent delayed Telegram notification."""
    tool_name = hook_input.get("tool_name", "")
    session_id = hook_input.get("session_id", "default")

    if tool_name == "ExitPlanMode":
        key = "plan"
    else:
        sys.exit(0)

    # Write cancel signal
    sig_path = cancel_signal_path(key, session_id)
    with open(sig_path, "w") as f:
        f.write("cancelled")

    # Kill background process if still running
    pid_path = pid_file_path(key, session_id)
    if os.path.exists(pid_path):
        try:
            with open(pid_path) as f:
                pid = int(f.read().strip())
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, ValueError, OSError):
            pass
        finally:
            try:
                os.remove(pid_path)
            except OSError:
                pass

    sys.exit(0)


def main():
    env = load_env()
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat_id = env.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        sys.exit(0)

    hook_input = json.loads(sys.stdin.read())
    tool_name = hook_input.get("tool_name", "")
    hook_event = hook_input.get("hook_event_name", "")

    # PostToolUse: cancel delayed notifications
    if hook_event == "PostToolUse":
        handle_post_tool(hook_input)
        return

    # PreToolUse: fork background notifier, return immediately
    if tool_name == "ExitPlanMode":
        handle_exit_plan_mode_pre(token, chat_id, hook_input)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
