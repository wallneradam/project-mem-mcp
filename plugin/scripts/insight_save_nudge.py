"""Stop hook: nudge the model to save to project memory when the last
assistant message contained a `★ Insight` block.

Rationale: insight-mode output blocks are pre-curated by the model as
meaningful conclusions (decisions, architecture, gotchas) — exactly the
content that belongs in project memory. Triggering a save reminder only
when such a block appears gives a high-precision, zero-LLM-cost nudge
(unlike the retired Haiku-classifier memory_nudge).

Exit codes:
- 0 = silent (no insight block in last assistant message, or loop guard tripped)
- 2 = stderr nudge surfaced to the model so it can decide whether to save
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

INSIGHT_MARKER = "★ Insight"

NUDGE = (
    "PROJECT_MEMORY_HINT: Your last reply contained a `★ Insight` block. "
    "If any of those points are durable (architecture, decision, gotcha, "
    "convention, non-obvious pattern) and not yet in MEMORY.md, save them "
    "NOW via update_project_memory. Also consider a 1-2 line entry under "
    "`## Recent Sessions` if the insight captures the state of a just-completed "
    "task. If nothing is durable, continue without saving."
)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    # Loop guard: if this Stop hook was already re-triggered by our previous
    # exit 2, don't nudge again.
    if payload.get("stop_hook_active"):
        return 0

    transcript_path = payload.get("transcript_path")
    if not transcript_path:
        return 0
    tp = Path(transcript_path)
    if not tp.is_file():
        return 0

    last_text_parts: list[str] = []
    try:
        with tp.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") != "assistant":
                    continue
                msg = entry.get("message") or {}
                content = msg.get("content")
                if not isinstance(content, list):
                    continue
                parts: list[str] = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        t = block.get("text")
                        if isinstance(t, str):
                            parts.append(t)
                if parts:
                    last_text_parts = parts
    except OSError:
        return 0

    last_text = "\n".join(last_text_parts)
    if INSIGHT_MARKER not in last_text:
        return 0

    print(NUDGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
