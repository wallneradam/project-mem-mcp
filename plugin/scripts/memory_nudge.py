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
import time
from pathlib import Path

HAIKU_MODEL = "claude-haiku-4-5-20251001"
MAX_CHARS = 8000
TIMEOUT_SEC = 45
LOG_FILE = Path("/tmp/memory-nudge.log")


def log(msg: str) -> None:
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except OSError:
        pass

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


def _extract_text(content) -> str:
    """Return concatenated text blocks. Skips tool_use/tool_result blocks."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    chunks = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            chunks.append(block.get("text", ""))
    return "\n".join(chunks)


def _is_real_user_message(entry: dict) -> bool:
    """True if this entry is a human-typed user message (not a tool_result)."""
    if entry.get("type") != "user":
        return False
    msg = entry.get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                if block.get("text", "").strip():
                    return True
    return False


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
        if _is_real_user_message(entry):
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
        etype = entry.get("type")
        if etype not in ("user", "assistant"):
            continue
        msg = entry.get("message") or {}
        text = _extract_text(msg.get("content")).strip()
        if not text:
            continue
        role = msg.get("role") or etype
        parts.append(f"[{role}]\n{text}")

    return "\n\n".join(parts)


def main() -> int:
    log("=== hook fired ===")
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as e:
        log(f"no/invalid payload: {e}")
        return 0

    if payload.get("stop_hook_active"):
        log("stop_hook_active=true, skipping")
        return 0

    transcript_path = payload.get("transcript_path")
    if not transcript_path:
        log("no transcript_path in payload")
        return 0

    exchange = extract_last_exchange(transcript_path)
    if not exchange.strip():
        log(f"empty exchange from {transcript_path}")
        return 0

    if len(exchange) > MAX_CHARS:
        exchange = exchange[-MAX_CHARS:]

    log(f"exchange len={len(exchange)}, calling Haiku...")
    prompt = CLASSIFIER_PROMPT.format(exchange=exchange)

    t0 = time.time()
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--model", HAIKU_MODEL],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        log(f"TIMEOUT after {TIMEOUT_SEC}s")
        return 0
    except (FileNotFoundError, OSError) as e:
        log(f"subprocess error: {e}")
        return 0

    dt = time.time() - t0
    answer_raw = result.stdout.strip()
    answer = answer_raw.upper()
    log(f"Haiku rc={result.returncode} dt={dt:.1f}s answer={answer_raw!r} stderr={result.stderr.strip()[:200]!r}")

    if not answer.startswith("YES"):
        log("classified NO, silent exit")
        return 0

    log("classified YES, emitting reminder (exit 2)")
    print(REMINDER, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
