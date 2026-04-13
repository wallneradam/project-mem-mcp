---
name: memory
description: >
  Maintain persistent project memory in MEMORY.md using MCP tools.
  ALWAYS save to project memory when you discover something worth remembering
  for future sessions: architecture decisions, non-obvious patterns, gotchas,
  key file purposes, integration notes, or current work context.
  ALWAYS update project memory when existing information becomes outdated or wrong.
  ALWAYS remove completed task details from Current Work after extracting lessons.
  Do NOT save: changelog entries (git handles this), information already in CLAUDE.md,
  trivial/obvious things, session timestamps, temporary debugging notes.
  Do NOT use this skill for simple questions or when only reading code.
tools: mcp__*__get_project_memory, mcp__*__set_project_memory, mcp__*__update_project_memory
---

# Memory — Persistent Project Knowledge

You have access to a project memory system that persists knowledge between conversations
via a `MEMORY.md` file in the project directory.

The memory is automatically loaded at the start of each session (via hook).
Your job is to **keep it up to date** as you work.

## When to Save

Save when you learn something that took effort to discover and would help in future sessions:

- **Architecture decisions** and WHY they were made
- **Code patterns and conventions** not obvious from the code itself
- **Gotchas, edge cases, and hard-won insights** (e.g., "X looks like it should work but fails because Y")
- **Important file paths and their purposes** when the structure is non-obvious
- **External dependency notes** (API quirks, version constraints, integration details)
- **Current work context** when a task spans multiple sessions (remove when done)

## When NOT to Save

- Information already in CLAUDE.md files — no duplication
- Change log entries ("Fixed X", "Added Y") — git history handles this
- Completed task details — extract the lesson, delete the task info
- Anything obvious from file names, code structure, or standard conventions
- Temporary debugging state or session-specific notes

## How to Save

**Prefer `update_project_memory`** for incremental changes — it's safer and preserves
the rest of the file:

```
<<<<<<< SEARCH
existing text to find
=======
updated or new text
>>>>>>> REPLACE
```

**Use `set_project_memory`** only when:
- Creating a memory file for a new project
- The file needs complete reorganization
- `update_project_memory` fails (search text not found or not unique)

## Rules

- **English only** — all memory content must be in English
- **No sensitive data** — never store passwords, tokens, API keys, emails
- **Update, don't duplicate** — before adding, check if similar info already exists
- **Current knowledge only** — the memory reflects what is true NOW, not history
- **Be concise but complete** — optimize for LLM readability, every line should earn its place

## Recommended Structure

```markdown
# Project Name

## Overview
[2-3 sentences: what is this, main technologies]

## Key Locations
[Important files and their purposes]

## Conventions & Patterns
[Non-obvious rules, naming conventions, architectural patterns]

## Lessons Learned
[Gotchas, edge cases, things that took time to figure out]

## Current Work
[Only if there's ongoing work spanning sessions — DELETE when done]
```
