"""Nudge the model to consider saving to project memory.

Stop hook. Extracts the last user message + following assistant responses
from the transcript, asks a Haiku classifier whether the exchange might
contain something durable worth remembering, and if so blocks the stop
with a reminder. The main model still decides what (if anything) to save.

Exit 0 = silent, exit 2 + stderr = reminder fed back to the model.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HAIKU_MODEL = "claude-haiku-4-5-20251001"
MAX_CHARS = 8000
TIMEOUT_SEC = 20

CLASSIFIER_PROMPT = """You are a binary classifier. Decide whether the following conversation exchange contains anything potentially worth saving to persistent project memory for future sessions.

Potentially worth saving: user preferences, corrections to the assistant's behavior, workflow rules, architecture decisions with reasoning, non-obvious project context, stable gotchas, durable facts about the user or project.

NOT worth saving: routine coding tasks, ephemeral debugging, trivial Q&A, things obvious from the code, one-off requests, changelog-style summaries.

You do NOT decide what to save or how. You only signal whether the main model should review the exchange for potential memory-worthy content.

Respond with EXACTLY one word, uppercase, no punctuation: YES or NO.

--- EXCHANGE START ---
{exchange}
--- EXCHANGE END ---
"""

REMINDER = (
    "MEMORY_CHECK: The last exchange may contain something worth saving to "
    "project memory (e.g. user preference, correction, decision, gotcha, or "
    "durable project context). Review the exchange against the current "
    "MEMORY.md. If — and only if — there is non-obvious, durable information "
    "that is not already saved, save it now via update_project_memory. "
    "Otherwise ignore this reminder and stop."
)


def extract_last_exchange(transcript_path: str) -> str:
    try:
        lines = Path(transcript_path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""

    last_user_idx = -1
    for i in range(len(lines) - 1, -1, -1):
        try:
            entry = json.loads(lines[i])
        except json.JSONDecodeError:
            continue
        if entry.get("type") == "user":
            last_user_idx = i
            break

    if last_user_idx < 0:
        return ""

    parts: list[str] = []
    for line in lines[last_user_idx:]:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = entry.get("message") or {}
        role = msg.get("role") or entry.get("type", "")
        content = msg.get("content")
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            chunks = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    chunks.append(block.get("text", ""))
            text = "\n".join(chunks)
        text = text.strip()
        if text:
            parts.append(f"[{role}]\n{text}")

    return "\n\n".join(parts)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    if payload.get("stop_hook_active"):
        return 0

    transcript_path = payload.get("transcript_path")
    if not transcript_path:
        return 0

    exchange = extract_last_exchange(transcript_path)
    if not exchange.strip():
        return 0

    if len(exchange) > MAX_CHARS:
        exchange = exchange[-MAX_CHARS:]

    prompt = CLASSIFIER_PROMPT.format(exchange=exchange)

    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--model", HAIKU_MODEL],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SEC,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return 0

    answer = result.stdout.strip().upper()
    if not answer.startswith("YES"):
        return 0

    print(REMINDER, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
