"""Check if dream consolidation is needed after a project memory write.

Conditions: file > 25KB AND last dream was > 24h ago (or never).
Exit 0 = silent (no dream needed), exit 2 + stderr = signal to Claude.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

SIZE_THRESHOLD = 25_600  # 25 KB
DREAM_INTERVAL = 86_400  # 24 hours in seconds


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

    dream_timestamp = Path(project_dir) / ".claude" / ".last-dream-timestamp"
    if dream_timestamp.is_file():
        try:
            last_dream = int(dream_timestamp.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            last_dream = 0
        if (time.time() - last_dream) < DREAM_INTERVAL:
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
