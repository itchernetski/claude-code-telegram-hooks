#!/usr/bin/env python3
"""
Claude Code hook: Telegram interactive control.
Handles ExitPlanMode (approve/reject plans) and AskUserQuestion (answer via buttons).
"""

import json
import os
import sys
import time
import glob
import urllib.request
import urllib.parse
import urllib.error

# --- Config ---
ENV_FILE = os.path.expanduser("~/.claude/.env")
POLL_INTERVAL = 3  # seconds
POLL_TIMEOUT = int(os.environ.get("POLL_TIMEOUT", "120"))  # seconds
MAX_MSG_LEN = 4096  # Telegram message limit


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
    # Split long text into chunks
    chunks = []
    while len(text) > MAX_MSG_LEN:
        # Find a good split point
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
        # Add buttons only to the last chunk
        if reply_markup and i == len(chunks) - 1:
            data["reply_markup"] = reply_markup
        result = tg_request(token, "sendMessage", data)
        if result and result.get("ok"):
            messages.append(result["result"])
    return messages


def poll_callback(token, chat_id, callback_prefix, timeout):
    """Poll for a callback_query matching our prefix. Returns callback data or None."""
    # First, flush old updates
    tg_request(token, "getUpdates", {"offset": -1, "limit": 1})
    time.sleep(0.5)

    # Get the latest update_id to use as offset
    flush = tg_request(token, "getUpdates", {"limit": 1, "timeout": 0})
    offset = 0
    if flush and flush.get("ok") and flush["result"]:
        offset = flush["result"][-1]["update_id"] + 1

    start = time.time()
    while time.time() - start < timeout:
        result = tg_request(token, "getUpdates", {
            "offset": offset,
            "limit": 10,
            "timeout": POLL_INTERVAL,
        })
        if not result or not result.get("ok"):
            time.sleep(POLL_INTERVAL)
            continue

        for update in result.get("result", []):
            offset = update["update_id"] + 1

            # Check for callback_query
            cb = update.get("callback_query")
            if cb and cb.get("data", "").startswith(callback_prefix):
                # Answer the callback to remove the loading indicator
                tg_request(token, "answerCallbackQuery", {
                    "callback_query_id": cb["id"],
                    "text": "Received!",
                })
                return cb["data"][len(callback_prefix):]

            # Check for text message (for "Edit" flow)
            msg = update.get("message")
            if msg and str(msg.get("chat", {}).get("id")) == str(chat_id):
                text = msg.get("text", "")
                if text.startswith("/"):
                    continue  # Skip commands
                return f"text:{text}"

    return None


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


def handle_exit_plan_mode(token, chat_id, hook_input):
    """Handle ExitPlanMode (PostToolUse): send plan to Telegram, get feedback via additionalContext."""
    cwd = hook_input.get("cwd", "")

    # Try to get plan from tool_input first (ExitPlanMode may include plan text)
    tool_input = hook_input.get("tool_input", {})
    plan_text = tool_input.get("plan", "")

    # Fallback: read plan file
    if not plan_text:
        plan_file = find_plan_file(cwd)
        if not plan_file:
            sys.exit(0)
        with open(plan_file) as f:
            plan_text = f.read()

    # Escape markdown special chars for Telegram
    safe_text = plan_text.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")
    # Truncate if too long
    if len(safe_text) > MAX_MSG_LEN * 3:
        safe_text = safe_text[:MAX_MSG_LEN * 3] + "\n\n... (truncated)"

    # Send plan to Telegram
    prefix = f"plan_{int(time.time())}_"
    header = "📋 *Claude Code Plan*\n\n"
    send_message(token, chat_id, header + safe_text)

    # Send action buttons
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Approve", "callback_data": f"{prefix}approve"},
            {"text": "❌ Reject", "callback_data": f"{prefix}reject"},
            {"text": "✏️ Edit", "callback_data": f"{prefix}edit"},
        ]]
    }
    send_message(token, chat_id, "Что сделать с планом?", reply_markup=keyboard)

    # Poll for response
    response = poll_callback(token, chat_id, prefix, POLL_TIMEOUT)

    if response is None:
        send_message(token, chat_id, "⏰ Нет ответа, ожидание в IDE.")
        sys.exit(0)

    if response == "approve":
        send_message(token, chat_id, "✅ План одобрен!")
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": "The user approved the plan via Telegram. Proceed with implementation.",
            }
        }
        print(json.dumps(output))
        sys.exit(0)

    if response == "reject":
        send_message(token, chat_id, "❌ План отклонён.")
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": "The user REJECTED the plan via Telegram. Do NOT proceed with implementation. Ask the user what they'd like to change.",
            }
        }
        print(json.dumps(output))
        sys.exit(0)

    if response == "edit":
        send_message(token, chat_id, "✏️ Напишите ваш фидбек:")
        feedback = poll_callback(token, chat_id, "", POLL_TIMEOUT)
        feedback_text = ""
        if feedback and feedback.startswith("text:"):
            feedback_text = feedback[5:]
        elif feedback:
            feedback_text = feedback

        send_message(token, chat_id, f"📝 Фидбек получен: {feedback_text}")
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": f"The user reviewed the plan via Telegram and requested changes. Do NOT proceed as-is. Their feedback: {feedback_text}",
            }
        }
        print(json.dumps(output))
        sys.exit(0)


def handle_ask_user_question(token, chat_id, hook_input):
    """Handle AskUserQuestion: send options as inline keyboard."""
    tool_input = hook_input.get("tool_input", {})
    questions = tool_input.get("questions", [])

    if not questions:
        sys.exit(0)

    answers = {}
    prefix = f"q_{int(time.time())}_"

    for q_idx, q in enumerate(questions):
        question_text = q.get("question", "")
        header_text = q.get("header", "")
        options = q.get("options", [])
        multi_select = q.get("multiSelect", False)

        # Build message
        msg = f"❓ *{header_text}*\n{question_text}"
        if multi_select:
            msg += "\n_(можно выбрать несколько)_"

        # Build inline keyboard (1 button per row for readability)
        q_prefix = f"{prefix}{q_idx}_"
        keyboard_rows = []
        for opt_idx, opt in enumerate(options):
            label = opt.get("label", f"Option {opt_idx}")
            desc = opt.get("description", "")
            btn_text = label
            if desc:
                btn_text = f"{label} — {desc}"
            # Truncate button text to 64 chars (Telegram limit)
            if len(btn_text) > 64:
                btn_text = btn_text[:61] + "..."
            keyboard_rows.append([{
                "text": btn_text,
                "callback_data": f"{q_prefix}{opt_idx}",
            }])

        keyboard = {"inline_keyboard": keyboard_rows}
        send_message(token, chat_id, msg, reply_markup=keyboard)

        # Poll for answer
        response = poll_callback(token, chat_id, q_prefix, POLL_TIMEOUT)

        if response is None:
            send_message(token, chat_id, "⏰ No response, falling through to IDE.")
            sys.exit(0)

        # Map response back to option label
        try:
            opt_idx = int(response)
            selected = options[opt_idx].get("label", f"Option {opt_idx}")
        except (ValueError, IndexError):
            selected = response

        answers[question_text] = selected
        send_message(token, chat_id, f"✅ Selected: {selected}")

    # Build context for Claude
    answer_lines = []
    for q_text, answer in answers.items():
        answer_lines.append(f'- "{q_text}" → "{answer}"')
    context = "User answered questions via Telegram:\n" + "\n".join(answer_lines)

    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "User answered via Telegram",
            "additionalContext": context,
        }
    }
    print(json.dumps(output))
    sys.exit(0)


def main():
    env = load_env()
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat_id = env.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        sys.exit(0)

    hook_input = json.loads(sys.stdin.read())
    tool_name = hook_input.get("tool_name", "")

    if tool_name == "ExitPlanMode":
        handle_exit_plan_mode(token, chat_id, hook_input)
    elif tool_name == "AskUserQuestion":
        handle_ask_user_question(token, chat_id, hook_input)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
