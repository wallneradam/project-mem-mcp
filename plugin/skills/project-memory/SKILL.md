---
name: project-memory
user-invocable: false
description: >
  Maintain persistent project memory in MEMORY.md using MCP tools.
  DEFAULT TO SAVE — under-saving silently starves future sessions of context; the dream
  protocol consolidates excess later. When in doubt, save.
  ALWAYS save project memory IMMEDIATELY (mid-task, without asking) when you discover
  architecture decisions, non-obvious patterns or conventions, gotchas, surprising
  behavior, key file purposes, external dependency quirks, or current work context.
  ALWAYS fix project memory entries when existing information becomes outdated or wrong
  (renamed file, changed version, reversed decision) — do not defer, do not ask.
  ALWAYS append a 1-2 line entry to '## Recent Sessions' AFTER ANY non-trivial task
  completion (NOT only at pause signals): finishing a multi-step edit, making a design
  decision, debugging something unexpected, completing a refactor, resolving a question
  that required investigation, or when the user signals a pause ("ennyi mára", "jó így",
  "folytatjuk"). The git log is NOT in context across sessions — this log is the only
  cross-session continuity.
  Recent Sessions ≠ changelog: Recent Sessions is high-level session state (SAVE);
  changelog is per-commit code-change lists (git owns that — DO NOT save).
  Do NOT save: information already in CLAUDE.md, obvious things derivable from code,
  temporary debugging state, sensitive data.
  Do NOT use this skill for simple questions or when only reading code.
tools: mcp__*__get_project_memory, mcp__*__set_project_memory, mcp__*__update_project_memory
---

# Project Memory — Persistent Project Knowledge

You have access to a project memory system that persists knowledge between conversations
via a `MEMORY.md` file in the project directory.

The project memory is automatically loaded at the start of each session (via hook).
Your job is to **keep it up to date** as you work.

## Scope — Project Memory vs. Auto Memory

This skill manages **project memory** — a single `MEMORY.md` file in the project
directory that stores shared, code-level knowledge (architecture, conventions,
gotchas). It is distinct from **auto memory**, Claude Code's built-in per-user
memory under `~/.claude/projects/<hash>/memory/`, which stores personal context
about the user and their collaboration preferences.

| Aspect   | Project memory                | Auto memory                               |
| -------- | ----------------------------- | ----------------------------------------- |
| Location | `<project>/MEMORY.md`         | `~/.claude/projects/<hash>/memory/`       |
| Scope    | Shared (team, any agent)      | Private (per user, per working directory) |
| Content  | Code/architecture/conventions | User profile, feedback, session state     |
| Language | English only                  | Conversation language                     |

Rule of thumb: **if it describes the code, it belongs here.** If it describes
the user or how to collaborate with them, it belongs to auto memory. Never
duplicate between the two systems; at most keep a one-line pointer in auto
memory referencing the project memory.

## Default to Save

**Under-saving silently starves future sessions of context — that is the real risk,
not over-saving.** The dream protocol consolidates excess later. When in doubt, save.

Agents frequently under-save because nothing feels "important enough" in isolation;
resist that instinct. If the insight took you any effort to reach (debugging, reading
docs, trial and error), a future agent will want it too. Err on the side of writing
one short bullet rather than nothing.

## When to Save

Save when you learn something that took effort to discover and would help in future sessions:

- **Architecture decisions** and WHY they were made
- **Code patterns and conventions** not obvious from the code itself
- **Gotchas, edge cases, and hard-won insights** (e.g., "X looks like it should work but fails because Y")
- **Important file paths and their purposes** when the structure is non-obvious
- **External dependency notes** (API quirks, version constraints, integration details)
- **Current work context** when a task spans multiple sessions (remove when done)
- **Recent Sessions log** — a 1-2 line entry at the end of each meaningful task or session,
  so future sessions know where we left off (git log is NOT in the agent's context)

## Recent Sessions — Format & Rules

Append a short bullet under `## Recent Sessions` **AFTER ANY non-trivial task completion**,
not only at pause signals. Triggers include:

- Finishing a multi-step edit (code, docs, config)
- Making a design, architecture, or naming decision
- Debugging something unexpected or surprising
- Completing a refactor or renaming
- Resolving a user question that required investigation
- Abandoning an approach after trying it ("tried X, reverted because Y")
- The user signals a pause ("ennyi mára", "jó így", "folytatjuk", "szünet")
- A decision was made that might matter later

If you finished a meaningful piece of work and you didn't add a bullet, you probably
should have.

Entry format (one line, ~15-25 words):

```
- YYYY-MM-DD: <what was done / decided / left half-done>. Next: <optional next step>.
```

Focus on **state and decisions**, not file-by-file changes (those are in git diff).
Examples:
- `2026-04-14: Added Recent Sessions section to project memory skill + dream protocol. Next: test dream consolidation on old entries.`
- `2026-04-10: Tried switching to unified diff patches — reverted, SEARCH/REPLACE is more reliable.`
- `2026-04-08: Plugin install works via marketplace. Blocked on: Stop hook noise during plugin dev.`

Keep the list ordered newest-first. Cap at ~10 entries — the dream protocol consolidates older ones.

## When NOT to Save

- Information already in CLAUDE.md files — no duplication
- **Per-commit changelog entries** ("Fixed null ptr in foo.py", "Added field X to Y") —
  git log owns these. **Do NOT confuse with Recent Sessions entries, which ARE required:**
    - SAVE (Recent Sessions, high-level session state):
      `- 2026-04-16: Replaced bare "memory" with "project memory" across plugin+docs.`
    - DO NOT SAVE (changelog, per-commit code-change list):
      `Fixed null ptr in foo.py; added field X to Y.`
- Completed task details in "Current Work" — extract the lesson, delete the task info
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
- Creating a project memory file for a new project
- The file needs complete reorganization
- `update_project_memory` fails (search text not found or not unique)

## Rules

- **English only** — all project memory content must be in English
- **No sensitive data** — never store passwords, tokens, API keys, emails
- **Update, don't duplicate** — before adding, check if similar info already exists
- **Current knowledge only** — the project memory reflects what is true NOW, not history
- **Fix stale project memory immediately, without asking** — if anything in the conversation
  reveals that a project memory entry is outdated or wrong (a renamed file, a changed version,
  a reversed decision, a superseded pattern), correct it right away via
  `update_project_memory`. Do NOT ask for permission, do NOT defer to end of session.
  Stale project memory silently poisons future sessions — treat fixing it as part of the
  current task, not a separate chore.
- **Be concise but complete** — optimize for LLM readability, every line should earn its place
- **Do NOT ask the user for confirmation** before saving or updating project memory — just
  call the MCP tool. The user has already opted in by installing this plugin; pausing to
  ask ("Shall I save this?", "Want me to update project memory?") is friction, not safety.
  Save silently and mention it briefly afterward if relevant.

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

## Recent Sessions
[Newest-first, 1-2 lines per entry, ~10 entries max — dream consolidates older ones]
```
