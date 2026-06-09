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
2. **Consolidate** by calling the `Agent` tool with `subagent_type: "project-mem:dream-consolidator"` (the fully-qualified `plugin:agent` name — the bare `dream-consolidator` is NOT found and the call fails). Pass the inputs in the `prompt`. **Do NOT pass a `model:` parameter** — see precedence note in *Important*.

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

The consolidator subagent picks its writeback mode by the scale of change (see *Important*): an aggressive shrink on a bloated file (every hook-triggered dream — the file crossed the ~50KB trigger threshold) goes back as ONE `set_project_memory` full rewrite of the shrunk file; minor steady-state nudges on an already-healthy file go back as a series of `update_project_memory` SEARCH/REPLACE patches. Either way each write carries `bump_last_dream=True`, which refreshes the `last_dream:` YAML frontmatter. You do not need a post-step here.

## Important

- **Sonnet is pinned via the agent definition's `model: claude-sonnet-4-6` frontmatter (full model ID, not the `sonnet` alias).** Claude Code's documented model resolution order is: (1) `CLAUDE_CODE_SUBAGENT_MODEL` env var, (2) per-invocation `model` parameter, (3) the agent definition's `model` frontmatter, (4) the parent's model. If you pass `model:` in the Agent call, it wins over the frontmatter and may downgrade or upgrade away from Sonnet — so **omit it**.
- **Why full model ID, not the alias:** there is a known Claude Code bug ([anthropics/claude-code#43869](https://github.com/anthropics/claude-code/issues/43869), open as of 2026-05) where model aliases (`sonnet`, `opus`, `haiku`) in *any* of the four mechanisms above are passed through unresolved into the subagent subprocess, fail to parse, and silently fall back to a hardcoded Opus config. Full model IDs survive the unresolved pass-through and route correctly. This is why earlier versions of this plugin (which used `model: sonnet`) still ran consolidation on Opus despite the frontmatter — slow and expensive. Switching to `model: claude-sonnet-4-6` is the active workaround.
- **Effort is pinned to `low` via the agent's `effort: low` frontmatter (since 0.4.21).** Without it, the subagent inherits the *session* effort level — if the main chat runs at high/`max`, the consolidator inherits that and spends large adaptive-reasoning budgets, which is slow. Consolidation is mostly mechanical (merge near-duplicates, tighten wording, drop stale entries), so `low` is enough; the only reasoning-sensitive part is keep-vs-drop judgement. If consolidation quality visibly degrades, bump to `medium`. Resolution order for `effort`: subagent frontmatter > session (`CLAUDE_CODE_EFFORT_LEVEL` env / `effortLevel` in settings.json). The Anthropic API `thinking.budget_tokens` knob is NOT exposed by Claude Code — `effort` is the only lever.
- **Writeback mode is chosen by the scale of change.** The dominant cost of a dream is output-token generation, and the two write tools have opposite cost curves: a patch costs ≈ Σ(SEARCH+REPLACE) (cheap only when little changes); a full rewrite costs ≈ the size of the NEW file (cheap when the file shrinks a lot, since you emit only the small result). So: a bloated file undergoing an aggressive ~30% shrink (every hook-triggered dream) → ONE `set_project_memory` rewrite (cheaper *and* more effective than dozens of patches that each must quote the bulky old text); an already-healthy file getting minor nudges → incremental `update_project_memory` patches. The earlier "patches are the unconditional default" stance (0.4.19) was right only for steady-state maintenance — it made aggressive consolidations both timid and expensive on large files (e.g. PyneSys 180KB→170KB), which is why the rule is now scale-dependent.
- **Every consolidator write carries `bump_last_dream=True`** (idempotent). Bumping on every patch — not only the last — keeps `last_dream:` fresh across the multi-write run, so the PostToolUse `check_dream.py` never sees a stale timestamp after an intermediate write and fires a spurious DREAM_NEEDED mid-consolidation. The `bump_last_dream` MCP parameter (added 0.4.7, works on both MCP write tools) replaced the separate `update_dream_timestamp.py` Bash call removed in 0.4.7.
- No backup is written. If you need to recover the pre-dream state, use git (`git show HEAD:MEMORY.md`, `git checkout HEAD -- MEMORY.md`). If the project isn't in git, that's the user's accepted risk.
