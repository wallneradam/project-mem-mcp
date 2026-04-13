# Project Memory MCP

An MCP server and Claude Code plugin for persistent project memory. Allows AI agents to maintain knowledge about projects between conversations via `MEMORY.md` files.

## Features

- **Store & retrieve** project knowledge in Markdown format
- **Incremental updates** via SEARCH/REPLACE patches
- **Auto-read hook** — automatically loads project memory on first prompt (Claude Code plugin)
- **Dream consolidation** — automatic memory cleanup and deduplication (Claude Code plugin)

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

Overwrites the entire `MEMORY.md`. Use when creating a new memory or when patches fail.

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
Text to find in the memory file
=======
Text to replace it with
>>>>>>> REPLACE
```

The search text must appear exactly once in the file. Use empty replacement to remove content.

## Plugin Features

When installed as a Claude Code plugin, you also get:

### Memory Skill (auto-trigger)

Guides Claude on when and how to save to project memory. Automatically triggers when insights worth persisting are discovered — architecture decisions, gotchas, non-obvious patterns, current work context. No manual intervention needed.

### Auto-read Hook

Automatically reads `MEMORY.md` into context on the first prompt of each session. No manual tool call needed.

### Dream Consolidation

Automatic memory maintenance triggered after writes when:
- File size exceeds 25KB
- Last consolidation was more than 24 hours ago

The dream spawns a sonnet subagent that:
- Removes content duplicated in CLAUDE.md files
- Restructures for clarity and LLM readability
- Creates a backup before consolidating

Manual trigger: `/dream`

## Security

- Project paths are validated against `--allowed-dir` arguments
- Memory files should never contain sensitive information
- Memory files must be in English

## Dependencies

- fastmcp (>=3.2.0, <4.0.0)

## License

MIT
