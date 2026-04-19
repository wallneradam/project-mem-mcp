"""Block set_project_memory / update_project_memory calls from subagents.

Subagents (Task/Agent tool invocations) run with narrow task context and have
repeatedly polluted MEMORY.md with task-specific noise. This PreToolUse hook
restricts writes to the main session only.

Detection: `auto_read.py` creates `project-memory-read-{session_id}` on
UserPromptSubmit. UserPromptSubmit fires only for the main session's user
prompts, never for subagent invocations. Therefore: state file present →
main session (allow); state file absent → subagent (deny).

Reads (`get_project_memory`) are not matched by the hook and remain available
to subagents.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    session_id = payload.get("session_id")
    if not session_id:
        return 0

    state_file = Path(tempfile.gettempdir()) / f"project-memory-read-{session_id}"
    if state_file.exists():
        return 0

    print(
        "Project memory writes are disabled inside subagents. "
        "Only the main session may call set_project_memory / update_project_memory. "
        "If you discovered something worth persisting, include it in your final "
        "report to the parent agent and let the parent save it.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
