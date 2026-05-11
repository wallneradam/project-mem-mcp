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
| `scripts/continuous_save_prime.py` | SessionStart hook — injects `additionalContext` keeping inline save-awareness active for the whole session |
| `scripts/check_dream.py`         | Checks if dream consolidation is needed after write   |
| `skills/project-memory/SKILL.md` | Auto-trigger: when and how to save to project memory  |
| `skills/dream/SKILL.md`          | Dream consolidation protocol — invokes the named subagent below |
| `agents/dream-consolidator.md`   | Named subagent definition with `model: sonnet` pinned via frontmatter |
| `commands/dream.md`              | `/dream` slash command for manual trigger             |

**Auto-read:** UserPromptSubmit hook emits RULES + PRELOAD_DIRECTIVE on the first prompt per session (tracked via `session_id` state file). The directive instructs the agent to call `ToolSearch` to preload the three MCP tool schemas and then `get_project_memory` to load MEMORY.md — the content itself is not inlined in the hook output because the harness truncates large stdouts. The directive also tells the agent to ignore the `last_dream:` YAML frontmatter returned in the tool result.

**Continuous save-awareness:** SessionStart hook emits `hookSpecificOutput.additionalContext` (pattern copied from Anthropic's explanatory-output-style plugin) that primes the agent to call `update_project_memory` inline whenever non-trivial project knowledge surfaces, not only at prompt-time. Complements `auto_read.py`: UserPromptSubmit installs rules + loads MEMORY.md; SessionStart keeps the save impulse active throughout the session.

**Dream:** PostToolUse hook triggers after project memory writes (regex matcher: `.*set_project_memory|.*update_project_memory`). Conditions: file > 50KB AND last dream > 24h ago. The dream skill invokes the `dream-consolidator` named subagent (Agent tool with `subagent_type: "dream-consolidator"`, **no `model:` parameter**), which is pinned to Sonnet via its definition's `model: sonnet` frontmatter. Model resolution order in Claude Code: env var `CLAUDE_CODE_SUBAGENT_MODEL` → per-invocation `model:` parameter → agent definition's frontmatter → parent's model. Earlier versions relied on a prose "spawn with model: sonnet" instruction; that was unreliable and frequently inherited Opus from the parent.

The `last_dream:` frontmatter rewrite is owned by the subagent (it runs `update_dream_timestamp.py` via Bash after `set_project_memory`), not by the dream skill's post-step. This ensures a correct timestamp even when the consolidator is invoked directly via the Agent tool (bypassing the skill).

## Key Constraints

- Project memory files must be written in English only
- FastMCP dependency: `>=3.2.0, <4.0.0`
- Entry point is `project_mem_mcp.server:main` (defined in `pyproject.toml`)
