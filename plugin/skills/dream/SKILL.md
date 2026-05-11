---
name: dream
description: >
  Consolidate and reorganize project memory (MEMORY.md) by invoking the
  `dream-consolidator` named subagent (Sonnet, pinned via the agent's
  `model:` frontmatter — see Important section below). When triggered by
  the DREAM_NEEDED hook message, run AUTOMATICALLY without asking the user.
  Do NOT ask for confirmation — just execute the consolidation protocol.
  Can also be triggered manually via /dream.
tools: Agent, Read, Glob
---

# Dream — Project Memory Consolidation

When this skill is triggered, invoke the **`dream-consolidator`** named subagent (defined in `plugin/agents/dream-consolidator.md`, pinned to `model: sonnet`) to consolidate the project's MEMORY.md.

## Protocol

1. **Read** the current MEMORY.md content.
2. **Read** all CLAUDE.md files in the project (`**/CLAUDE.md`).
3. **Consolidate** by calling the `Agent` tool with `subagent_type: "dream-consolidator"`. Pass the inputs in the `prompt`. **Do NOT pass a `model:` parameter** — see precedence note in *Important*.

   The `prompt` must contain, in this order:

   ```
   Today's date: {TODAY}
   Project path: {CLAUDE_PROJECT_DIR}

   ## Current MEMORY.md:

   {paste full MEMORY.md content verbatim}

   ## Project CLAUDE.md files:

   ### {path/to/CLAUDE.md}
   {content}

   ### {path/to/another/CLAUDE.md}
   {content}
   ```

   Substitute `{TODAY}` with today's date in `YYYY-MM-DD` format and `{CLAUDE_PROJECT_DIR}` with the absolute project root before sending. The agent's body (its system prompt) already contains the consolidation rules and Recent Sessions retention policy — do not duplicate them in the user prompt.

The consolidator subagent updates the `last_dream:` timestamp itself as part of its protocol (it runs `update_dream_timestamp.py` after `set_project_memory`). You do not need a post-step here.

## Important

- **Sonnet is pinned via the agent definition's `model: sonnet` frontmatter.** Claude Code's model resolution order is: (1) `CLAUDE_CODE_SUBAGENT_MODEL` env var, (2) per-invocation `model` parameter, (3) the agent definition's `model` frontmatter, (4) the parent's model. If you pass `model:` in the Agent call, it wins over the frontmatter and may downgrade or upgrade away from Sonnet — so **omit it**. Earlier versions of this skill relied on a prose instruction telling the parent to "spawn with model: sonnet"; that was unreliable and frequently silently inherited the parent (Opus), making consolidation slow and expensive. The named-agent + frontmatter approach is the fix.
- The consolidator writes back via `set_project_memory` to maintain path validation, then rewrites the frontmatter via `update_dream_timestamp.py`. The timestamp step is owned by the subagent so that direct invocation (without this skill) still leaves a correct `last_dream:` behind — earlier versions kept the post-step here and a direct subagent call silently dropped the timestamp.
- No backup is written. If you need to recover the pre-dream state, use git (`git show HEAD:MEMORY.md`, `git checkout HEAD -- MEMORY.md`). If the project isn't in git, that's the user's accepted risk.
