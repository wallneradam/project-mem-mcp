#!/usr/bin/env python3
import sys
import argparse
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
Stores and retrieves project knowledge in `{MEMORY_FILE}`.

IMPORTANT: You MUST proactively use these tools during your work. When you discover
non-obvious insights, architecture decisions, gotchas, or conventions — call
`update_project_memory` IMMEDIATELY, without being asked. This is not optional.

## Rules

- The project memory file **must be in English**
- Never store sensitive information (passwords, tokens, emails, etc.)
- Use `set_project_memory` when creating new or completely reorganizing
- Use `update_project_memory` for incremental changes

## What TO Store

- Architecture decisions and WHY they were made
- Code patterns and conventions not obvious from the code itself
- Known gotchas, edge cases, and hard-won insights
- Important file paths and their purposes
- External dependencies and integration notes
- Current work context (temporarily, while work is in progress)

## What NOT TO Store

- Change log entries — this belongs in git history
- Information already in CLAUDE.md files
- Completed task details — extract lessons first, then remove the task info
- Information obvious from file names or code structure
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
    project_path: str = Field(description="The full path to the project directory"),
    project_info: str = Field(description="Complete project information in Markdown format")
):
    """
    Set the whole project memory for the given project path in Markdown format.

    Use when creating a new project memory file, completely replacing an existing one,
    or when `update_project_memory` fails to apply patches.

    :raises FileNotFoundError: If the project path doesn't exist
    :raises PermissionError: If the project path is not in allowed directories
    """
    pp = Path(project_path).resolve()
    if not pp.exists() or not pp.is_dir():
        raise FileNotFoundError(f"Project path {project_path} does not exist")
    if not any(str(pp).startswith(base) for base in allowed_directories):
        raise PermissionError(f"Project path {project_path} is not in allowed directories")

    memory_file = pp / MEMORY_FILE
    with open(memory_file, "w") as f:
        f.write(project_info)

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
    project_path: str = Field(description="The full path to the project directory"),
    patch_content: str = Field(description="Single SEARCH/REPLACE block")
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
        raise ValueError("Could not find the search text in the file. "
                         "Please ensure the search text exactly matches the content in the file.")
    if count > 1:
        raise ValueError(f"The search text appears {count} times in the file. "
                         "Please provide more context to identify the specific occurrence.")

    # Apply the replacement
    new_content = content.replace(search_text, replace_text)

    with open(memory_file, 'w', encoding='utf-8') as f:
        f.write(new_content)

    size_bytes = memory_file.stat().st_size
    return f"Successfully updated project memory. {get_size_status(size_bytes)}"
