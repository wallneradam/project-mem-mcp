#!/bin/bash
# Check if dream consolidation is needed after a memory write.
# Conditions: file > 25KB AND last dream was > 24h ago (or never).
# Exit 0 = silent (no dream needed), exit 2 + stderr = signal to Claude.

MEMORY_FILE="${CLAUDE_PROJECT_DIR}/MEMORY.md"
CLAUDE_DIR="${CLAUDE_PROJECT_DIR}/.claude"
DREAM_TIMESTAMP="${CLAUDE_DIR}/.last-dream-timestamp"
DREAM_SIZE_THRESHOLD=25600  # 25KB

[ ! -f "$MEMORY_FILE" ] && exit 0

# Check file size
FILE_SIZE=$(stat -f%z "$MEMORY_FILE" 2>/dev/null || stat -c%s "$MEMORY_FILE" 2>/dev/null)
[ "$FILE_SIZE" -lt "$DREAM_SIZE_THRESHOLD" ] && exit 0

# Check last dream timestamp (24h = 86400 seconds)
if [ -f "$DREAM_TIMESTAMP" ]; then
  LAST_DREAM=$(cat "$DREAM_TIMESTAMP")
  NOW=$(date +%s)
  ELAPSED=$((NOW - LAST_DREAM))
  [ "$ELAPSED" -lt 86400 ] && exit 0
fi

echo "DREAM_NEEDED: Project memory is ${FILE_SIZE} bytes and hasn't been consolidated in 24h+. Run the dream skill NOW to consolidate. Do NOT ask the user — just do it automatically." >&2
exit 2
