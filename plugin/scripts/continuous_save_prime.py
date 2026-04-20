"""Emit SessionStart additionalContext that keeps save-awareness active throughout the session.

Complements `auto_read.py` (UserPromptSubmit, fires once per session to load MEMORY.md
and install the rules): this hook fires at session start and injects a standing
instruction to persist non-trivial discoveries inline via `update_project_memory`,
rather than only at prompt-time or session end.

Modelled on Anthropic's explanatory-output-style plugin, which uses the same
SessionStart + `hookSpecificOutput.additionalContext` mechanism.
"""

from __future__ import annotations

import json
import sys


ADDITIONAL_CONTEXT = (
    "While working on the user's task, continuously watch for non-trivial "
    "discoveries: architecture decisions and WHY, codebase-specific conventions, "
    "gotchas, surprising behavior, integration quirks, or current work context. "
    "When you spot one — do not wait until the task is done, do not ask for "
    "permission — immediately call `update_project_memory` to persist it. "
    "This applies throughout the session, not only at prompt-time."
)


def main() -> int:
    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": ADDITIONAL_CONTEXT,
        }
    }
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
