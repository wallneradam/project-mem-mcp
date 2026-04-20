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

## Guiding principle

**Default to KEEP.** Prefer removing only information that is genuinely
outdated, superseded, duplicated, or contradicted by current state. When in
doubt, keep. Compression means *tighter wording*, not *less content*. It is
better to leave in something marginally useful than to drop something that
might matter later — the file has plenty of headroom (50KB threshold).

## Rules:
1. REMOVE only information that is clearly stale: renamed files no longer at
   that path, decisions that have since been reversed, patterns that were
   replaced, facts contradicted by the current CLAUDE.md or code state.
2. REMOVE content that literally duplicates CLAUDE.md (same fact, same phrasing
   scope). If MEMORY.md adds nuance, context, or the *why* behind a CLAUDE.md
   statement, KEEP it — CLAUDE.md is terse by design.
3. REMOVE completed task details from Current Work, but extract any durable
   lesson first and promote it to `## Lessons Learned`.
4. RESTRUCTURE: group related information logically; merge near-duplicates
   into a single clearer entry rather than deleting either.
5. KEEP all unique insights, gotchas, architecture decisions, historical
   rationale ("we chose X because Y"), and current work context. If unsure
   whether an item is still relevant, KEEP it.
6. TIGHTEN wording where verbose, but do NOT summarize away detail — a
   reader should still be able to understand *why* a decision was made.
7. FORMAT for LLM readability: clear headers, concise bullet points, no fluff.
8. WRITE in English only.
9. Preserve the factual content — you are reorganizing and pruning stale
   entries, not rewriting or compressing for its own sake.

## Recent Sessions consolidation

Today's date is {TODAY}. Apply these rules to the `## Recent Sessions` section:

- **≤ 14 days old**: keep verbatim as individual entries (newest-first).
- **14–60 days old**: keep as individual entries, but tighten wording where
  verbose. Only merge entries into a weekly summary if they are clearly
  redundant or cover the same narrow topic.
- **> 60 days old**: consider merging into a themed summary bullet
  (e.g. `- 2026-02: <2-3 sentence themed summary>`) only if the individual
  entries have lost their day-to-day relevance. BEFORE dropping any detail,
  scan for durable lessons (gotcha, convention, decision) and promote them
  to `## Lessons Learned` or the appropriate section if not already there.
- Cap the section at ~20 bullets total after consolidation. Only trim if
  over the cap — do not trim a shorter section just to tidy it up.

Write back the consolidated MEMORY.md using the set_project_memory MCP tool.
```

## Important

- The sonnet agent writes back via `set_project_memory` to maintain path validation
- Step 4 runs AFTER the sonnet agent finishes its `set_project_memory` write. The `update_dream_timestamp.py` script rewrites the file in place with the new frontmatter — do not inline-edit the timestamp in the prompt or rely on the sonnet agent to preserve it
- No backup is written. If you need to recover the pre-dream state, use git (`git show HEAD:MEMORY.md`, `git checkout HEAD -- MEMORY.md`). If the project isn't in git, that's the user's accepted risk
