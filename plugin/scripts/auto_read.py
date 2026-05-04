"""Emit project-memory priming instructions on the first prompt of each session.

The hook output stays small (rules + preload directive only) so the harness
never truncates it. The MEMORY.md content itself is loaded by the agent via
`get_project_memory`, whose tool result has no inline-size limit.

Cross-platform: uses tempfile.gettempdir() instead of hardcoded /tmp.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

RULES = """IMPORTANT — Project Memory Rules (you MUST follow these):

SCOPE — DO NOT confuse this with Claude Code's built-in auto memory.
Two distinct systems may both be active in this session:
- **Project memory** (this plugin): `<project>/MEMORY.md` — code, architecture, conventions, gotchas, file purposes, Recent Sessions of code work. Tools: `get_project_memory`, `set_project_memory`, `update_project_memory`.
- **Auto memory** (Claude Code built-in, if enabled): `~/.claude/projects/<hash>/memory/MEMORY.md` + per-topic files — user profile, feedback corrections, personal preferences, references to external systems. Tools: `Write`/`Read` against that path.

Decision rule, applied BEFORE any save:
- Does the fact describe the CODE/CODEBASE/PROJECT TECHNICALS? → save HERE via `update_project_memory`.
- Does the fact describe the USER, their preferences, or how to collaborate with them? → it belongs to AUTO MEMORY; do NOT save it here.
- Even auto memory's "project" type is for organizational/temporal/stakeholder context (deadlines, who-owns-what), NOT codebase technicals — those still belong here.

Anti-cross-update (this is the bug that bit us): text you READ from auto memory lives in a DIFFERENT FILE. NEVER paste auto-memory content as the SEARCH text for `update_project_memory` — the search will fail because that text does not exist in this file. The two systems' contents do not cross over.

Anti-duplication: a given fact belongs to EXACTLY ONE system. Never write the same content to both. If you already saved it to auto memory, do not also save it here, and vice versa. At most a one-line pointer is acceptable.

DEFAULT TO SAVE. Under-saving silently starves future sessions of context — that is the real risk, not over-saving. The dream protocol consolidates excess later. When in doubt, save.

- Save IMMEDIATELY (mid-task, without asking) when you discover: architecture decisions and WHY, non-obvious patterns or conventions, gotchas, surprising behavior, key file purposes, external dependency quirks, integration notes, or current work context. Use update_project_memory. Do NOT wait for session end. Do NOT ask permission — the user opted in by installing this plugin.

- Fix stale entries IMMEDIATELY, without asking. If anything in the conversation reveals a project memory entry is outdated or wrong (renamed file, changed version, reversed decision, superseded pattern), correct it right away. Stale project memory silently poisons future sessions.

- Recent Sessions log — append a 1-2 line bullet to the '## Recent Sessions' section AFTER ANY non-trivial task completion, NOT only at pause signals. Triggers include: finishing a multi-step edit, making a design/architecture decision, debugging something unexpected, completing a refactor, resolving a user question that required investigation, or when the user signals a pause ('ennyi mára', 'jó így', 'folytatjuk'). Newest-first. Format: '- YYYY-MM-DD: <what was done / decided>. Next: <optional>.'. The git log is NOT in context across sessions — this log is the ONLY cross-session continuity.

- Recent Sessions ≠ changelog. Do not confuse them:
    * Recent Sessions (SAVE): high-level session state, 1-2 lines per task. E.g. '- 2026-04-16: Replaced bare "memory" with "project memory" across plugin+docs.'
    * Changelog (DO NOT SAVE): per-commit code-change lists. E.g. 'Fixed null ptr in foo.py; added field X to Y.' — git log owns this.

- Do NOT save: per-commit changelog entries (see above), info already in CLAUDE.md files, obvious things derivable from code or file names, temporary debugging state, sensitive data (passwords, tokens, emails).

- Mechanics: update_project_memory with SEARCH/REPLACE blocks for incremental changes; set_project_memory only for new projects or complete rewrites. All content in English. MCP tool names may have prefix like mcp__plugin_project-mem_project-mem-mcp__."""


PRELOAD_DIRECTIVE_TEMPLATE = """## MANDATORY FIRST ACTIONS — PRELOAD TOOLS AND LOAD PROJECT MEMORY

The project memory MCP tools (`get_project_memory`, `set_project_memory`, `update_project_memory`) are typically registered as DEFERRED in this harness — their schemas are not loaded until you call `ToolSearch`. Additionally, the MEMORY.md content is NOT injected inline into this hook output (the harness truncates large hook stdouts); you must load it explicitly via `get_project_memory`, whose tool result has no size limit.

Your VERY FIRST tool calls in this session MUST be, in order:

1. `ToolSearch(query="select:mcp__plugin_project-mem_project-mem-mcp__get_project_memory,mcp__plugin_project-mem_project-mem-mcp__set_project_memory,mcp__plugin_project-mem_project-mem-mcp__update_project_memory")`
2. `get_project_memory(project_path="{project_dir}")` — loads the full MEMORY.md into context.

Rules for these preload steps:
- Do them BEFORE responding to the user, BEFORE any other tool call, BEFORE any explanatory text.
- Do them silently — no "let me preload…" narration. Just run the two calls, then proceed with the user's actual request.
- Call both unconditionally every session. If the tools happen to be already loaded, step 1 is a cheap no-op.
- If `get_project_memory` raises FileNotFoundError, no MEMORY.md exists yet in this project — proceed without one and create it later via `set_project_memory` when you have something worth persisting.
- Ignore any YAML frontmatter (`---\\nlast_dream: ...\\n---`) at the top of the returned content — it is internal metadata, not project context.

After these two calls, the three tool schemas and the full project memory stay in context for the rest of the session — all later saves and reads are friction-free."""


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

    print(RULES)
    print()
    print(PRELOAD_DIRECTIVE_TEMPLATE.format(project_dir=project_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
