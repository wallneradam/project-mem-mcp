# Project Memory MCP

An MCP server and Claude Code plugin for persistent project memory. Allows AI agents to maintain knowledge about projects between conversations via `MEMORY.md` files.

## Features

- **Store & retrieve** project knowledge in Markdown format
- **Incremental updates** via SEARCH/REPLACE patches
- **Auto-read hook** — automatically loads project memory on first prompt (Claude Code plugin)
- **Insight save nudge** — Stop hook that reminds the model to save when its reply contained a `★ Insight` block from Claude Code's built-in Explanatory output style (Claude Code plugin)
- **Dream consolidation** — automatic project memory cleanup and deduplication (Claude Code plugin)

## Installation

### Claude Code Plugin (recommended)

Installs the MCP server, auto-read hook, and dream consolidation:

```bash
/plugin marketplace add /path/to/project-mem-mcp
/plugin install project-mem@cc-plugin-project-mem
```

### Standalone MCP Server

For Codex, Claude Desktop, Cursor, or other MCP clients:

```bash
uvx project-mem-mcp
```

#### MCP Client Configuration

```json
{
  "mcpServers": {
    "project-mem-mcp": {
      "command": "uvx",
      "args": [
        "project-mem-mcp",
        "--allowed-dir", "/path/to/your/projects"
      ]
    }
  }
}
```

The `--allowed-dir` argument restricts which directories the server can access. Can be used multiple times. Defaults to the current working directory if omitted.

### Install from Source

```bash
git clone https://github.com/pynesys/project-mem-mcp.git
cd project-mem-mcp
python -m venv venv
source venv/bin/activate
pip install -e .
```

## Tools

### get_project_memory

Retrieves the entire `MEMORY.md` for a project.

```
get_project_memory(project_path: str) -> str
```

### set_project_memory

Overwrites the entire `MEMORY.md`. Use when creating a new project memory or when patches fail.

```
set_project_memory(project_path: str, project_info: str)
```

### update_project_memory

Applies a single SEARCH/REPLACE patch to `MEMORY.md`:

```
update_project_memory(project_path: str, patch_content: str)
```

Patch format:

```
<<<<<<< SEARCH
Text to find in the project memory file
=======
Text to replace it with
>>>>>>> REPLACE
```

The search text must appear exactly once in the file. Use empty replacement to remove content.

## Plugin Features

When installed as a Claude Code plugin, you also get:

### Project-memory Skill (auto-trigger)

Guides Claude on when and how to save to project memory. Automatically triggers when insights worth persisting are discovered — architecture decisions, gotchas, non-obvious patterns, current work context. The skill is marked `user-invocable: false` so it does not appear in the slash command picker; the main model invokes it autonomously.

### Auto-read Hook

Automatically reads `MEMORY.md` into context on the first prompt of each session. No manual tool call needed.

### Insight Save Nudge (Stop hook)

At the end of each assistant turn, a lightweight Stop hook checks whether the reply contained a `★ Insight` block. Such blocks are produced by Claude Code's built-in **Explanatory** output style (selectable via `/config` → Output Style, alongside Default and Learning), and can also appear in other setups — e.g. when a project or global `CLAUDE.md` instructs the model to emit insight blocks, or via custom output styles. If the marker is present, the hook injects a short reminder asking the model to save any durable points (architecture, decisions, gotchas, conventions) to `MEMORY.md` — including, when appropriate, a 1-2 line `## Recent Sessions` entry.

Why this signal: Insight blocks are pre-curated by the model as meaningful conclusions — exactly the content that belongs in project memory. The hook is deterministic (simple string match, no LLM classifier), adds zero cost, and fires only when there is plausibly something worth saving. A loop guard (`stop_hook_active`) prevents repeated nudging on the same stop cycle.

No-op in sessions where no `★ Insight` block is emitted.

### Dream Consolidation

Automatic project memory maintenance triggered after writes when:
- File size exceeds 25KB
- Last consolidation was more than 24 hours ago

The dream spawns a sonnet subagent that:
- Removes content duplicated in CLAUDE.md files
- Restructures for clarity and LLM readability

No backup is written; use `git` to recover the pre-dream state if needed.

Manual trigger: `/dream`

The last-dream timestamp is stored as `last_dream:` inside a YAML frontmatter block at the top of `MEMORY.md`. Projects previously using this plugin may still have a `.claude/.last-dream-timestamp` file — that file is now ignored and can be safely deleted (the first dream run after upgrade repopulates the frontmatter).

## Security

- Project paths are validated against `--allowed-dir` arguments
- Project memory files should never contain sensitive information
- Project memory files must be in English

## Dependencies

- fastmcp (>=3.2.0, <4.0.0)

## License

MIT
