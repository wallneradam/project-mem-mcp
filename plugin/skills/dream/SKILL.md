---
name: dream
description: >
  Consolidate and reorganize project memory (MEMORY.md) by invoking the
  `dream-consolidator` named subagent (Sonnet, pinned via the agent's
  `model:` frontmatter — see Important section below). When triggered by
  the DREAM_NEEDED hook message, run AUTOMATICALLY without asking the user.
  Do NOT ask for confirmation — just execute the consolidation protocol.
  Can also be triggered manually via /dream.
tools: Agent, Read, Glob, Bash
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

4. **Update timestamp**: run `uv run --no-project --quiet python ${CLAUDE_PLUGIN_ROOT}/scripts/update_dream_timestamp.py "$CLAUDE_PROJECT_DIR"` via Bash. The first argument is the project root (passed explicitly because the Bash tool may run with an empty `CLAUDE_PROJECT_DIR`; if the argument is empty the script falls back to the env var, then to `cwd`). This writes `last_dream: <current UTC ISO 8601>` into the YAML frontmatter at the top of `MEMORY.md` (creates the frontmatter block if absent, updates in place otherwise). Verify success: stdout prints `update_dream_timestamp: set last_dream=<ts> in <path>`; non-zero exit indicates failure (logged to stderr).

## Important

- **Sonnet is pinned via the agent definition's `model: sonnet` frontmatter.** Claude Code's model resolution order is: (1) `CLAUDE_CODE_SUBAGENT_MODEL` env var, (2) per-invocation `model` parameter, (3) the agent definition's `model` frontmatter, (4) the parent's model. If you pass `model:` in the Agent call, it wins over the frontmatter and may downgrade or upgrade away from Sonnet — so **omit it**. Earlier versions of this skill relied on a prose instruction telling the parent to "spawn with model: sonnet"; that was unreliable and frequently silently inherited the parent (Opus), making consolidation slow and expensive. The named-agent + frontmatter approach is the fix.
- The consolidator writes back via `set_project_memory` to maintain path validation. Step 4 runs AFTER the consolidator finishes its write. The `update_dream_timestamp.py` script rewrites the file in place with the new frontmatter — do not inline-edit the timestamp in the prompt or rely on the consolidator to preserve it.
- No backup is written. If you need to recover the pre-dream state, use git (`git show HEAD:MEMORY.md`, `git checkout HEAD -- MEMORY.md`). If the project isn't in git, that's the user's accepted risk.
