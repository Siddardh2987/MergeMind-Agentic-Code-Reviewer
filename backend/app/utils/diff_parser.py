"""
MergeMind — Diff Parser

Parses GitHub's unified diff format into structured data.
Extracts file paths, line ranges, and changed content for each file in the diff.
"""

import re
from dataclasses import dataclass, field


@dataclass
class DiffHunk:
    """
    Represents a single hunk (block of changes) within a file diff.
    
    A hunk corresponds to one @@ ... @@ section in the unified diff format.
    It contains the specific line range and the actual changed lines.
    """
    # Starting line number in the old (pre-change) file
    old_start: int = 0
    # Number of lines in the old version covered by this hunk
    old_count: int = 0
    # Starting line number in the new (post-change) file
    new_start: int = 0
    # Number of lines in the new version covered by this hunk
    new_count: int = 0
    # Lines added in this hunk (without the '+' prefix)
    added_lines: list[str] = field(default_factory=list)
    # Lines removed in this hunk (without the '-' prefix)
    removed_lines: list[str] = field(default_factory=list)
    # All lines in the hunk (context + changes), preserving order
    content: str = ""


@dataclass
class FileDiff:
    """
    Represents all changes to a single file in the commit.
    
    Contains the file path, whether it's a new/deleted/modified file,
    and all the hunks (change blocks) within it.
    """
    # File path (e.g., "src/utils/helper.py")
    file_path: str = ""
    # Previous file path (for renames)
    old_file_path: str = ""
    # Whether this file was newly added
    is_new: bool = False
    # Whether this file was deleted
    is_deleted: bool = False
    # Whether this is a binary file (we skip binary files)
    is_binary: bool = False
    # Detected programming language based on file extension
    language: str = ""
    # List of change hunks in this file
    hunks: list[DiffHunk] = field(default_factory=list)


# ── Language Detection ────────────────────────────────────────────────
# Maps file extensions to language names for better agent context
EXTENSION_TO_LANGUAGE = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript-react",
    ".jsx": "javascript-react",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".r": "r",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".sh": "bash",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".xml": "xml",
    ".md": "markdown",
    ".dockerfile": "dockerfile",
    ".tf": "terraform",
}


def detect_language(file_path: str) -> str:
    """
    Detect programming language from file extension.
    Returns empty string if extension is not recognized.
    """
    # Handle Dockerfile specifically (no extension)
    if file_path.lower().endswith("dockerfile"):
        return "dockerfile"

    # Extract extension and look up language
    dot_index = file_path.rfind(".")
    if dot_index == -1:
        return ""

    extension = file_path[dot_index:].lower()
    return EXTENSION_TO_LANGUAGE.get(extension, "")


def parse_diff(raw_diff: str) -> list[FileDiff]:
    """
    Parse a unified diff string into a list of FileDiff objects.
    
    This handles GitHub's diff format which looks like:
    
        diff --git a/path/to/file b/path/to/file
        index abc123..def456 100644
        --- a/path/to/file
        +++ b/path/to/file
        @@ -10,5 +10,7 @@ def some_function():
             context line
        -    removed line
        +    added line
    
    Args:
        raw_diff: The raw unified diff string from GitHub's API
        
    Returns:
        List of FileDiff objects, one per changed file
    """
    if not raw_diff or not raw_diff.strip():
        return []

    file_diffs: list[FileDiff] = []
    current_file: FileDiff | None = None
    current_hunk: DiffHunk | None = None
    hunk_lines: list[str] = []

    # Regex patterns for parsing diff components
    # Matches: diff --git a/path/to/file b/path/to/file
    file_header_pattern = re.compile(r"^diff --git a/(.+?) b/(.+?)$")
    # Matches: @@ -10,5 +10,7 @@ optional context
    hunk_header_pattern = re.compile(
        r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@"
    )

    for line in raw_diff.split("\n"):
        # ── Check for new file header ─────────────────────────────────
        file_match = file_header_pattern.match(line)
        if file_match:
            # Save previous hunk if exists
            if current_hunk and current_file:
                current_hunk.content = "\n".join(hunk_lines)
                current_file.hunks.append(current_hunk)
                hunk_lines = []

            # Save previous file if exists
            if current_file:
                file_diffs.append(current_file)

            # Start new file
            old_path = file_match.group(1)
            new_path = file_match.group(2)
            current_file = FileDiff(
                file_path=new_path,
                old_file_path=old_path,
                language=detect_language(new_path),
            )
            current_hunk = None
            continue

        # Skip if no current file is being parsed
        if current_file is None:
            continue

        # ── Detect new/deleted/binary files ───────────────────────────
        if line.startswith("new file mode"):
            current_file.is_new = True
            continue
        if line.startswith("deleted file mode"):
            current_file.is_deleted = True
            continue
        if line.startswith("Binary files"):
            current_file.is_binary = True
            continue

        # Skip --- and +++ headers (we already have paths from diff --git)
        if line.startswith("--- ") or line.startswith("+++ "):
            continue
        # Skip index lines
        if line.startswith("index "):
            continue

        # ── Check for hunk header ─────────────────────────────────────
        hunk_match = hunk_header_pattern.match(line)
        if hunk_match:
            # Save previous hunk if exists
            if current_hunk:
                current_hunk.content = "\n".join(hunk_lines)
                current_file.hunks.append(current_hunk)
                hunk_lines = []

            # Start new hunk with parsed line ranges
            current_hunk = DiffHunk(
                old_start=int(hunk_match.group(1)),
                old_count=int(hunk_match.group(2) or "1"),
                new_start=int(hunk_match.group(3)),
                new_count=int(hunk_match.group(4) or "1"),
            )
            continue

        # ── Parse hunk content lines ──────────────────────────────────
        if current_hunk is not None:
            hunk_lines.append(line)

            if line.startswith("+") and not line.startswith("+++"):
                # Added line (strip the leading '+')
                current_hunk.added_lines.append(line[1:])
            elif line.startswith("-") and not line.startswith("---"):
                # Removed line (strip the leading '-')
                current_hunk.removed_lines.append(line[1:])

    # ── Save the last hunk and file ───────────────────────────────────
    if current_hunk and current_file:
        current_hunk.content = "\n".join(hunk_lines)
        current_file.hunks.append(current_hunk)

    if current_file:
        file_diffs.append(current_file)

    return file_diffs


def get_changed_line_numbers(file_diff: FileDiff) -> list[int]:
    """
    Extract the line numbers that were changed (added/modified) in the new version.
    
    This is useful for mapping changes to function boundaries —
    we need to know which lines were touched to find the enclosing functions.
    
    Args:
        file_diff: A FileDiff object for a single file
        
    Returns:
        Sorted list of line numbers (1-indexed) that were added or modified
    """
    changed_lines: list[int] = []

    for hunk in file_diff.hunks:
        # Track the current line number in the new file
        current_line = hunk.new_start

        for line in hunk.content.split("\n"):
            if line.startswith("+"):
                # This line was added — record its line number
                changed_lines.append(current_line)
                current_line += 1
            elif line.startswith("-"):
                # This line was removed — doesn't exist in new file, skip
                pass
            else:
                # Context line — exists in both old and new, advance counter
                current_line += 1

    return sorted(set(changed_lines))
