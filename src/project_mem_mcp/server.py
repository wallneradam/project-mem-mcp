#!/usr/bin/env python3
import re
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from pydantic.fields import Field

MEMORY_FILE = "MEMORY.md"

# Token-budget guard. Refuse to return the full file in one shot above this
# estimate (chars/4 heuristic) — Claude Code's tool-result cap is 25K tokens
# and other MCP clients may have similar limits. Callers can override by
# passing explicit offset/limit (treated as informed consent).
MAX_FULL_READ_TOKENS = 20000


mcp = FastMCP(
    name="Project Memory MCP",
    instructions=f"""
This server manages "project memory": a `{MEMORY_FILE}` file at the project root,
an agent-maintained knowledge base about the codebase — architecture decisions
and WHY, non-obvious conventions, gotchas, key file purposes, and a
"Recent Sessions" log of recent work.

IMPORTANT: NEVER edit `{MEMORY_FILE}` directly with file-editing tools
(Write/Edit/sed/...). Always go through the four MCP tools below — they enforce
safe patching, size guards, and pagination.

Tools:
- get_project_memory: read at session start. On a "too large" ValueError, retry
  with head_only=True (returns size + section TOC with line ranges), then fetch
  sections via offset/limit.
- search_project_memory: substring lookup; returns matching lines with 1-indexed
  line numbers. Follow up with get_project_memory(offset, limit) for context.
- update_project_memory: default for changes. ONE SEARCH/REPLACE block per call,
  SEARCH text must match exactly once.
- set_project_memory: new projects or full rewrites only — overwrites the whole
  file.

Save proactively, mid-task, without waiting for permission, when you discover:
architecture decisions and WHY, non-obvious patterns or conventions, gotchas,
surprising behavior, external dependency quirks, integration notes. After any
non-trivial task, prepend 1-2 lines to a "## Recent Sessions" section, newest
first, format: "- YYYY-MM-DD: <what was done/decided>.".

Skip: per-commit changelogs (git history owns that), facts already in
CLAUDE.md / AGENTS.md, code-obvious info, secrets, ephemeral state.
All content in English.
"""
)

allowed_directories = []


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def format_size(size_bytes: int) -> str:
    """Format size in human-readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} bytes"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def get_size_status(size_bytes: int) -> str:
    """Get size status message."""
    return f"Size: {format_size(size_bytes)}"


def estimate_tokens(text: str) -> int:
    """Rough token estimate (chars/4 heuristic, no tokenizer dep)."""
    return len(text) // 4


_LAST_DREAM_RE = re.compile(r"^\s*last_dream\s*:")


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _split_frontmatter(content: str) -> tuple[str, str]:
    """Split content into (frontmatter_block, body).

    frontmatter_block is the full "---\\n...\\n---\\n" prefix (delimiters
    included, trailing newline included) if present, otherwise "". An
    unterminated `---` opener is treated as no frontmatter.
    """
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\n") != "---":
        return "", content
    for i in range(1, len(lines)):
        if lines[i].rstrip("\n") == "---":
            return "".join(lines[: i + 1]), "".join(lines[i + 1 :])
    return "", content


def _apply_last_dream_bump(content: str, now_iso: str) -> str:
    """Idempotently set `last_dream: <now_iso>` in YAML frontmatter.

    Creates a frontmatter block if absent; updates the existing key in place
    if present; otherwise appends it. Preserves any other frontmatter keys.
    """
    frontmatter, body = _split_frontmatter(content)
    if not frontmatter:
        return f"---\nlast_dream: {now_iso}\n---\n\n{content.lstrip()}"

    lines = frontmatter.splitlines(keepends=True)
    inner = lines[1:-1]
    for j, line in enumerate(inner):
        if _LAST_DREAM_RE.match(line):
            inner[j] = f"last_dream: {now_iso}\n"
            break
    else:
        inner.append(f"last_dream: {now_iso}\n")

    return "".join([lines[0]] + inner + [lines[-1]]) + body


def _extract_last_dream(frontmatter: str) -> str | None:
    """Return the raw value of `last_dream:` from a frontmatter block, or None."""
    if not frontmatter:
        return None
    for line in frontmatter.splitlines():
        m = re.match(r"^\s*last_dream\s*:\s*(.*?)\s*$", line)
        if m:
            return m.group(1)
    return None


def _strip_last_dream(content: str) -> str:
    """Remove any `last_dream:` line from the frontmatter.

    `last_dream:` is MCP-owned — callers must not set it (an LLM-written
    value tends to be a hard-coded string with `:00` seconds, not a real
    timestamp). If stripping leaves the frontmatter block empty, drop the
    block entirely so the caller's intent ("no frontmatter") is honored.
    """
    frontmatter, body = _split_frontmatter(content)
    if not frontmatter:
        return content
    lines = frontmatter.splitlines(keepends=True)
    inner = [line for line in lines[1:-1] if not _LAST_DREAM_RE.match(line)]
    if not inner:
        return body
    return "".join([lines[0]] + inner + [lines[-1]]) + body


def build_head(content: str) -> str:
    """Return size metadata + markdown heading TOC with line ranges.

    Used when the caller asks for head_only or when the full file would exceed
    MAX_FULL_READ_TOKENS. Lines are 1-indexed to match offset/limit semantics
    a human reader expects (matches `Read` tool conventions in most harnesses).
    """
    lines = content.splitlines()
    total_lines = len(lines)
    size_bytes = len(content.encode("utf-8"))
    tokens_est = estimate_tokens(content)

    headings: list[tuple[int, str]] = []
    for i, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            headings.append((i, line.rstrip()))

    out = [
        f"total_lines: {total_lines}",
        f"size_bytes: {size_bytes}",
        f"estimated_tokens: {tokens_est}",
        "",
        "sections (line ranges, 1-indexed):",
    ]
    if not headings:
        out.append(f"  1-{total_lines}: (no markdown headings found)")
    else:
        if headings[0][0] > 1:
            out.append(f"  1-{headings[0][0] - 1}: (pre-heading content)")
        for idx, (start, text) in enumerate(headings):
            end = headings[idx + 1][0] - 1 if idx + 1 < len(headings) else total_lines
            out.append(f"  {start}-{end}: {text}")
    out.append("")
    out.append(
        "Use get_project_memory(offset=N, limit=M) to fetch a chunk. "
        "Offset is 1-indexed line number; limit is line count."
    )
    return "\n".join(out)


def main():
    # Process command line arguments
    global allowed_directories
    parser = argparse.ArgumentParser(description="Project Memory MCP server")
    parser.add_argument(
        '--allowed-dir',
        action='append',
        dest='allowed_dirs',
        default=[],
        help='Allowed base directory for project paths (can be used multiple times)'
    )
    args = parser.parse_args()
    allowed_directories = [str(Path(d).resolve()) for d in args.allowed_dirs]

    if not allowed_directories:
        # Default to current working directory (where the server was started from)
        allowed_directories = [str(Path.cwd().resolve())]

    eprint(f"Allowed directories: {allowed_directories}")

    # Run the MCP server
    mcp.run()


if __name__ == "__main__":
    main()


#
# Tools
#

@mcp.tool()
def get_project_memory(
    project_path: Annotated[str, Field(description="The full path to the project directory")],
    offset: Annotated[int, Field(description="1-indexed start line; 0 = from start")] = 0,
    limit: Annotated[int | None, Field(description="Max lines to return; None = all")] = None,
    head_only: Annotated[bool, Field(description="If True, return only size + heading TOC")] = False,
) -> str:
    """
    Get project memory (MEMORY.md) content.

    For large files, call with head_only=True first to inspect size + sections,
    then use offset/limit to fetch chunks. Default returns the whole file unless
    it exceeds the server's token budget, in which case an error suggests pagination.

    :raises FileNotFoundError: If the project path doesn't exist or MEMORY.md is missing
    :raises PermissionError: If the project path is not in allowed directories
    :raises ValueError: If file exceeds token budget and no offset/limit/head_only given
    """
    pp = Path(project_path).resolve()

    if not pp.exists() or not pp.is_dir():
        raise FileNotFoundError(f"Project path {project_path} does not exist")
    if not any(str(pp).startswith(base) for base in allowed_directories):
        raise PermissionError(f"Project path {project_path} is not in allowed directories")

    with open(pp / MEMORY_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    if head_only:
        return build_head(content)

    # Chunked read path — caller has opted in via offset/limit.
    if offset > 0 or limit is not None:
        lines = content.splitlines(keepends=True)
        total = len(lines)
        start = max(0, offset - 1) if offset > 0 else 0
        end = total if limit is None else min(total, start + limit)
        chunk = "".join(lines[start:end])
        return f"# lines {start + 1}-{end} of {total}\n{chunk}"

    # Full-file path — guard against runaway responses.
    tokens_est = estimate_tokens(content)
    if tokens_est > MAX_FULL_READ_TOKENS:
        raise ValueError(
            f"MEMORY.md is large (~{tokens_est} tokens, threshold {MAX_FULL_READ_TOKENS}). "
            "Call with head_only=True to get a size+TOC summary, then use "
            "offset/limit to read sections."
        )
    return content


@mcp.tool()
def set_project_memory(
    project_path: Annotated[str, Field(description="The full path to the project directory")],
    project_info: Annotated[str, Field(description="Complete project information in Markdown format")],
    bump_last_dream: Annotated[bool, Field(description="If True, set `last_dream:` in YAML frontmatter to current UTC ISO timestamp (idempotent; creates frontmatter if absent; preserves other keys)")] = False,
):
    """
    Set the whole project memory for the given project path in Markdown format.

    Use when creating a new project memory file, completely replacing an existing one,
    or when `update_project_memory` fails to apply patches.

    If the existing MEMORY.md has a YAML frontmatter block (e.g. `last_dream:`)
    and the new `project_info` does not, the old frontmatter is preserved
    automatically — callers do not need to know about it.

    :raises FileNotFoundError: If the project path doesn't exist
    :raises PermissionError: If the project path is not in allowed directories
    """
    pp = Path(project_path).resolve()
    if not pp.exists() or not pp.is_dir():
        raise FileNotFoundError(f"Project path {project_path} does not exist")
    if not any(str(pp).startswith(base) for base in allowed_directories):
        raise PermissionError(f"Project path {project_path} is not in allowed directories")

    memory_file = pp / MEMORY_FILE

    # MCP owns `last_dream:` — strip any caller-written value before merging.
    new_content = _strip_last_dream(project_info)

    old_last_dream: str | None = None
    if memory_file.exists():
        with open(memory_file, "r", encoding="utf-8") as f:
            old_content = f.read()
        old_frontmatter, _ = _split_frontmatter(old_content)
        old_last_dream = _extract_last_dream(old_frontmatter)
        new_frontmatter, _ = _split_frontmatter(new_content)
        if old_frontmatter and not new_frontmatter:
            new_content = old_frontmatter + "\n" + new_content
            old_last_dream = None  # already preserved via the verbatim splice

    if old_last_dream is not None:
        new_content = _apply_last_dream_bump(new_content, old_last_dream)

    if bump_last_dream:
        new_content = _apply_last_dream_bump(new_content, _now_iso_utc())

    with open(memory_file, "w", encoding="utf-8") as f:
        f.write(new_content)

    size_bytes = memory_file.stat().st_size
    return f"Project memory saved successfully. {get_size_status(size_bytes)}"


def validate_single_block(lines):
    """
    Validate that `lines` contains exactly one valid SEARCH/REPLACE block.

    Markers are matched line-exact (the whole line must equal the marker),
    so `=======` or `>>>>>>> REPLACE` appearing as substrings within a line
    do not count.

    :param lines: The patch content split into lines
    :raises ValueError: If format is invalid or there's not exactly one block
    """
    search_count = sum(1 for line in lines if line == "<<<<<<< SEARCH")
    separator_count = sum(1 for line in lines if line == "=======")
    replace_count = sum(1 for line in lines if line == ">>>>>>> REPLACE")

    if search_count == 0:
        raise ValueError("Missing <<<<<<< SEARCH marker")
    if search_count > 1:
        raise ValueError(f"Only one SEARCH/REPLACE block allowed, found {search_count}")
    if separator_count != 1:
        raise ValueError("Missing or multiple ======= separators")
    if replace_count != 1:
        raise ValueError("Missing or multiple >>>>>>> REPLACE markers")


def find_match_lines(content: str, needle: str) -> list[int]:
    """Return 1-indexed line numbers of every exact occurrence of `needle` in `content`."""
    if not needle:
        return []
    lines = []
    start = 0
    while True:
        idx = content.find(needle, start)
        if idx == -1:
            break
        lines.append(content.count("\n", 0, idx) + 1)
        start = idx + 1
    return lines


def diagnose_missing_search(content: str, search_text: str) -> str:
    """Build a helpful hint string explaining where SEARCH partially matched.

    Strategy: take the first non-empty line of the SEARCH block and look for it
    in the file — first exact, then whitespace-normalized. If anything matches,
    point the caller at those line numbers so they can re-read just that slice
    instead of the whole file.
    """
    search_lines = [ln for ln in search_text.splitlines() if ln.strip()]
    if not search_lines:
        return ""
    first = search_lines[0]
    file_lines = content.splitlines()

    exact = [i + 1 for i, ln in enumerate(file_lines) if ln == first]
    if exact:
        return (
            f" Hint: the first non-empty line of SEARCH matches exactly at line(s) "
            f"{exact}. The rest of the block likely diverges (whitespace, stale "
            f"content, or surrounding lines changed). Re-read around those lines "
            f"via get_project_memory(offset=N, limit=M)."
        )

    stripped_target = first.strip()
    fuzzy = [i + 1 for i, ln in enumerate(file_lines) if ln.strip() == stripped_target]
    if fuzzy:
        return (
            f" Hint: the first non-empty line of SEARCH matches at line(s) "
            f"{fuzzy} after stripping whitespace. Likely indentation or "
            f"trailing-whitespace mismatch — re-read those lines verbatim."
        )
    return ""


@mcp.tool()
def search_project_memory(
    project_path: Annotated[str, Field(description="The full path to the project directory")],
    query: Annotated[str, Field(description="Substring to search for (case-insensitive)")],
    max_results: Annotated[int, Field(description="Max matches to return")] = 50,
) -> str:
    """
    Search MEMORY.md for a substring. Returns matching lines with 1-indexed line
    numbers; follow up with get_project_memory(offset=N, limit=M) for surrounding
    context. Cheap alternative to reading the whole file when looking up a fact.

    :raises FileNotFoundError: If the project path doesn't exist or MEMORY.md is missing
    :raises PermissionError: If the project path is not in allowed directories
    """
    pp = Path(project_path).resolve()
    if not pp.exists() or not pp.is_dir():
        raise FileNotFoundError(f"Project path {project_path} does not exist")
    if not any(str(pp).startswith(base) for base in allowed_directories):
        raise PermissionError(f"Project path {project_path} is not in allowed directories")
    if not query:
        raise ValueError("query must be non-empty")

    with open(pp / MEMORY_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    needle = query.lower()
    matches: list[tuple[int, str]] = []
    for i, line in enumerate(content.splitlines(), start=1):
        if needle in line.lower():
            matches.append((i, line))
            if len(matches) >= max_results:
                break

    if not matches:
        return f"No matches for {query!r} in MEMORY.md."

    truncated = " (truncated)" if len(matches) == max_results else ""
    out = [f"Found {len(matches)} match(es){truncated} for {query!r}:"]
    for line_no, line in matches:
        # Cap each line for output sanity — full context is one offset/limit call away.
        display = line if len(line) <= 200 else line[:200] + "…"
        out.append(f"L{line_no}: {display}")
    out.append("")
    out.append(
        "Use get_project_memory(offset=N, limit=M) to read context around any match."
    )
    return "\n".join(out)


def parse_single_block(patch_content):
    """
    Parse a single SEARCH/REPLACE block from the patch content.

    :param patch_content: Raw patch content with one SEARCH/REPLACE block
    :return: Tuple (search_text, replace_text)
    :raises ValueError: If patch format is invalid
    """
    lines = patch_content.splitlines()
    validate_single_block(lines)

    search_start = None
    separator_idx = None
    replace_end = None

    for i, line in enumerate(lines):
        if line == "<<<<<<< SEARCH":
            search_start = i + 1
        elif line == "=======" and search_start is not None:
            separator_idx = i
        elif line == ">>>>>>> REPLACE" and separator_idx is not None:
            replace_end = i
            break

    search_text = "\n".join(lines[search_start:separator_idx])
    replace_text = "\n".join(lines[separator_idx + 1:replace_end])

    return search_text, replace_text


@mcp.tool()
def update_project_memory(
    project_path: Annotated[str, Field(description="The full path to the project directory")],
    patch_content: Annotated[str, Field(description="Single SEARCH/REPLACE block")],
    bump_last_dream: Annotated[bool, Field(description="If True, also set `last_dream:` in YAML frontmatter to current UTC ISO timestamp (idempotent; creates frontmatter if absent; preserves other keys)")] = False,
):
    """
    Update the project memory by applying a single search-replace patch.

    Required format:
    ```
    <<<<<<< SEARCH
    Text to find in the project memory file
    =======
    Text to replace it with
    >>>>>>> REPLACE
    ```

    Use empty replacement text to remove content.

    :return: Success message
    :raises FileNotFoundError: If the project path or project memory file doesn't exist
    :raises ValueError: If patch format is invalid or search text isn't unique
    """
    project_dir = Path(project_path).resolve()
    if not project_dir.is_dir():
        raise FileNotFoundError(f"Project path {project_path} does not exist or is not a directory")
    memory_file = project_dir / MEMORY_FILE
    if not memory_file.exists():
        raise FileNotFoundError(
            f"Project memory file does not exist at {memory_file}. Use `set_project_memory` to set the whole project memory instead."
        )

    # Read the current file content
    with open(memory_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Parse the single block
    search_text, replace_text = parse_single_block(patch_content)

    # Check exact match count
    count = content.count(search_text)

    if count == 0:
        hint = diagnose_missing_search(content, search_text)
        raise ValueError(
            "Could not find the search text in the file. "
            "Please ensure the search text exactly matches the content in the file."
            + hint
        )
    if count > 1:
        positions = find_match_lines(content, search_text)
        raise ValueError(
            f"The search text appears {count} times in the file (at line(s) {positions}). "
            "Add more surrounding context lines to make the match unique, or re-read "
            "one of those line ranges via get_project_memory(offset=N, limit=M) to "
            "choose the right anchor."
        )

    # Apply the replacement
    new_content = content.replace(search_text, replace_text)

    # MCP owns `last_dream:` — strip from result and splice the old value back,
    # so a patch that accidentally touches the frontmatter cannot corrupt it.
    old_frontmatter, _ = _split_frontmatter(content)
    old_last_dream = _extract_last_dream(old_frontmatter)
    new_content = _strip_last_dream(new_content)
    if old_last_dream is not None:
        new_content = _apply_last_dream_bump(new_content, old_last_dream)

    if bump_last_dream:
        new_content = _apply_last_dream_bump(new_content, _now_iso_utc())

    with open(memory_file, 'w', encoding='utf-8') as f:
        f.write(new_content)

    size_bytes = memory_file.stat().st_size
    return f"Successfully updated project memory. {get_size_status(size_bytes)}"
