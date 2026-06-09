# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

An MCP server + Claude Code plugin that manages persistent project memory files (`MEMORY.md`) for AI agents. Built with FastMCP 3.x and Python 3.11+.

The MCP server lives in `src/project_mem_mcp/server.py`. The plugin layer adds auto-read hooks and a dream (consolidation) system.

## Development Commands

```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -e .

# Run the server locally
project-mem-mcp
project-mem-mcp --allowed-dir /path/to/projects

# Run without installation (via uvx)
uvx project-mem-mcp

# Plugin installation (in Claude Code)
# /plugin marketplace add /path/to/project-mem-mcp
# /plugin install project-mem@cc-plugin-project-mem
```

There are no tests or linting configured in this project.

## Architecture

### MCP Server (`src/project_mem_mcp/server.py`)

Four MCP tools:

| Tool                    | Purpose                                            |
| ----------------------- | -------------------------------------------------- |
| `get_project_memory`    | Read `MEMORY.md` — full file, `head_only` TOC, or `offset/limit` chunk |
| `search_project_memory` | Substring search; returns matching lines with 1-indexed line numbers |
| `set_project_memory`    | Overwrite the entire `MEMORY.md`                   |
| `update_project_memory` | Apply a single SEARCH/REPLACE patch to `MEMORY.md` |

**Security model:** Project paths are validated against `--allowed-dir` arguments. If none are provided, the server defaults to the current working directory.

**Patch format:** `update_project_memory` uses a custom SEARCH/REPLACE block format (not unified diff). The search text must appear exactly once in the file; non-unique matches raise `ValueError`. Only one block per call is allowed.

**Read size guard:** `get_project_memory` with no `offset`/`limit`/`head_only` raises `ValueError` when the estimated token count (`chars/4`) exceeds `MAX_FULL_READ_TOKENS` (20000, below Claude Code's 25K tool-result cap). Callers fall back to `head_only=True` (returns size + heading TOC with 1-indexed line ranges) and then chunk via `offset`/`limit`. Explicit `offset`/`limit` is treated as informed consent and bypasses the guard.

**Concurrent-write safety (since pyproject 0.4.10).** Each session runs its own MCP server process, so two sessions writing the same `MEMORY.md` are two OS processes with no shared lock. Both write tools combine two independent mechanisms:

- **Atomic write** (`_atomic_write`): the new content is written to a temp file in the *same directory* (so `os.replace` is a same-filesystem atomic rename), `fsync`'d, then `os.replace`'d over `MEMORY.md`. A concurrent reader (incl. the `check_dream.py` hook, external tools, other MCP clients) or a crash mid-write never sees a half-written file — only the complete old or complete new one. This needs no lock and protects *every* reader.
- **File lock** (`_memory_lock`): an exclusive advisory lock held across the read-modify-write critical section, so concurrent writers serialize instead of silently losing the earlier edit (last-writer-wins / lost update). Stdlib-only cross-platform shim — `fcntl.flock` on POSIX, `msvcrt.locking` on Windows (no `filelock` dependency). The lock file is a stable, never-renamed file in `tempfile.gettempdir()` keyed by a SHA-1 of the resolved `MEMORY.md` path (flock binds to an inode, so it must not be the file being atomically replaced; temp-dir keeps the repo clean). **Fail-open:** if the lock can't be acquired (permission/odd FS) the write proceeds unlocked — losing the write is worse than a rare race, and atomic replacement still prevents corruption.

The two are orthogonal and both required: the lock stops writer-vs-writer lost updates; atomic write stops torn reads and crash-truncation (which the lock cannot, since readers don't take it and a crash drops the lock with the file already truncated). This lives in the MCP layer (not the plugin) so it also covers cross-client races (e.g. Claude in one window, Codex in another, same repo). It does **not** replace the dream single-dreamer lock in `check_dream.py`: that prevents two *consolidations* from starting; this prevents two *file writes* from clobbering each other.

### Plugin Layer (`plugin/`)

| Component                        | Purpose                                              |
| -------------------------------- | ---------------------------------------------------- |
| `.mcp.json`                      | Registers MCP server via `uvx` for plugin installs    |
| `hooks/hooks.json`               | Hook definitions (auto-read, dream trigger)           |
| `scripts/auto_read.py`           | Emits RULES + PRELOAD_DIRECTIVE on first prompt per session; agent then loads MEMORY.md via `get_project_memory` |
| `scripts/continuous_save_prime.py` | SessionStart hook — injects `additionalContext` keeping inline save-awareness active for the whole session |
| `scripts/check_dream.py`         | Checks if dream consolidation is needed after write   |
| `skills/project-memory/SKILL.md` | Auto-trigger: when and how to save to project memory  |
| `skills/dream/SKILL.md`          | Dream consolidation protocol — invokes the named subagent below |
| `agents/dream-consolidator.md`   | Named subagent definition pinned via frontmatter: `model: claude-sonnet-4-6` (full ID) + `effort: low` (see Dream section); invoked via `subagent_type: "project-mem:dream-consolidator"` (fully-qualified — bare name fails) |
| `commands/dream.md`              | `/dream` slash command for manual trigger             |

**Auto-read:** UserPromptSubmit hook emits RULES + PRELOAD_DIRECTIVE on the first prompt per session (tracked via `session_id` state file). The directive instructs the agent to call `ToolSearch` to preload the three MCP tool schemas and then `get_project_memory` to load MEMORY.md — the content itself is not inlined in the hook output because the harness truncates large stdouts. The directive also tells the agent to ignore the `last_dream:` YAML frontmatter returned in the tool result.

**Continuous save-awareness:** SessionStart hook emits `hookSpecificOutput.additionalContext` (pattern copied from Anthropic's explanatory-output-style plugin) that primes the agent to call `update_project_memory` inline whenever non-trivial project knowledge surfaces, not only at prompt-time. Complements `auto_read.py`: UserPromptSubmit installs rules + loads MEMORY.md; SessionStart keeps the save impulse active throughout the session.

**Dream:** PostToolUse hook triggers after project memory writes (regex matcher: `.*set_project_memory|.*update_project_memory`). Conditions: file > 50KB AND last dream > 24h ago AND no other session is already dreaming on this project (single-dreamer lock — see below). The dream skill invokes the `dream-consolidator` named subagent (Agent tool with `subagent_type: "project-mem:dream-consolidator"` — the fully-qualified `plugin:agent` name; the bare `dream-consolidator` is not found and fails — **no `model:` parameter**), which is pinned to Sonnet via its definition's `model: claude-sonnet-4-6` frontmatter (full model ID — see next paragraph). Model resolution order in Claude Code per docs: env var `CLAUDE_CODE_SUBAGENT_MODEL` → per-invocation `model:` parameter → agent definition's frontmatter → parent's model. Earlier versions relied on a prose "spawn with model: sonnet" instruction; that was unreliable and frequently inherited Opus from the parent.

**Effort level — pinned to `low` (since 0.4.21).** The consolidator carries `effort: low` in its frontmatter. Without it the subagent inherits the *session* effort level, so a main chat running at high/`max` makes the consolidator spend large adaptive-reasoning budgets and run slowly. Consolidation is mostly mechanical (merge, tighten, drop stale), so `low` suffices; the only reasoning-sensitive part is keep-vs-drop judgement — bump to `medium` if quality degrades. `effort` resolution order: subagent frontmatter > session (`CLAUDE_CODE_EFFORT_LEVEL` env / `effortLevel` in settings.json). The API `thinking.budget_tokens` knob is not exposed by Claude Code; `effort` is the only lever.

**Known Claude Code bug — model aliases silently fall back to Opus** ([anthropics/claude-code#43869](https://github.com/anthropics/claude-code/issues/43869), open as of 2026-05). All five documented subagent-model mechanisms (alias in frontmatter, alias as per-invocation param, alias or full ID via `CLAUDE_CODE_SUBAGENT_MODEL`, settings.json env injection) are silently ignored — the subagent inherits the parent's model. Source-level investigation in the issue traced this to `resolveTeammateModel()` (`src/tools/shared/spawnMultiAgent.ts`) passing aliases through unresolved; the spawned subprocess receives e.g. `--model sonnet` (unparseable), fails to parse, and falls back to a hardcoded Opus config. **Workaround:** use a *full* model ID in frontmatter (e.g. `claude-sonnet-4-6` instead of `sonnet`) — the full ID survives the unparsed-pass-through and the subprocess accepts it. This is why `dream-consolidator.md` carries `model: claude-sonnet-4-6`, not `model: sonnet`. When this bug is fixed upstream, the value can move back to the `sonnet` alias.

**Aggressive consolidation — size target + dormant-topic tier + scale-dependent writeback (since 0.4.23).** Earlier dreams under-compressed (PyneSys 180KB→170KB) because three things pushed the consolidator toward timid, cosmetic edits. All three were addressed in `dream-consolidator.md`:

- **Explicit shrink target, not "no-growth".** The old rule was "keep the file roughly the same size or smaller" — a hold-flat mandate, so a 170KB file read as steady state, not failure. Now: a file in the healthy range (≲ ~40KB) holds flat; a bloated file (> ~50KB, true of *every* hook-triggered dream since that is the trigger threshold) must be cut by **at least ~30% per pass**, repeated over successive dreams until it settles into the healthy range. The consolidator verifies it hit the target before finishing.
- **Dormant-topic compression (where the bulk of the win is).** The age tiers used to govern only `## Recent Sessions`; topic blocks (a shipped feature/subproject/migration) were age-blind and stayed verbatim forever. Now a topic is **dormant** if not mentioned in Recent Sessions within ~30 days AND complete per code/CLAUDE.md → collapse to one paragraph/line keeping only the durable gotcha + *why* (drop version-by-version history and anything reconstructible from code/git/CLAUDE.md; drop entirely if no gotcha survives). Active work threads (recent, or open/blocked) stay detailed. User-chosen heuristic: last-mention age, not an explicit `[DONE]` marker.
- **Writeback mode is now scale-dependent, not patch-by-default.** The two write tools have opposite cost curves: a `update_project_memory` patch costs ≈ Σ(SEARCH+REPLACE) — cheap only when little changes; a `set_project_memory` full rewrite costs ≈ size of the NEW file — cheap when the file shrinks a lot, since only the small result is emitted. The 0.4.19 "patches are the unconditional default" was correct ONLY for steady-state maintenance; on an aggressive shrink it is *pessimal*, because every SEARCH must quote the bulky old text being deleted (a 180KB→50KB shrink via patches ≈ 4-5× the same shrink via one rewrite). New rule: **bloated file + ~30% cut → ONE `set_project_memory` rewrite** (the expected path for triggered dreams); already-healthy file + minor nudges → incremental patches. `set_project_memory` reverts from "rare fallback" to "primary path for triggered dreams".

Each consolidator write still carries `bump_last_dream=True` (idempotent). For the patch path, bumping on *every* patch (not just the last) keeps `last_dream:` fresh across the multi-write run so the PostToolUse `check_dream.py` does not see a stale timestamp mid-consolidation and fire a spurious DREAM_NEEDED. The full-rewrite path is a single write, so this is moot there.

**Single-dreamer lock (since 0.4.22).** The `last_dream:` 24h gate is time-of-check-only: it closes the duplicate-dream window only *after* a dream's first `bump_last_dream` write. If two sessions write to the same `MEMORY.md` near-simultaneously, both see `last_dream:` > 24h (neither has bumped yet) and both emit DREAM_NEEDED → two consolidators race each other's SEARCH/REPLACE patches. `check_dream.py:acquire_dream_lock` is the mutex — a cross-platform, self-expiring lease, acquired as the *last* gate in `main()` (after the size and 24h checks, so no lock file is created when no dream is due):

- **Location:** per-project lock file in `tempfile.gettempdir()`, keyed by a SHA-1 of the resolved project path (same temp-dir convention as `auto_read.py`'s per-session state file). Two sessions on the same project contend for one file; the repo is never touched (no `.gitignore` entry needed) and the OS reclaims the temp dir.
- **Acquire:** atomic `os.open(O_CREAT|O_EXCL)` — exactly one of N racing sessions wins, the losers exit silently (verified with a 12-process race). The lock payload is `<epoch>\n<pid>\n`.
- **Stale takeover:** if the lock exists but its epoch is older than `DREAM_LOCK_TTL` (1800s) or is unparseable, it is taken over atomically via `os.replace()` of a unique temp file, then a read-back PID verify (the loser of a takeover race sees the other's token and yields).
- **Release (happy path):** the lock only needs to live until the dream's first bump. That bump refreshes `last_dream:` and re-fires this hook (PostToolUse fires for the consolidator subagent's writes); that run sees a fresh `last_dream:` and calls `release_dream_lock` (also on a sub-threshold file). From then on the 24h gate is the active guard, so deleting the lock — regardless of holder — cannot let a second dream start. Release is driven by observable on-disk state in the hook, never by asking an LLM subagent to unlock itself (a missed final step would leak the lock).
- **TTL = crash backstop only:** if a dream dies *before* its first bump, no fresh-`last_dream:` run fires to release the lock, so the lease expires it after `DREAM_LOCK_TTL`.
- **Fail-open:** any IO error during acquire/takeover falls back to the old always-trigger behavior — a rare concurrent dream is the lesser evil versus silently suppressing dreams (which would let `MEMORY.md` grow unbounded).
- Manual `/dream` does not go through this hook, so the lock never gates an on-demand consolidation.

The `last_dream:` frontmatter rewrite is atomic with the writeback via the `bump_last_dream=True` MCP parameter (added in 0.4.7; works on both `set_project_memory` and `update_project_memory`). Earlier versions used a separate `update_dream_timestamp.py` Bash call owned by the subagent; that script was removed in 0.4.7. The MCP layer owns `last_dream:` entirely: it strips any caller-written value and splices the genuine one back, and `set_project_memory` preserves an existing YAML frontmatter when the caller's payload doesn't include one — callers can pass plain markdown without knowing about the frontmatter convention.

## Key Constraints

- Project memory files must be written in English only
- FastMCP dependency: `>=3.2.0, <4.0.0`
- Entry point is `project_mem_mcp.server:main` (defined in `pyproject.toml`)
