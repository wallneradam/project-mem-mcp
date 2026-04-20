"""Check if dream consolidation is needed after a project memory write.

Conditions: file > 50KB AND last dream was > 24h ago (or never).
Exit 0 = silent (no dream needed), exit 2 + stderr = signal to Claude.

The last-dream timestamp lives as `last_dream: <ISO 8601 UTC>` inside the
YAML frontmatter at the top of MEMORY.md (written by update_dream_timestamp.py
after each dream run). Missing or unparseable → treated as "never".
"""

from __future__ import annotations

import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

SIZE_THRESHOLD = 51_200  # 50 KB
DREAM_INTERVAL = 86_400  # 24 hours in seconds

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
        return 0

    last_dream = read_last_dream(memory_file)
    if last_dream and (time.time() - last_dream) < DREAM_INTERVAL:
        return 0

    print(
        f"DREAM_NEEDED: Project memory is {file_size} bytes and hasn't been "
        "consolidated in 24h+. Run the dream skill NOW to consolidate. "
        "Do NOT ask the user — just do it automatically.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
