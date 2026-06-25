"""
MergeMind — Context Builder

Responsible for building enriched code context for AI agents.
Instead of sending just the raw diff lines, this module gathers:
  1. The full code diff/changes
  2. The surrounding function(s) where changes occur  
  3. Additional nearby context for meaningful review

This gives agents enough context to provide high-quality, nuanced reviews.
"""

import re
from dataclasses import dataclass, field
from app.utils.diff_parser import FileDiff, get_changed_line_numbers


@dataclass
class FunctionContext:
    """
    Represents a function/method/class that contains changed code.
    """
    # Function/method name
    name: str = ""
    # Start line of the function in the file (1-indexed)
    start_line: int = 0
    # End line of the function in the file (1-indexed)
    end_line: int = 0
    # The full function source code
    source: str = ""


@dataclass
class FileContext:
    """
    Complete context for a single changed file.
    
    This is what gets sent to AI agents — it contains everything
    they need to understand the change in context.
    """
    # File path relative to repo root
    file_path: str = ""
    # Detected programming language
    language: str = ""
    # Whether this is a new file
    is_new: bool = False
    # Whether this file was deleted
    is_deleted: bool = False
    # The raw diff content for this file
    diff_content: str = ""
    # Full file content (for context)
    full_content: str = ""
    # Functions/methods that contain the changed lines
    changed_functions: list[FunctionContext] = field(default_factory=list)
    # Lines of nearby context around each changed section
    surrounding_context: str = ""


# ── Function Boundary Patterns ────────────────────────────────────────
# Regex patterns to detect function/method/class definitions
# These are simple heuristics — not a full parser, but good enough for context
FUNCTION_PATTERNS = {
    "python": re.compile(
        r"^(\s*)(def|class|async\s+def)\s+(\w+)"
    ),
    "javascript": re.compile(
        r"^(\s*)(function|class|const|let|var|async\s+function)\s+(\w+)"
    ),
    "typescript": re.compile(
        r"^(\s*)(function|class|const|let|var|async\s+function|interface|type|enum)\s+(\w+)"
    ),
    "java": re.compile(
        r"^(\s*)(public|private|protected|static|final|abstract|synchronized)?\s*(class|interface|void|int|String|boolean|double|float|long)\s+(\w+)"
    ),
    "go": re.compile(
        r"^(\s*)(func|type)\s+(\w+)"
    ),
    "rust": re.compile(
        r"^(\s*)(fn|pub\s+fn|struct|enum|impl|trait)\s+(\w+)"
    ),
    "ruby": re.compile(
        r"^(\s*)(def|class|module)\s+(\w+)"
    ),
    "php": re.compile(
        r"^(\s*)(function|class|interface|trait)\s+(\w+)"
    ),
    "csharp": re.compile(
        r"^(\s*)(public|private|protected|internal|static)?\s*(class|interface|void|int|string|bool|async)\s+(\w+)"
    ),
}

# Default pattern used when language-specific pattern isn't available
DEFAULT_FUNCTION_PATTERN = re.compile(
    r"^(\s*)(function|def|class|fn|func|pub\s+fn|async\s+def|async\s+function)\s+(\w+)"
)


def find_function_boundaries(
    file_content: str,
    language: str
) -> list[tuple[str, int, int]]:
    """
    Find all function/method/class boundaries in a file.
    
    Uses indentation-based heuristics for Python-like languages
    and brace-counting for C-style languages.
    
    Args:
        file_content: The full source code of the file
        language: The programming language
        
    Returns:
        List of (name, start_line, end_line) tuples (1-indexed)
    """
    lines = file_content.split("\n")
    pattern = FUNCTION_PATTERNS.get(language, DEFAULT_FUNCTION_PATTERN)
    functions: list[tuple[str, int, int]] = []

    # Track function starts so we can determine where they end
    function_starts: list[tuple[str, int, int]] = []  # (name, line_num, indent_level)

    for i, line in enumerate(lines):
        match = pattern.search(line)
        if match:
            # Get the indentation level (number of leading spaces)
            indent = len(line) - len(line.lstrip())
            # The function name is the last captured group
            name = match.group(match.lastindex)

            # Close any functions at the same or deeper indent level
            while function_starts and function_starts[-1][2] >= indent:
                prev_name, prev_start, _ = function_starts.pop()
                functions.append((prev_name, prev_start, i))

            function_starts.append((name, i + 1, indent))  # 1-indexed

    # Close remaining open functions at end of file
    total_lines = len(lines)
    while function_starts:
        name, start, _ = function_starts.pop()
        functions.append((name, start, total_lines))

    return functions


def extract_surrounding_context(
    file_content: str,
    changed_lines: list[int],
    context_radius: int = 10
) -> str:
    """
    Extract lines surrounding the changed code for additional context.
    
    Instead of sending the entire file, we grab a window of lines
    around each changed section. This balances context vs. token usage.
    
    Args:
        file_content: The full source code
        changed_lines: List of changed line numbers (1-indexed)
        context_radius: Number of lines to include above/below changes
        
    Returns:
        String containing the relevant surrounding lines with line numbers
    """
    if not changed_lines or not file_content:
        return ""

    lines = file_content.split("\n")
    total_lines = len(lines)

    # Build a set of line numbers to include
    included_lines: set[int] = set()
    for line_num in changed_lines:
        start = max(1, line_num - context_radius)
        end = min(total_lines, line_num + context_radius)
        for ln in range(start, end + 1):
            included_lines.add(ln)

    # Build the context string with line numbers
    # We group consecutive lines and add "..." for gaps
    sorted_lines = sorted(included_lines)
    context_parts: list[str] = []
    prev_line = 0

    for line_num in sorted_lines:
        if prev_line > 0 and line_num > prev_line + 1:
            # There's a gap — indicate skipped lines
            context_parts.append("    ...")

        # Add the line with its line number (1-indexed to match editors)
        if 1 <= line_num <= total_lines:
            context_parts.append(f"  {line_num:4d} | {lines[line_num - 1]}")

        prev_line = line_num

    return "\n".join(context_parts)


def build_file_context(
    file_diff: FileDiff,
    full_file_content: str | None = None
) -> FileContext:
    """
    Build complete context for a single changed file.
    
    This is the main function that combines:
    - The raw diff content
    - Surrounding context lines
    - Function boundaries that contain changes
    
    Args:
        file_diff: Parsed diff for this file
        full_file_content: Full source code of the file (fetched from GitHub)
        
    Returns:
        FileContext with all the enriched context agents need
    """
    # Assemble the raw diff content from all hunks
    diff_content = "\n".join(hunk.content for hunk in file_diff.hunks)

    context = FileContext(
        file_path=file_diff.file_path,
        language=file_diff.language,
        is_new=file_diff.is_new,
        is_deleted=file_diff.is_deleted,
        diff_content=diff_content,
        full_content=full_file_content or "",
    )

    # If we have the full file content, extract richer context
    if full_file_content and not file_diff.is_deleted:
        changed_lines = get_changed_line_numbers(file_diff)

        # Find functions that contain changes
        function_boundaries = find_function_boundaries(
            full_file_content, file_diff.language
        )

        lines = full_file_content.split("\n")
        for func_name, func_start, func_end in function_boundaries:
            # Check if any changed line falls within this function
            if any(func_start <= ln <= func_end for ln in changed_lines):
                # Extract function source code
                func_lines = lines[func_start - 1 : func_end]
                context.changed_functions.append(
                    FunctionContext(
                        name=func_name,
                        start_line=func_start,
                        end_line=func_end,
                        source="\n".join(func_lines),
                    )
                )

        # Extract surrounding context (nearby lines around changes)
        context.surrounding_context = extract_surrounding_context(
            full_file_content, changed_lines
        )

    return context


def build_review_context(
    file_diffs: list[FileDiff],
    file_contents: dict[str, str]
) -> list[FileContext]:
    """
    Build context for all changed files in a commit.
    
    This is the entry point called by the review service.
    It processes each changed file and returns enriched context
    ready to be sent to the AI agents.
    
    Args:
        file_diffs: List of parsed file diffs from the commit
        file_contents: Dict mapping file paths to their full content
        
    Returns:
        List of FileContext objects, one per changed file
    """
    contexts: list[FileContext] = []

    for file_diff in file_diffs:
        # Skip binary files — agents can't review images, etc.
        if file_diff.is_binary:
            continue

        # Get full file content if available
        full_content = file_contents.get(file_diff.file_path)

        # Build enriched context for this file
        context = build_file_context(file_diff, full_content)
        contexts.append(context)

    return contexts


def format_context_for_agent(file_contexts: list[FileContext]) -> str:
    """
    Format the enriched context into a readable string for AI agents.
    
    This creates a structured text prompt that gives agents:
    1. File overview (path, language, status)
    2. The raw diff (what changed)
    3. Changed function bodies (full context)
    4. Surrounding context lines
    
    Args:
        file_contexts: List of FileContext objects
        
    Returns:
        Formatted string ready to be inserted into agent prompts
    """
    if not file_contexts:
        return "No code changes to review."

    sections: list[str] = []

    for ctx in file_contexts:
        section = []
        section.append(f"═══ File: {ctx.file_path} ({ctx.language or 'unknown'}) ═══")

        # File status indicator
        if ctx.is_new:
            section.append("📄 Status: NEW FILE")
        elif ctx.is_deleted:
            section.append("🗑️ Status: DELETED FILE")
        else:
            section.append("✏️ Status: MODIFIED")

        # 1. The raw diff (most important)
        section.append("\n── Changes (Diff) ──")
        section.append(ctx.diff_content)

        # 2. Changed functions (if available)
        if ctx.changed_functions:
            section.append("\n── Changed Functions (Full Context) ──")
            for func in ctx.changed_functions:
                section.append(
                    f"\n▸ {func.name} (lines {func.start_line}-{func.end_line}):"
                )
                section.append(func.source)

        # 3. Surrounding context (if available)
        if ctx.surrounding_context:
            section.append("\n── Surrounding Context ──")
            section.append(ctx.surrounding_context)

        sections.append("\n".join(section))

    return "\n\n".join(sections)
