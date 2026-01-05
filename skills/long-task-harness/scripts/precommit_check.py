#!/usr/bin/env python3
"""
Shared pre-commit check for long-task-harness.

Outputs metadata and warns if long-task-progress.md is not staged.
Exit code 0 so commits proceed.
"""

import subprocess
import sys


def get_git_metadata() -> dict:
    """Gather git metadata for the current staged changes."""
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
    )
    staged_files = staged.stdout.strip().split("\n") if staged.stdout.strip() else []

    diffstat = subprocess.run(
        ["git", "diff", "--cached", "--stat"],
        capture_output=True,
        text=True,
    )

    last_commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
    )
    last_hash = last_commit.stdout.strip() if last_commit.returncode == 0 else "unknown"

    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True,
        text=True,
    )
    branch_name = branch.stdout.strip() if branch.returncode == 0 else "unknown"

    file_changes = []
    for line in diffstat.stdout.strip().split("\n")[:-1]:  # Skip summary line
        if line.strip():
            file_changes.append(line.strip())

    return {
        "staged_files": staged_files,
        "last_hash": last_hash,
        "branch": branch_name,
        "file_changes": file_changes,
    }


def format_metadata(meta: dict) -> str:
    """Format metadata for display."""
    lines = [
        "",
        "Session Metadata (for long-task-progress.md):",
        f"  Commits: {meta['last_hash']}..HEAD",
        f"  Branch: {meta['branch']}",
        "  Files Changed:",
    ]
    for change in meta["file_changes"]:
        lines.append(f"    {change}")
    return "\n".join(lines)


def is_progress_staged(staged_files: list) -> bool:
    """Check if progress file is staged (supports both old and new locations)."""
    progress_paths = [
        "long-task-progress.md",
        ".long-task-harness/long-task-progress.md",
    ]
    return any(path in staged_files for path in progress_paths)


def run_check() -> int:
    """Run the pre-commit check, always allowing commit to proceed."""
    meta = get_git_metadata()
    metadata_str = format_metadata(meta)
    progress_staged = is_progress_staged(meta["staged_files"])

    if progress_staged:
        print(f"[OK] long-task-progress.md is staged.{metadata_str}", file=sys.stderr)
        return 0

    print(
        f"""⚠️ Long-task-harness: .long-task-harness/long-task-progress.md is not staged.
   If relevant, also update features.json with completed/failed features.
   Update these files before committing to maintain session continuity.
{metadata_str}""",
        file=sys.stderr,
    )
    return 0


def main() -> int:
    return run_check()


if __name__ == "__main__":
    sys.exit(main())
