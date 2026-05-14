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

When this skill is triggered, invoke the **`dream-consolidator`** named subagent (defined in `plugin/agents/dream-consolidator.md`, pinned to `model: claude-sonnet-4-6`) to consolidate the project's MEMORY.md.

## Protocol

1. **Read** all CLAUDE.md files in the project (`**/CLAUDE.md`).
2. **Consolidate** by calling the `Agent` tool with `subagent_type: "dream-consolidator"`. Pass the inputs in the `prompt`. **Do NOT pass a `model:` parameter** — see precedence note in *Important*.

   The `prompt` must contain, in this order:

   ```
   Today's date: {TODAY}
   Project path: {CLAUDE_PROJECT_DIR}

   ## Project CLAUDE.md files:

   ### {path/to/CLAUDE.md}
   {content}

   ### {path/to/another/CLAUDE.md}
   {content}
   ```

   Substitute `{TODAY}` with today's date in `YYYY-MM-DD` format and `{CLAUDE_PROJECT_DIR}` with the absolute project root before sending. **Do NOT inline MEMORY.md** — the subagent loads it itself via `get_project_memory` (with chunked reads if large; see its Read protocol). The agent's body (its system prompt) already contains the consolidation rules and Recent Sessions retention policy — do not duplicate them in the user prompt.

The consolidator subagent writes back via `set_project_memory(..., bump_last_dream=True)`, which atomically applies the new content and refreshes the `last_dream:` YAML frontmatter. You do not need a post-step here.

## Important

- **Sonnet is pinned via the agent definition's `model: claude-sonnet-4-6` frontmatter (full model ID, not the `sonnet` alias).** Claude Code's documented model resolution order is: (1) `CLAUDE_CODE_SUBAGENT_MODEL` env var, (2) per-invocation `model` parameter, (3) the agent definition's `model` frontmatter, (4) the parent's model. If you pass `model:` in the Agent call, it wins over the frontmatter and may downgrade or upgrade away from Sonnet — so **omit it**.
- **Why full model ID, not the alias:** there is a known Claude Code bug ([anthropics/claude-code#43869](https://github.com/anthropics/claude-code/issues/43869), open as of 2026-05) where model aliases (`sonnet`, `opus`, `haiku`) in *any* of the four mechanisms above are passed through unresolved into the subagent subprocess, fail to parse, and silently fall back to a hardcoded Opus config. Full model IDs survive the unresolved pass-through and route correctly. This is why earlier versions of this plugin (which used `model: sonnet`) still ran consolidation on Opus despite the frontmatter — slow and expensive. Switching to `model: claude-sonnet-4-6` is the active workaround.
- The consolidator writes back via `set_project_memory(..., bump_last_dream=True)`, which keeps both the path-validation invariant and the frontmatter refresh atomic. Earlier versions used a separate `update_dream_timestamp.py` Bash call; that script was removed in 0.4.7 — the `bump_last_dream` MCP parameter replaces it.
- No backup is written. If you need to recover the pre-dream state, use git (`git show HEAD:MEMORY.md`, `git checkout HEAD -- MEMORY.md`). If the project isn't in git, that's the user's accepted risk.
