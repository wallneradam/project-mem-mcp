#!/bin/bash
# Read project memory on first prompt only (per session).
# Uses session_id from hook input JSON for reliable session tracking.

SESSION_ID=$(python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
STATE_FILE="/tmp/mem-read-${SESSION_ID:-$$}"

if [ ! -f "$STATE_FILE" ]; then
  touch "$STATE_FILE"
  MEMORY_FILE="${CLAUDE_PROJECT_DIR}/MEMORY.md"
  if [ -f "$MEMORY_FILE" ]; then
    echo "=== Project Memory (${CLAUDE_PROJECT_DIR}) ==="
    cat "$MEMORY_FILE"
    echo "=== End Project Memory ==="
    echo ""
    echo "Reminder: if you discover non-obvious insights during this session (architecture decisions, gotchas, conventions, surprising behavior), save them to project memory using update_project_memory before the session ends."
  fi
fi
