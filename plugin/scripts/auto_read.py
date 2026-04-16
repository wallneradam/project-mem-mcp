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

DEFAULT TO SAVE. Under-saving silently starves future sessions of context — that is the real risk, not over-saving. The dream protocol consolidates excess later. When in doubt, save.

- Save IMMEDIATELY (mid-task, without asking) when you discover: architecture decisions and WHY, non-obvious patterns or conventions, gotchas, surprising behavior, key file purposes, external dependency quirks, integration notes, or current work context. Use update_project_memory. Do NOT wait for session end. Do NOT ask permission — the user opted in by installing this plugin.

- Fix stale entries IMMEDIATELY, without asking. If anything in the conversation reveals a project memory entry is outdated or wrong (renamed file, changed version, reversed decision, superseded pattern), correct it right away. Stale project memory silently poisons future sessions.

- Recent Sessions log — append a 1-2 line bullet to the '## Recent Sessions' section AFTER ANY non-trivial task completion, NOT only at pause signals. Triggers include: finishing a multi-step edit, making a design/architecture decision, debugging something unexpected, completing a refactor, resolving a user question that required investigation, or when the user signals a pause ('ennyi mára', 'jó így', 'folytatjuk'). Newest-first. Format: '- YYYY-MM-DD: <what was done / decided>. Next: <optional>.'. The git log is NOT in context across sessions — this log is the ONLY cross-session continuity.

- Recent Sessions ≠ changelog. Do not confuse them:
    * Recent Sessions (SAVE): high-level session state, 1-2 lines per task. E.g. '- 2026-04-16: Replaced bare "memory" with "project memory" across plugin+docs.'
    * Changelog (DO NOT SAVE): per-commit code-change lists. E.g. 'Fixed null ptr in foo.py; added field X to Y.' — git log owns this.

- Do NOT save: per-commit changelog entries (see above), info already in CLAUDE.md files, obvious things derivable from code or file names, temporary debugging state, sensitive data (passwords, tokens, emails).

- Mechanics: update_project_memory with SEARCH/REPLACE blocks for incremental changes; set_project_memory only for new projects or complete rewrites. All content in English. MCP tool names may have prefix like mcp__plugin_project-mem_project-mem-mcp__."""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    session_id = payload.get("session_id") or str(os.getpid())
    state_file = Path(tempfile.gettempdir()) / f"project-memory-read-{session_id}"

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
