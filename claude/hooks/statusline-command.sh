#!/usr/bin/env bash
# statusline-command.sh
# Displays PS1-style session info in the Claude Code status line.
# Input: JSON via stdin (see Claude Code statusLine spec)
#
# Output format:
#   user:dir (branch) | Model Name | Ctx:XX% | 5h:XX%
#
# Colors match ~/.bashrc PS1:
#   user  -> bold green  (\033[01;32m)
#   dir   -> bold blue   (\033[01;34m)
#   branch-> bold yellow (\033[01;33m)
# Context / rate-limit colors:
#   >=80% -> red    (warning: nearly exhausted)
#   >=60% -> yellow (caution)
#   <60%  -> default

input=$(cat)

# --- Extract fields from JSON ---
cwd=$(echo "$input"   | jq -r '.workspace.current_dir // .cwd // ""')
model=$(echo "$input" | jq -r '.model.display_name // ""')
used_pct=$(echo "$input" | jq -r '.context_window.used_percentage // empty')
five_h=$(echo "$input"       | jq -r '.rate_limits.five_hour.used_percentage // empty')
five_resets=$(echo "$input" | jq -r '.rate_limits.five_hour.resets_at // empty')

# --- PS1-style: user and dir ---
user=$(whoami)
dir_name=$(basename "$cwd")

# Git branch (skip lock files to avoid interfering with running git processes)
branch=""
if [ -n "$cwd" ] && [ -d "$cwd/.git" ]; then
    branch=$(git -C "$cwd" --no-optional-locks branch 2>/dev/null \
             | grep '^\*' | sed 's/\* //')
fi

# --- Build the prompt string using printf for ANSI colors ---

# "user:dir" part  (bold green user, bold blue dir)
prompt=$(printf '\033[01;32m%s\033[00m:\033[01;34m%s\033[00m' "$user" "$dir_name")

# " (branch)" part  (bold yellow), only when inside a git repo
if [ -n "$branch" ]; then
    prompt="${prompt}$(printf ' \033[01;33m(%s)\033[00m' "$branch")"
fi

# Separator before model/stats
parts="$prompt"

# Model display name
if [ -n "$model" ]; then
    parts="${parts} | ${model}"
fi

# Context window usage percentage
if [ -n "$used_pct" ]; then
    pct_int=$(printf '%.0f' "$used_pct")
    if [ "$pct_int" -ge 80 ]; then
        ctx_str=$(printf '\033[0;31mCtx:%d%%\033[0m' "$pct_int")
    elif [ "$pct_int" -ge 60 ]; then
        ctx_str=$(printf '\033[0;33mCtx:%d%%\033[0m' "$pct_int")
    else
        ctx_str=$(printf 'Ctx:%d%%' "$pct_int")
    fi
    parts="${parts} | ${ctx_str}"
fi

# 5-hour rate limit usage (only shown when data is available)
if [ -n "$five_h" ]; then
    five_int=$(printf '%.0f' "$five_h")
    if [ "$five_int" -ge 80 ]; then
        five_str=$(printf '\033[0;31m5h:%d%%\033[0m' "$five_int")
    elif [ "$five_int" -ge 60 ]; then
        five_str=$(printf '\033[0;33m5h:%d%%\033[0m' "$five_int")
    else
        five_str=$(printf '5h:%d%%' "$five_int")
    fi

    # Append reset countdown if available (e.g. "5h:45% reset:1h23m")
    if [ -n "$five_resets" ]; then
        now=$(date +%s)
        remaining=$(( five_resets - now ))
        if [ "$remaining" -gt 0 ]; then
            hrs=$(( remaining / 3600 ))
            mins=$(( (remaining % 3600) / 60 ))
            if [ "$hrs" -gt 0 ]; then
                reset_str="reset:${hrs}h${mins}m"
            else
                reset_str="reset:${mins}m"
            fi
            five_str="${five_str} ${reset_str}"
        fi
    fi

    parts="${parts} | ${five_str}"
fi

printf '%b' "$parts"
