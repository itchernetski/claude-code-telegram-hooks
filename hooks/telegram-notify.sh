#!/bin/bash
# Telegram notification hook for Claude Code
# Fires on Stop event — notifies when Claude finishes responding
# If .md files were created/modified in session, sends them as documents

set -euo pipefail

# Load credentials
ENV_FILE="$HOME/.claude/.env"
if [ ! -f "$ENV_FILE" ]; then
  exit 0
fi
source "$ENV_FILE"

if [ -z "${TELEGRAM_BOT_TOKEN:-}" ] || [ -z "${TELEGRAM_CHAT_ID:-}" ]; then
  exit 0
fi

API="https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}"

input=$(cat)
cwd=$(echo "$input" | jq -r '.cwd // empty')
session_id=$(echo "$input" | jq -r '.session_id // "unknown"')

dir_name=$(basename "${cwd:-unknown}")

# Extract task summary from the transcript (last user message or plan title)
task_summary=""
transcript_path=$(echo "$input" | jq -r '.transcript_path // empty')
if [ -n "$transcript_path" ] && [ -f "$transcript_path" ]; then
  # Get the first user message as task description
  task_summary=$(head -20 "$transcript_path" 2>/dev/null | jq -r 'select(.role == "user") | .content // empty' 2>/dev/null | head -1 | cut -c1-200)
fi

# Fallback: check for recent plan file
if [ -z "$task_summary" ]; then
  plan_file=$(ls -t "$HOME/.claude/plans/"*.md 2>/dev/null | head -1)
  if [ -n "$plan_file" ]; then
    task_summary=$(head -1 "$plan_file" | sed 's/^#* *//')
  fi
fi

# Check for .md files modified in the last 5 minutes in the working directory
md_files=()
if [ -n "$cwd" ] && [ -d "$cwd" ]; then
  while IFS= read -r -d '' file; do
    md_files+=("$file")
  done < <(find "$cwd" -maxdepth 2 -name "*.md" -newer /tmp/.claude_session_start_${session_id} -type f -print0 2>/dev/null || true)
fi

# Send notification
message="✅ Claude Code finished in *${dir_name}*"
if [ -n "$task_summary" ]; then
  # Escape markdown special chars in task summary
  safe_summary=$(echo "$task_summary" | sed 's/[_*\[`]/\\&/g')
  message="${message}"$'\n'"📌 ${safe_summary}"
fi
if [ ${#md_files[@]} -gt 0 ]; then
  message="${message}"$'\n'"📎 MD files: ${#md_files[@]}"
fi

curl -s -X POST "${API}/sendMessage" \
  -d chat_id="${TELEGRAM_CHAT_ID}" \
  -d text="${message}" \
  -d parse_mode="Markdown" > /dev/null 2>&1

# Send each .md file as a document
for file in "${md_files[@]}"; do
  filename=$(basename "$file")
  curl -s -X POST "${API}/sendDocument" \
    -F chat_id="${TELEGRAM_CHAT_ID}" \
    -F document=@"${file}" \
    -F caption="${filename}" > /dev/null 2>&1
done

exit 0
