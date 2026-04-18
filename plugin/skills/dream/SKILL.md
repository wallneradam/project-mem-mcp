---
name: dream
description: >
  Consolidate and reorganize project memory (MEMORY.md) using a sonnet subagent.
  When triggered by the DREAM_NEEDED hook message, run AUTOMATICALLY without asking
  the user. Do NOT ask for confirmation — just execute the consolidation protocol.
  Can also be triggered manually via /dream.
tools: Agent, Read, Glob, Bash
---

# Dream — Project Memory Consolidation

When this skill is triggered, spawn a **sonnet** Agent subagent to consolidate the project's MEMORY.md.

## Protocol

1. **Read** the current MEMORY.md content
2. **Read** all CLAUDE.md files in the project (`**/CLAUDE.md`)
3. **Consolidate** by spawning a sonnet Agent with the prompt below.
   Substitute `{TODAY}` with today's date in `YYYY-MM-DD` format before sending.
4. **Update timestamp**: run `uv run --no-project --quiet python ${CLAUDE_PLUGIN_ROOT}/scripts/update_dream_timestamp.py` via Bash. This writes `last_dream: <current UTC ISO 8601>` into the YAML frontmatter at the top of `MEMORY.md` (creates the frontmatter block if absent, updates in place otherwise).

## Sonnet Agent Prompt

Spawn with `model: "sonnet"` and provide:

```
You are consolidating a project's MEMORY.md file. Your goal is to make it cleaner,
better organized, and optimized for LLM consumption.

## Current MEMORY.md:
{paste full content}

## Project CLAUDE.md files:
{paste all CLAUDE.md contents with their paths}

## Rules:
1. REMOVE anything that duplicates information already in CLAUDE.md files
2. REMOVE completed task details from Current Work (extract any lesson first)
3. RESTRUCTURE: group related information logically
4. KEEP all unique insights, gotchas, architecture decisions, and current work context
5. FORMAT for LLM readability: clear headers, concise bullet points, no fluff
6. WRITE in English only
7. Do NOT compress below the current size artificially — organize, don't summarize away detail
8. Preserve the factual content — you are reorganizing, not rewriting

## Recent Sessions consolidation

Today's date is {TODAY}. Apply these rules to the `## Recent Sessions` section:

- **≤ 7 days old**: keep verbatim as individual entries (newest-first).
- **7–30 days old**: merge into weekly summary bullets
  (e.g. `- 2026-03-week-2: <2-3 sentence themed summary of that week's work>`).
  Drop granular details; keep decisions and state transitions.
- **> 30 days old**: remove from Recent Sessions entirely. BEFORE removing, scan for
  any durable lesson (gotcha, convention, decision) and promote it to
  `## Lessons Learned` or the appropriate section if not already there.
- Cap the section at ~10 bullets total after consolidation.

Write back the consolidated MEMORY.md using the set_project_memory MCP tool.
```

## Important

- The sonnet agent writes back via `set_project_memory` to maintain path validation
- Step 4 runs AFTER the sonnet agent finishes its `set_project_memory` write. The `update_dream_timestamp.py` script rewrites the file in place with the new frontmatter — do not inline-edit the timestamp in the prompt or rely on the sonnet agent to preserve it
- No backup is written. If you need to recover the pre-dream state, use git (`git show HEAD:MEMORY.md`, `git checkout HEAD -- MEMORY.md`). If the project isn't in git, that's the user's accepted risk
