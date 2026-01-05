#!/usr/bin/env python3
"""
Extract relevant sections from long-task-progress.md for session startup.

Default: header sections (Overview, Key Decisions, Current State) + last 3 sessions
Use -n N for more sessions, --all for everything.
"""

import argparse
import re
import sys
from pathlib import Path


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


def parse_progress_file(content: str) -> tuple[str, list[tuple[str, str]]]:
    """
    Parse long-task-progress.md into header and sessions.

    Returns:
        (header_content, [(session_title, session_content), ...])
    """
    # Remove HTML comments (including template blocks)
    content_no_comments = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)

    # Split at "## Session Log" or first "### Session"
    session_log_match = re.search(r'^## Session Log\s*$', content_no_comments, re.MULTILINE)

    if session_log_match:
        header = content_no_comments[:session_log_match.start()].rstrip()
        sessions_content = content_no_comments[session_log_match.end():]
    else:
        # No "## Session Log" header, look for first session directly
        first_session = re.search(r'^### Session \d+', content_no_comments, re.MULTILINE)
        if first_session:
            header = content_no_comments[:first_session.start()].rstrip()
            sessions_content = content_no_comments[first_session.start():]
        else:
            # No sessions found
            return content_no_comments, []

    # Parse individual sessions
    session_pattern = re.compile(r'^### Session (\d+.*?)(?=^### Session |\Z)', re.MULTILINE | re.DOTALL)
    sessions = []

    for match in session_pattern.finditer(sessions_content):
        session_text = match.group(0).strip()
        # Skip empty or template sessions
        if not session_text or 'YYYY-MM-DD' in session_text:
            continue
        # Extract title from first line
        first_line = session_text.split('\n')[0]
        title = first_line.replace('### ', '').strip()
        sessions.append((title, session_text))

    return header, sessions


def extract_session_number(title: str) -> int | None:
    """Extract session number from title like 'Session 5 | 2024-12-18 | ...'"""
    match = re.match(r'Session\s+(\d+)', title)
    return int(match.group(1)) if match else None


def format_session_list(sessions: list[tuple[str, str]]) -> str:
    """Format a compact list of all sessions for quick scanning."""
    lines = [f"[{len(sessions)} sessions found]\n"]
    for title, content in sessions:
        # Extract first line of goal/accomplished if present
        summary = ""
        for marker in ['#### Goal', '**Goal**:', 'Goal:']:
            if marker in content:
                idx = content.find(marker)
                rest = content[idx + len(marker):].strip()
                summary = rest.split('\n')[0].strip()[:60]
                break
        
        session_num = extract_session_number(title)
        if session_num:
            lines.append(f"  {session_num:3d}. {title[:50]}{'...' if len(title) > 50 else ''}")
        else:
            lines.append(f"       {title[:50]}{'...' if len(title) > 50 else ''}")
        if summary:
            lines.append(f"       └─ {summary}...")
    
    lines.append(f"\n[Use --session N to read a specific session]")
    return '\n'.join(lines)


def format_single_session(sessions: list[tuple[str, str]], session_num: int) -> str:
    """Format a single session by number."""
    for title, content in sessions:
        if extract_session_number(title) == session_num:
            return f"[Session {session_num}]\n\n{content}"
    
    # Session not found - show available
    available = [extract_session_number(t) for t, _ in sessions]
    available = [n for n in available if n is not None]
    return f"Error: Session {session_num} not found. Available: {', '.join(map(str, sorted(available)))}"


def format_output(header: str, sessions: list[tuple[str, str]],
                  num_sessions: int | None, show_all: bool) -> str:
    """Format the output with header and selected sessions."""
    total_sessions = len(sessions)

    if show_all or num_sessions is None or num_sessions >= total_sessions:
        selected_sessions = sessions
        omitted = 0
    else:
        selected_sessions = sessions[-num_sessions:]
        omitted = total_sessions - num_sessions

    output_parts = []

    # Status line
    if total_sessions > 0:
        if omitted > 0:
            first_shown = total_sessions - len(selected_sessions) + 1
            output_parts.append(f"[Showing: header + sessions {first_shown}-{total_sessions} of {total_sessions}]\n")
        else:
            output_parts.append(f"[Showing: header + all {total_sessions} sessions]\n")
    else:
        output_parts.append("[Showing: header only (no sessions found)]\n")

    # Header
    output_parts.append(header)

    # Sessions
    if selected_sessions:
        output_parts.append("\n\n---\n\n## Session Log\n")
        for _, session_content in selected_sessions:
            output_parts.append(f"\n{session_content}\n")

    # Hint about more content
    if omitted > 0:
        output_parts.append(f"\n---\n[{omitted} earlier session(s) available: -n N or --all]")

    return ''.join(output_parts)


def main():
    parser = argparse.ArgumentParser(
        description="Extract relevant sections from long-task-progress.md",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 read_progress.py              # header + last 3 sessions
  python3 read_progress.py -n 5         # header + last 5 sessions
  python3 read_progress.py --all        # everything
  python3 read_progress.py --list       # list all sessions (for quick scan)
  python3 read_progress.py --session 12 # read specific session by number
        """
    )
    parser.add_argument('-n', '--sessions', type=int, default=3,
                        help='Number of recent sessions to show (default: 3)')
    parser.add_argument('--all', action='store_true',
                        help='Show all sessions')
    parser.add_argument('--list', '-l', action='store_true',
                        help='List all sessions with titles (compact view)')
    parser.add_argument('--session', '-s', type=int,
                        help='Show a specific session by number')
    parser.add_argument('--file', type=Path,
                        help='Path to long-task-progress.md (default: auto-detect)')

    args = parser.parse_args()

    # Find progress file
    if args.file:
        progress_file = args.file
    else:
        progress_file = find_progress_file()

    if not progress_file or not progress_file.exists():
        print("Error: long-task-progress.md not found", file=sys.stderr)
        print("Run from a project directory with long-task-progress.md, or use --file", file=sys.stderr)
        sys.exit(1)

    # Read and parse
    content = progress_file.read_text()
    header, sessions = parse_progress_file(content)

    # Handle --list flag
    if args.list:
        print(format_session_list(sessions))
        return

    # Handle --session flag
    if args.session:
        print(format_single_session(sessions, args.session))
        return

    # Default: Format output with header and recent sessions
    output = format_output(header, sessions, args.sessions, args.all)
    print(output)


if __name__ == "__main__":
    main()
