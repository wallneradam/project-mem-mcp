# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

An MCP server + Claude Code plugin that manages persistent project memory files (`MEMORY.md`) for AI agents. Built with FastMCP 3.x and Python 3.11+.

The MCP server lives in `src/project_mem_mcp/server.py`. The plugin layer adds auto-read hooks and a dream (consolidation) system.

## Development Commands

```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -e .

# Run the server locally
project-mem-mcp
project-mem-mcp --allowed-dir /path/to/projects

# Run without installation (via uvx)
uvx project-mem-mcp

# Plugin installation (in Claude Code)
# /plugin marketplace add /path/to/project-mem-mcp
# /plugin install project-mem@cc-plugin-project-mem
```

There are no tests or linting configured in this project.

## Architecture

### MCP Server (`src/project_mem_mcp/server.py`)

Three MCP tools:

| Tool                    | Purpose                                            |
| ----------------------- | -------------------------------------------------- |
| `get_project_memory`    | Read the entire `MEMORY.md` for a project          |
| `set_project_memory`    | Overwrite the entire `MEMORY.md`                   |
| `update_project_memory` | Apply a single SEARCH/REPLACE patch to `MEMORY.md` |

**Security model:** Project paths are validated against `--allowed-dir` arguments. If none are provided, the server defaults to the current working directory.

**Patch format:** `update_project_memory` uses a custom SEARCH/REPLACE block format (not unified diff). The search text must appear exactly once in the file; non-unique matches raise `ValueError`. Only one block per call is allowed.

### Plugin Layer (`plugin/`)

| Component                        | Purpose                                              |
| -------------------------------- | ---------------------------------------------------- |
| `.mcp.json`                      | Registers MCP server via `uvx` for plugin installs    |
| `hooks/hooks.json`               | Hook definitions (auto-read, dream trigger)           |
| `scripts/auto_read.py`           | Emits RULES + PRELOAD_DIRECTIVE on first prompt per session; agent then loads MEMORY.md via `get_project_memory` |
| `scripts/check_dream.py`         | Checks if dream consolidation is needed after write   |
| `scripts/insight_save_nudge.py`  | Stop hook: reminds model to save when reply had `★ Insight` block |
| `skills/project-memory/SKILL.md` | Auto-trigger: when and how to save to project memory  |
| `skills/dream/SKILL.md`          | Dream consolidation protocol (sonnet subagent)        |
| `commands/dream.md`              | `/dream` slash command for manual trigger             |

**Auto-read:** UserPromptSubmit hook emits RULES + PRELOAD_DIRECTIVE on the first prompt per session (tracked via `session_id` state file). The directive instructs the agent to call `ToolSearch` to preload the three MCP tool schemas and then `get_project_memory` to load MEMORY.md — the content itself is not inlined in the hook output because the harness truncates large stdouts. The directive also tells the agent to ignore the `last_dream:` YAML frontmatter returned in the tool result.

**Dream:** PostToolUse hook triggers after project memory writes (regex matcher: `.*set_project_memory|.*update_project_memory`). Conditions: file > 50KB AND last dream > 24h ago. Spawns a sonnet subagent to consolidate.

**Insight save nudge:** Stop hook scans the last assistant message in the transcript for a `★ Insight` marker. The marker is produced by Claude Code's built-in **Explanatory** output style (selectable via `/config` → Output Style) and also appears in setups where a project or global `CLAUDE.md` instructs the model to emit insight blocks, or via custom output styles. If present, emits a stderr reminder (exit 2) so the model can decide whether to save to project memory. Uses `stop_hook_active` as a loop guard. No-op in sessions where no `★ Insight` block is emitted.
## Key Constraints

- Project memory files must be written in English only
- FastMCP dependency: `>=3.2.0, <4.0.0`
- Entry point is `project_mem_mcp.server:main` (defined in `pyproject.toml`)
