#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path

from fastmcp import FastMCP
from pydantic.fields import Field

MEMORY_FILE = "MEMORY.md"


mcp = FastMCP(
    name="Project Memory MCP",
    instructions=f"""
Stores and retrieves project knowledge in `{MEMORY_FILE}`.

IMPORTANT: You MUST proactively use these tools during your work. When you discover
non-obvious insights, architecture decisions, gotchas, or conventions — call
`update_project_memory` IMMEDIATELY, without being asked. This is not optional.

## Rules

- The memory file **must be in English**
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
    project_path: str = Field(description="The full path to the project directory")
) -> str:
    """
    Get the whole project memory for the given project path in Markdown format.

    :return: The project memory content in Markdown format
    :raises FileNotFoundError: If the project path doesn't exist or MEMORY.md is missing
    :raises PermissionError: If the project path is not in allowed directories
    """
    pp = Path(project_path).resolve()

    # Check if the project path exists and is a directory
    if not pp.exists() or not pp.is_dir():
        raise FileNotFoundError(f"Project path {project_path} does not exist")
    # Check if it is inside one of the allowed directories
    if not any(str(pp).startswith(base) for base in allowed_directories):
        raise PermissionError(f"Project path {project_path} is not in allowed directories")

    with open(pp / MEMORY_FILE, "r") as f:
        return f.read()


@mcp.tool()
def set_project_memory(
    project_path: str = Field(description="The full path to the project directory"),
    project_info: str = Field(description="Complete project information in Markdown format")
):
    """
    Set the whole project memory for the given project path in Markdown format.

    Use when creating a new memory file, completely replacing an existing one,
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
    return f"Memory saved successfully. {get_size_status(size_bytes)}"


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
    Text to find in the memory file
    =======
    Text to replace it with
    >>>>>>> REPLACE
    ```

    Use empty replacement text to remove content.

    :return: Success message
    :raises FileNotFoundError: If the project path or memory file doesn't exist
    :raises ValueError: If patch format is invalid or search text isn't unique
    """
    project_dir = Path(project_path).resolve()
    if not project_dir.is_dir():
        raise FileNotFoundError(f"Project path {project_path} does not exist or is not a directory")
    memory_file = project_dir / MEMORY_FILE
    if not memory_file.exists():
        raise FileNotFoundError(
            f"Memory file does not exist at {memory_file}. Use `set_project_memory` to set the whole memory instead."
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
    return f"Successfully updated memory file. {get_size_status(size_bytes)}"
