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

| Component                        | Purpose                                            |
| -------------------------------- | -------------------------------------------------- |
| `hooks/hooks.json`               | Hook definitions (auto-read + dream trigger)       |
| `scripts/auto-read.sh`           | Reads MEMORY.md on first prompt per session         |
| `scripts/check-dream.sh`         | Checks if dream consolidation is needed after write |
| `skills/dream/SKILL.md`          | Dream consolidation protocol (sonnet subagent)     |
| `commands/dream.md`              | `/dream` slash command for manual trigger           |

**Auto-read:** UserPromptSubmit hook reads MEMORY.md on the first prompt per session using `session_id` for tracking.

**Dream:** PostToolUse hook triggers after `set_project_memory`/`update_project_memory`. Conditions: file > 25KB AND last dream > 24h ago. Spawns a sonnet subagent to consolidate.

## Key Constraints

- Memory files must be written in English only
- FastMCP dependency: `>=3.2.0, <4.0.0`
- Entry point is `project_mem_mcp.server:main` (defined in `pyproject.toml`)
