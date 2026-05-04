"""Update the `last_dream` timestamp in MEMORY.md's YAML frontmatter.

Called by the dream skill at the end of consolidation. Idempotent: creates a
frontmatter block if none exists, inserts `last_dream:` if missing, replaces it
if present. No third-party deps — stdlib only.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

LAST_DREAM_RE = re.compile(r"^\s*last_dream\s*:")


def build_new_content(content: str, now: str) -> str:
    lines = content.splitlines(keepends=True)

    if not lines or lines[0].rstrip("\n") != "---":
        return f"---\nlast_dream: {now}\n---\n\n" + content

    closing_idx = None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\n") == "---":
            closing_idx = i
            break

    if closing_idx is None:
        return f"---\nlast_dream: {now}\n---\n\n" + content

    block = lines[1:closing_idx]
    for j, line in enumerate(block):
        if LAST_DREAM_RE.match(line):
            block[j] = f"last_dream: {now}\n"
            break
    else:
        block.append(f"last_dream: {now}\n")

    return "".join([lines[0]] + block + lines[closing_idx:])


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1]:
        project_dir = argv[1]
    else:
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()

    if not project_dir:
        print("update_dream_timestamp: no project dir resolved", file=sys.stderr)
        return 1

    memory_file = Path(project_dir) / "MEMORY.md"
    if not memory_file.is_file():
        print(
            f"update_dream_timestamp: MEMORY.md not found at {memory_file}",
            file=sys.stderr,
        )
        return 1

    try:
        content = memory_file.read_text(encoding="utf-8")
    except OSError as e:
        print(f"update_dream_timestamp: read failed: {e}", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_content = build_new_content(content, now)

    fd, tmp_path = tempfile.mkstemp(
        prefix=".MEMORY.md.", suffix=".tmp", dir=str(memory_file.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new_content)
        os.replace(tmp_path, memory_file)
    except OSError as e:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        print(f"update_dream_timestamp: write failed: {e}", file=sys.stderr)
        return 1

    print(f"update_dream_timestamp: set last_dream={now} in {memory_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
