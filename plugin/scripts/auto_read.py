"""Read project memory on first prompt only (per session).

Uses session_id from hook input JSON for reliable session tracking.
Cross-platform: uses tempfile.gettempdir() instead of hardcoded /tmp.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

RULES = """IMPORTANT — Project Memory Rules (you MUST follow these):
- When you discover non-obvious insights (architecture decisions, gotchas, conventions, surprising behavior), IMMEDIATELY save them using the update_project_memory MCP tool. Do NOT wait until the end of the session.
- When existing memory information becomes outdated or wrong (anywhere in the conversation — a renamed file, changed version, reversed decision, superseded pattern), fix it IMMEDIATELY and WITHOUT asking the user. Do not defer to end of session. Stale memory silently poisons future sessions.
- At the end of a meaningful task, or when the user signals a pause (e.g. 'ennyi mára', 'jó így', 'folytatjuk'), append a 1-2 line entry to the '## Recent Sessions' section (newest-first, format: '- YYYY-MM-DD: <what was done / decided>. Next: <optional>'). The git log is NOT in your context — this log is the only way future sessions know where you left off.
- Use update_project_memory with SEARCH/REPLACE blocks for incremental changes. Use set_project_memory only for new projects or complete rewrites.
- Do NOT save: changelog entries, info already in CLAUDE.md, obvious things, sensitive data.
- All memory content must be in English.
- The MCP tool names are: get_project_memory, set_project_memory, update_project_memory (may have a prefix like mcp__plugin_project-mem_project-mem-mcp__)."""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    session_id = payload.get("session_id") or str(os.getpid())
    state_file = Path(tempfile.gettempdir()) / f"mem-read-{session_id}"

    if state_file.exists():
        return 0
    state_file.touch()

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if not project_dir:
        return 0

    memory_file = Path(project_dir) / "MEMORY.md"
    if not memory_file.is_file():
        return 0

    try:
        content = memory_file.read_text(encoding="utf-8")
    except OSError:
        return 0

    print(f"=== Project Memory ({project_dir}) ===")
    print(content)
    print("=== End Project Memory ===")
    print()
    print(RULES)
    return 0


if __name__ == "__main__":
    sys.exit(main())
