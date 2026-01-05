#!/usr/bin/env python3
"""
Generate session metadata for long-task-progress.md.

Outputs git metadata (commits, branch, files changed) in a format
ready to paste into a session entry.

Usage:
  python3 session_metadata.py           # Metadata for staged changes
  python3 session_metadata.py --since   # Metadata since last progress.md update
"""

import argparse
import subprocess
import sys
from pathlib import Path


def run_git(*args) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        ['git'] + list(args),
        capture_output=True,
        text=True
    )
    return result.stdout.strip() if result.returncode == 0 else ''


def find_progress_file() -> Path | None:
    """Find long-task-progress.md in current directory or parents.
    
    Checks .long-task-harness/ first (new location), then falls back to
    project root (legacy location).
    """
    cwd = Path.cwd()
    for path in [cwd, *cwd.parents]:
        # Check new location first
        new_location = path / ".long-task-harness" / "long-task-progress.md"
        if new_location.exists():
            return new_location
        # Fall back to legacy location
        legacy_location = path / "long-task-progress.md"
        if legacy_location.exists():
            return legacy_location
    return None


def get_last_progress_commit() -> str | None:
    """Get the commit hash where long-task-progress.md was last modified.
    
    Checks both new and legacy locations.
    """
    # Try new location first
    for path in ['.long-task-harness/long-task-progress.md', 'long-task-progress.md']:
        result = subprocess.run(
            ['git', 'log', '-1', '--format=%h', '--', path],
            capture_output=True,
            text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    return None


def get_metadata_staged() -> dict:
    """Get metadata for currently staged changes."""
    # Staged files
    staged_files = run_git('diff', '--cached', '--name-only').split('\n')
    staged_files = [f for f in staged_files if f]

    # Diff stats for staged
    diffstat = run_git('diff', '--cached', '--stat')
    file_changes = []
    for line in diffstat.split('\n')[:-1]:  # Skip summary
        if line.strip():
            file_changes.append(line.strip())

    return {
        'last_hash': run_git('rev-parse', '--short', 'HEAD'),
        'branch': run_git('branch', '--show-current'),
        'file_changes': file_changes,
        'commit_range': f"{run_git('rev-parse', '--short', 'HEAD')}..staged"
    }


def get_metadata_since_progress() -> dict:
    """Get metadata for changes since last progress.md update."""
    last_progress_commit = get_last_progress_commit()
    
    if not last_progress_commit:
        print("Warning: No previous commits found for long-task-progress.md", file=sys.stderr)
        last_progress_commit = run_git('rev-list', '--max-parents=0', 'HEAD')  # First commit

    current_hash = run_git('rev-parse', '--short', 'HEAD')
    
    # Get diff stats since last progress commit
    diffstat = run_git('diff', '--stat', f'{last_progress_commit}..HEAD')
    file_changes = []
    for line in diffstat.split('\n')[:-1]:  # Skip summary
        if line.strip():
            file_changes.append(line.strip())

    # Get commit count
    commit_count = run_git('rev-list', '--count', f'{last_progress_commit}..HEAD')

    return {
        'last_hash': last_progress_commit,
        'current_hash': current_hash,
        'branch': run_git('branch', '--show-current'),
        'file_changes': file_changes,
        'commit_range': f"{last_progress_commit}..{current_hash}",
        'commit_count': commit_count
    }


def format_metadata(meta: dict, mode: str) -> str:
    """Format metadata for display."""
    lines = [
        "Session Metadata (copy to long-task-progress.md):",
        "=" * 50,
        ""
    ]

    if mode == 'since':
        lines.append(f"Commits: {meta['commit_range']} ({meta.get('commit_count', '?')} commits)")
    else:
        lines.append(f"Commits: {meta['commit_range']}")
    
    lines.append(f"Branch: {meta['branch']}")
    lines.append("")
    lines.append("Files Changed:")
    
    for change in meta['file_changes']:
        lines.append(f"  - {change}")

    if not meta['file_changes']:
        lines.append("  (no changes)")

    lines.append("")
    lines.append("=" * 50)
    
    # Also output in template format
    lines.append("")
    lines.append("Template format for session header:")
    lines.append(f"### Session N | YYYY-MM-DD | Commits: {meta['commit_range']}")
    lines.append("")
    lines.append("#### Metadata")
    lines.append("- **Features**: [feature-id (status)]")
    lines.append("- **Files Changed**:")
    for change in meta['file_changes'][:5]:  # First 5
        # Parse the diffstat format: "file.py | 10 ++"
        parts = change.split('|')
        if len(parts) >= 2:
            filename = parts[0].strip()
            stats = parts[1].strip()
            lines.append(f"  - `{filename}` ({stats})")
    if len(meta['file_changes']) > 5:
        lines.append(f"  - ... and {len(meta['file_changes']) - 5} more files")

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate session metadata for long-task-progress.md"
    )
    parser.add_argument(
        '--since', '-s',
        action='store_true',
        help='Show changes since last long-task-progress.md update (default: staged changes)'
    )

    args = parser.parse_args()

    # Check we're in a git repo
    if not run_git('rev-parse', '--git-dir'):
        print("Error: Not in a git repository", file=sys.stderr)
        sys.exit(1)

    if args.since:
        meta = get_metadata_since_progress()
        mode = 'since'
    else:
        meta = get_metadata_staged()
        mode = 'staged'

    print(format_metadata(meta, mode))


if __name__ == "__main__":
    main()
