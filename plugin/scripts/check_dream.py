"""Check if dream consolidation is needed after a project memory write.

Conditions: file > 50KB AND last dream was > 24h ago (or never) AND no other
session is already dreaming on this project (see the lock below).
Exit 0 = silent (no dream needed), exit 2 + stderr = signal to Claude.

The last-dream timestamp lives as `last_dream: <ISO 8601 UTC>` inside the
YAML frontmatter at the top of MEMORY.md (refreshed atomically by the
`set_project_memory(..., bump_last_dream=True)` MCP call at the end of each
dream run). Missing or unparseable → treated as "never".

## Single-dreamer lock

If two sessions write to the same MEMORY.md at nearly the same moment, both
PostToolUse hooks fire this script; both see a `last_dream:` older than 24h
(the running dream hasn't bumped it yet) and both would emit DREAM_NEEDED →
two consolidators run concurrently on one file, racing each other's
SEARCH/REPLACE patches. `last_dream:` alone is a time-of-check gate, not a
mutex: it only closes the window *after* a dream's first write.

`acquire_dream_lock` closes the window. It is a cross-platform, self-expiring
lease:
- Lives in `tempfile.gettempdir()`, keyed by a hash of the resolved project
  path (same temp-dir convention as `auto_read.py`'s per-session state file).
  Two sessions on the same project contend for the same file; the repo is
  never touched (no .gitignore needed), and the OS reclaims the temp dir.
- Fast path: an atomic `O_CREAT|O_EXCL` create — exactly one of N racing
  sessions wins; the losers stay silent. This is the common case.
- A held lock self-expires after `DREAM_LOCK_TTL`, so a crashed or interrupted
  dream cannot block consolidation forever. The 24h `last_dream:` gate is the
  second backstop once a dream has actually written.
- Fail-open: any IO error acquiring the lock falls back to the old
  always-trigger behavior — a rare concurrent dream is the lesser evil versus
  silently suppressing dreams (which would let MEMORY.md grow unbounded).

Release (happy path): the race window only needs the lock from "DREAM_NEEDED
emitted" until "the dream's first `bump_last_dream` write". That write atomically
refreshes `last_dream:` and triggers this hook again (PostToolUse fires for the
consolidator subagent's writes too); that run sees a fresh `last_dream:`, knows a
dream has progressed, and deletes the lock — at which point the 24h gate is the
active guard and the lock is redundant. A run that finds the file shrunk below
threshold releases too. We never ask an LLM subagent to unlock itself (a missed
final step would leak the lock); release is driven by observable on-disk state in
the hook.

TTL is purely the crash backstop: if a dream dies *before* its first bump, no
fresh-`last_dream:` run ever fires to release the lock, so the lease expires it
after `DREAM_LOCK_TTL`. Manual `/dream` does not go through this hook, so the lock
never blocks an on-demand consolidation.

Residual race: during a *stale takeover* (only after a crashed dream), two
sessions could in principle both win. The window is microseconds and the
worst case is the pre-existing behavior (two concurrent dreams) — never worse,
usually better.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

SIZE_THRESHOLD = 51_200  # 50 KB
DREAM_INTERVAL = 86_400  # 24 hours in seconds
DREAM_LOCK_TTL = 1_800  # 30 min — long enough for a worst-case consolidation,
# short enough that a crashed dream's lock self-expires.

LAST_DREAM_RE = re.compile(r"^\s*last_dream\s*:\s*(\S+)")


def read_last_dream(memory_file: Path) -> int:
    """Parse YAML frontmatter from top of MEMORY.md; return last_dream as epoch (0 on any miss)."""
    try:
        with open(memory_file, "r", encoding="utf-8") as f:
            head = f.read(2048)
    except OSError:
        return 0

    lines = head.splitlines()
    if not lines or lines[0] != "---":
        return 0

    for i in range(1, len(lines)):
        if lines[i] == "---":
            return 0
        m = LAST_DREAM_RE.match(lines[i])
        if m:
            val = m.group(1)
            try:
                dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                return int(dt.timestamp())
            except ValueError:
                return 0
    return 0


def _lock_path(project_dir: str) -> Path:
    """Per-project lock file in the OS temp dir (cross-platform, repo-clean)."""
    key = hashlib.sha1(str(Path(project_dir).resolve()).encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"project-mem-dream-{key}.lock"


def _read_lock_epoch(lock: Path) -> int | None:
    """First line of the lock holds the acquire epoch; None if missing/unparseable."""
    try:
        first = lock.read_text(encoding="utf-8").splitlines()[0]
        return int(first.strip())
    except (OSError, IndexError, ValueError):
        return None


def _read_lock_owner(lock: Path) -> str | None:
    """Second line holds the owner token (PID); None if missing/unreadable."""
    try:
        lines = lock.read_text(encoding="utf-8").splitlines()
        return lines[1].strip() if len(lines) > 1 else None
    except OSError:
        return None


def acquire_dream_lock(project_dir: str) -> bool:
    """Return True if this caller may emit DREAM_NEEDED, False if a live dream holds the lock.

    See the module docstring for the lease/fail-open design rationale.
    """
    lock = _lock_path(project_dir)
    now = int(time.time())
    owner = str(os.getpid())
    payload = f"{now}\n{owner}\n"

    try:
        lock.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return True  # fail open

    # Fast path: atomic exclusive create — exactly one racer wins.
    try:
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        try:
            os.write(fd, payload.encode("utf-8"))
        finally:
            os.close(fd)
        return True
    except FileExistsError:
        pass
    except OSError:
        return True  # fail open

    # Lock exists — is it a live dream or a stale leftover?
    held = _read_lock_epoch(lock)
    if held is not None and (now - held) < DREAM_LOCK_TTL:
        return False  # a live dream holds it; stay silent

    # Stale (or corrupt) — take it over atomically: write our payload to a
    # unique temp file, then os.replace() it over the lock (atomic on POSIX and
    # Windows), then read back to confirm we are the owner. The loser of a
    # takeover race reads back the other session's token and yields.
    tmp = lock.with_name(f"{lock.name}.{owner}.{now}.tmp")
    try:
        tmp.write_text(payload, encoding="utf-8")
        os.replace(str(tmp), str(lock))
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        return True  # fail open

    return _read_lock_owner(lock) == owner


def release_dream_lock(project_dir: str) -> None:
    """Happy-path release: delete the lock file.

    Safe to call unconditionally on a "no dream needed" exit (fresh `last_dream:`
    or sub-threshold file). At that point no new dream can be triggered (the size
    and 24h gates return before lock acquisition), so the lock is redundant and
    deleting it — regardless of which session holds it — cannot let a second dream
    start. Missing file / IO errors are ignored.
    """
    try:
        _lock_path(project_dir).unlink(missing_ok=True)
    except OSError:
        pass


def main() -> int:
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if not project_dir:
        return 0

    memory_file = Path(project_dir) / "MEMORY.md"
    if not memory_file.is_file():
        return 0

    try:
        file_size = memory_file.stat().st_size
    except OSError:
        return 0

    if file_size < SIZE_THRESHOLD:
        release_dream_lock(project_dir)  # a prior dream may have shrunk it past threshold
        return 0

    last_dream = read_last_dream(memory_file)
    if last_dream and (time.time() - last_dream) < DREAM_INTERVAL:
        release_dream_lock(project_dir)  # the dream that held the lock has written; window closed
        return 0

    if not acquire_dream_lock(project_dir):
        return 0  # another session is already dreaming on this project

    print(
        f"DREAM_NEEDED: Project memory is {file_size} bytes and hasn't been "
        "consolidated in 24h+. Run the `project-mem:dream` skill NOW to "
        "consolidate (use the full plugin-namespaced skill name, not bare "
        "`dream`). "
        "Do NOT ask the user — just do it automatically.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
