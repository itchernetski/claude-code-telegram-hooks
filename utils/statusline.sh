#!/bin/bash

# Claude Code Status Line
# Shows: folder · context% · 5-hour limit% · time before reset
#
# Example output: code · 54% ctx · 22% limit · 3h46m before reset
#
# Dependencies:
# - jq (brew install jq)
# - Claude Code with OAuth credentials in macOS Keychain

input=$(cat)

# === Usage API with 5-minute cache ===
CACHE_FILE="/tmp/claude_usage_cache"
CACHE_TTL=300

get_usage_data() {
  if [ -f "$CACHE_FILE" ]; then
    cache_age=$(($(date +%s) - $(stat -f %m "$CACHE_FILE")))
    if [ "$cache_age" -lt "$CACHE_TTL" ]; then
      cat "$CACHE_FILE"
      return
    fi
  fi

  creds=$(security find-generic-password -s "Claude Code-credentials" -w 2>/dev/null)
  token=$(echo "$creds" | jq -r '.claudeAiOauth.accessToken' 2>/dev/null)

  if [ -n "$token" ] && [ "$token" != "null" ]; then
    response=$(curl -s -H "Authorization: Bearer $token" \
      -H "anthropic-beta: oauth-2025-04-20" \
      https://api.anthropic.com/api/oauth/usage 2>/dev/null)

    pct=$(echo "$response" | jq -r '.five_hour.utilization' 2>/dev/null)
    resets_at=$(echo "$response" | jq -r '.five_hour.resets_at' 2>/dev/null)

    if [ -n "$pct" ] && [ "$pct" != "null" ]; then
      # Calculate time until reset
      if [ -n "$resets_at" ] && [ "$resets_at" != "null" ]; then
        # Strip microseconds and timezone, parse as UTC
        clean_ts=$(echo "$resets_at" | sed 's/\.[0-9]*//; s/+00:00$/Z/; s/Z$//')
        reset_ts=$(date -juf "%Y-%m-%dT%H:%M:%S" "$clean_ts" +%s 2>/dev/null)
        now_ts=$(date +%s)

        if [ -n "$reset_ts" ]; then
          diff=$((reset_ts - now_ts))
          if [ "$diff" -gt 0 ]; then
            hours=$((diff / 3600))
            mins=$(((diff % 3600) / 60))
            reset_time="${hours}h${mins}m"
          else
            reset_time="0h0m"
          fi
        else
          reset_time=""
        fi
      else
        reset_time=""
      fi

      printf "%.0f|%s" "$pct" "$reset_time" > "$CACHE_FILE"
      cat "$CACHE_FILE"
    fi
  fi
}

# === Directory name ===
cwd=$(echo "$input" | jq -r '.workspace.current_dir')
dir_name=$(basename "$cwd")
printf "\033[36m%s\033[0m" "$dir_name"

# === Context window % ===
usage=$(echo "$input" | jq '.context_window.current_usage')
if [ "$usage" != "null" ]; then
  current=$(echo "$usage" | jq '.input_tokens + .cache_creation_input_tokens + .cache_read_input_tokens')
  size=$(echo "$input" | jq '.context_window.context_window_size')

  if [ "$current" != "null" ] && [ "$size" != "null" ] && [ "$size" != "0" ]; then
    pct=$((current * 100 / size))

    if [ "$pct" -lt 50 ]; then color="\033[32m"
    elif [ "$pct" -lt 80 ]; then color="\033[33m"
    else color="\033[31m"; fi

    printf " \033[90m·\033[0m %b%d%% ctx\033[0m" "$color" "$pct"
  fi
fi

# === 5-hour usage limit % and reset time ===
usage_data=$(get_usage_data)
if [ -n "$usage_data" ]; then
  limit_pct=$(echo "$usage_data" | cut -d'|' -f1)
  reset_time=$(echo "$usage_data" | cut -d'|' -f2)

  if [ -n "$limit_pct" ]; then
    if [ "$limit_pct" -lt 50 ]; then color="\033[32m"
    elif [ "$limit_pct" -lt 80 ]; then color="\033[33m"
    else color="\033[31m"; fi

    printf " \033[90m·\033[0m %b%d%% limit\033[0m" "$color" "$limit_pct"
  fi

  if [ -n "$reset_time" ]; then
    printf " \033[90m·\033[0m \033[38;5;220m%s before reset\033[0m" "$reset_time"
  fi
fi
