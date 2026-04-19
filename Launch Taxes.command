#!/bin/bash
# Double-click to launch Farm Ledger. Detaches from its Terminal window so
# the launch feels seamless (Terminal flashes briefly, then closes on its own).

# --- First invocation: relaunch self detached, then close our Terminal window.
if [ "$1" != "--detached" ]; then
  DIR="$(cd "$(dirname "$0")" && pwd)"
  nohup "$DIR/$(basename "$0")" --detached >/dev/null 2>&1 &
  # Close the Terminal window we're running in (macOS default terminal).
  TTY_OF_SELF="$(tty 2>/dev/null)"
  if [ -n "$TTY_OF_SELF" ]; then
    osascript <<EOF >/dev/null 2>&1 &
tell application "Terminal"
  set winList to (every window whose tty of its selected tab is "$TTY_OF_SELF")
  repeat with w in winList
    close w saving no
  end repeat
end tell
EOF
  fi
  exit 0
fi

# --- Detached invocation: actual launch logic below.
cd "$(dirname "$0")" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

LOG="$PWD/Farm Ledger/launch.log"
exec >>"$LOG" 2>&1
echo "--- $(date) launching from Launch Taxes.command ---"

if [ ! -d ".venv" ]; then
  echo "First-time setup…"
  /opt/homebrew/bin/python3 -m venv .venv || python3 -m venv .venv
  ./.venv/bin/pip install -q -r "Farm Ledger/requirements.txt"
fi

# If already running, just reopen the browser and exit.
if curl -s -o /dev/null http://127.0.0.1:5173/; then
  open "http://127.0.0.1:5173"
  exit 0
fi

cleanup() { jobs -p | xargs -r kill 2>/dev/null; }
trap cleanup EXIT TERM INT

# Start ttyd (Claude terminal) on 5174 if available. Agents run with cwd inside the
# data tree so relative paths like "MDDocs/Profile.md" resolve correctly; Claude Code
# still finds .claude/ and CLAUDE.md by walking up to the project root.
TTYD="$(command -v ttyd)"; CLAUDE="$(command -v claude)"
if [ -n "$TTYD" ] && [ -n "$CLAUDE" ]; then
  DATA_ROOT_ABS="$PWD/Farm Ledger/YearData"
  XTERM_THEME='{"background":"#000000","foreground":"#ffffff","cursor":"#ffffff","cursorAccent":"#000000","selectionBackground":"rgba(255,255,255,0.3)","black":"#000000","red":"#cd3131","green":"#0dbc79","yellow":"#e5e510","blue":"#2472c8","magenta":"#bc3fbc","cyan":"#11a8cd","white":"#e5e5e5","brightBlack":"#666666","brightRed":"#f14c4c","brightGreen":"#23d18b","brightYellow":"#f5f543","brightBlue":"#3b8eea","brightMagenta":"#d670d6","brightCyan":"#29b8db","brightWhite":"#ffffff"}'
  "$TTYD" -p 5174 -i 127.0.0.1 -W \
    -t "fontSize=14" \
    -t "fontFamily=Menlo, Monaco, 'SF Mono', Consolas, monospace" \
    -t "lineHeight=1.3" \
    -t "cursorBlink=true" \
    -t "cursorStyle=block" \
    -t "theme=$XTERM_THEME" \
    bash -lc "cd \"$DATA_ROOT_ABS\" && exec \"$CLAUDE\"" &
fi

# Open browser when Flask responds.
( for i in {1..30}; do
    curl -s -o /dev/null http://127.0.0.1:5173/ && { open "http://127.0.0.1:5173"; break; }
    sleep 0.2
  done ) &

exec ./.venv/bin/python "Farm Ledger/app.py"
