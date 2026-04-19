"""Stop hook: nudge the model to save to project memory when the last
assistant message contained a `★ Insight` block.

Rationale: insight-mode output blocks are pre-curated by the model as
meaningful conclusions (decisions, architecture, gotchas) — exactly the
content that belongs in project memory. Triggering a save reminder only
when such a block appears gives a high-precision, zero-LLM-cost nudge
(unlike the retired Haiku-classifier memory_nudge).

Output:
- Silent exit 0 when there is no insight block, the loop guard tripped, or
  project memory was already fully rewritten this turn via
  set_project_memory (e.g. after a dream consolidation).
- JSON `{"decision": "block", "reason": "..."}` on stdout + exit 0 when a
  nudge is warranted. This makes the model continue past Stop and see the
  reason as feedback, without Claude Code rendering it as a red
  "Stop hook error" banner (which is what `exit 2 + stderr` produces).
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
    set_memory_called_this_turn = False
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
                etype = entry.get("type")
                if etype == "user":
                    set_memory_called_this_turn = False
                    continue
                if etype != "assistant":
                    continue
                msg = entry.get("message") or {}
                content = msg.get("content")
                if not isinstance(content, list):
                    continue
                parts: list[str] = []
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype == "text":
                        t = block.get("text")
                        if isinstance(t, str):
                            parts.append(t)
                    elif btype == "tool_use":
                        name = block.get("name") or ""
                        if "set_project_memory" in name:
                            set_memory_called_this_turn = True
                if parts:
                    last_text_parts = parts
    except OSError:
        return 0

    last_text = "\n".join(last_text_parts)
    if INSIGHT_MARKER not in last_text:
        return 0

    # Skip the nudge if project memory was just fully rewritten this turn
    # (e.g. dream consolidation). The model already persisted its state —
    # nudging to save again is redundant and visually noisy.
    if set_memory_called_this_turn:
        return 0

    json.dump({"decision": "block", "reason": NUDGE}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
