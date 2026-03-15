#!/bin/bash
# Creates a timestamp marker file at session start
# Used by telegram-notify.sh to detect files modified during session

input=$(cat)
session_id=$(echo "$input" | jq -r '.session_id // "default"')
touch "/tmp/.claude_session_start_${session_id}"
exit 0
