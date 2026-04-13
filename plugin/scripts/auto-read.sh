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
    echo "IMPORTANT — Project Memory Rules (you MUST follow these):"
    echo "- When you discover non-obvious insights (architecture decisions, gotchas, conventions, surprising behavior), IMMEDIATELY save them using the update_project_memory MCP tool. Do NOT wait until the end of the session."
    echo "- When existing memory information becomes outdated or wrong, update it immediately."
    echo "- Use update_project_memory with SEARCH/REPLACE blocks for incremental changes. Use set_project_memory only for new projects or complete rewrites."
    echo "- Do NOT save: changelog entries, info already in CLAUDE.md, obvious things, sensitive data."
    echo "- All memory content must be in English."
    echo "- The MCP tool names are: get_project_memory, set_project_memory, update_project_memory (may have a prefix like mcp__plugin_project-mem_project-mem-mcp__)."
  fi
fi
