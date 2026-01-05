#!/usr/bin/env python3
"""
Status line generator for long-task-harness.

Outputs a compact status line showing:
- Current session number
- Active feature
- Incomplete features count
- Git branch and status
- Loop status (if active)

Usage:
  python3 status_line.py           # One-line status
  python3 status_line.py --json    # JSON output
  python3 status_line.py --full    # Multi-line detailed status
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def get_harness_dir() -> Path | None:
    """Find .long-task-harness directory."""
    cwd = Path.cwd()
    for path in [cwd, *cwd.parents]:
        harness_dir = path / ".long-task-harness"
        if harness_dir.exists():
            return harness_dir
        # Legacy location
        if (path / "long-task-progress.md").exists():
            return path
    return None


def get_current_session() -> tuple[int, str | None]:
    """Get current session number and goal from progress file."""
    harness_dir = get_harness_dir()
    if not harness_dir:
        return 0, None
    
    # Try new location first
    progress_file = harness_dir / "long-task-progress.md"
    if not progress_file.exists():
        progress_file = harness_dir / ".." / "long-task-progress.md"
    if not progress_file.exists():
        return 0, None
    
    content = progress_file.read_text()
    
    # Find highest session number
    sessions = re.findall(r'### Session (\d+)', content)
    if not sessions:
        return 0, None
    
    max_session = max(int(s) for s in sessions)
    
    # Try to get goal from latest session
    goal = None
    pattern = rf'### Session {max_session}.*?(?:#### Goal|Goal:|\*\*Goal\*\*:)\s*(.+?)(?:\n|$)'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        goal = match.group(1).strip()[:50]
    
    return max_session, goal


def get_feature_status() -> tuple[int, int, str | None]:
    """Get feature counts and current feature from features.json."""
    harness_dir = get_harness_dir()
    if not harness_dir:
        return 0, 0, None
    
    features_file = harness_dir / "features.json"
    if not features_file.exists():
        features_file = harness_dir / ".." / "features.json"
    if not features_file.exists():
        return 0, 0, None
    
    try:
        data = json.loads(features_file.read_text())
        features = data.get("features", [])
        
        total = len(features)
        incomplete = sum(1 for f in features if not f.get("passes", False))
        
        # Get first incomplete feature
        current = None
        for f in features:
            if not f.get("passes", False):
                current = f.get("id", f.get("name", ""))[:20]
                break
        
        return total, incomplete, current
    except (json.JSONDecodeError, KeyError):
        return 0, 0, None


def get_git_status() -> tuple[str, int, int, int]:
    """Get git branch and change counts."""
    try:
        # Get branch
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        branch = result.stdout.strip() if result.returncode == 0 else "?"
        
        # Get status
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=5
        )
        
        staged = 0
        unstaged = 0
        untracked = 0
        
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                index_status = line[0] if len(line) > 0 else ' '
                worktree_status = line[1] if len(line) > 1 else ' '
                
                if index_status == '?':
                    untracked += 1
                elif index_status != ' ':
                    staged += 1
                if worktree_status not in (' ', '?'):
                    unstaged += 1
        
        return branch, staged, unstaged, untracked
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "?", 0, 0, 0


def get_loop_status() -> tuple[bool, int, int, str | None]:
    """Get iteration loop status."""
    harness_dir = get_harness_dir()
    if not harness_dir:
        return False, 0, 0, None
    
    loop_file = harness_dir / "iteration-loop.json"
    if not loop_file.exists():
        return False, 0, 0, None
    
    try:
        data = json.loads(loop_file.read_text())
        return (
            True,
            data.get("iteration", 0),
            data.get("max_iterations", 0),
            data.get("completion_promise")
        )
    except (json.JSONDecodeError, KeyError):
        return False, 0, 0, None


def format_status_line() -> str:
    """Generate compact status line."""
    parts = []
    
    # Session info
    session_num, goal = get_current_session()
    if session_num > 0:
        parts.append(f"S{session_num}")
    
    # Feature info
    total, incomplete, current = get_feature_status()
    if total > 0:
        parts.append(f"F:{total - incomplete}/{total}")
        if current:
            parts.append(f"[{current}]")
    
    # Git info
    branch, staged, unstaged, untracked = get_git_status()
    git_changes = []
    if staged:
        git_changes.append(f"S:{staged}")
    if unstaged:
        git_changes.append(f"U:{unstaged}")
    if untracked:
        git_changes.append(f"?:{untracked}")
    
    git_part = branch
    if git_changes:
        git_part += f" ({','.join(git_changes)})"
    parts.append(git_part)
    
    # Loop info
    loop_active, iteration, max_iter, promise = get_loop_status()
    if loop_active:
        loop_str = f"🔄{iteration}"
        if max_iter > 0:
            loop_str += f"/{max_iter}"
        parts.append(loop_str)
    
    return " | ".join(parts)


def format_json() -> str:
    """Generate JSON status."""
    session_num, goal = get_current_session()
    total, incomplete, current = get_feature_status()
    branch, staged, unstaged, untracked = get_git_status()
    loop_active, iteration, max_iter, promise = get_loop_status()
    
    return json.dumps({
        "session": {
            "number": session_num,
            "goal": goal
        },
        "features": {
            "total": total,
            "incomplete": incomplete,
            "current": current
        },
        "git": {
            "branch": branch,
            "staged": staged,
            "unstaged": unstaged,
            "untracked": untracked
        },
        "loop": {
            "active": loop_active,
            "iteration": iteration,
            "max_iterations": max_iter,
            "promise": promise
        } if loop_active else None
    }, indent=2)


def format_full() -> str:
    """Generate detailed multi-line status."""
    session_num, goal = get_current_session()
    total, incomplete, current = get_feature_status()
    branch, staged, unstaged, untracked = get_git_status()
    loop_active, iteration, max_iter, promise = get_loop_status()
    
    lines = ["═" * 60]
    lines.append("LONG-TASK-HARNESS STATUS")
    lines.append("═" * 60)
    
    # Session
    lines.append(f"\n📋 Session: {session_num if session_num else 'None'}")
    if goal:
        lines.append(f"   Goal: {goal}")
    
    # Features
    if total > 0:
        lines.append(f"\n✓ Features: {total - incomplete}/{total} complete")
        if current:
            lines.append(f"   Current: {current}")
    
    # Git
    lines.append(f"\n🌿 Git: {branch}")
    if staged or unstaged or untracked:
        changes = []
        if staged:
            changes.append(f"{staged} staged")
        if unstaged:
            changes.append(f"{unstaged} unstaged")
        if untracked:
            changes.append(f"{untracked} untracked")
        lines.append(f"   Changes: {', '.join(changes)}")
    
    # Loop
    if loop_active:
        lines.append(f"\n🔄 Loop: Iteration {iteration}" + (f"/{max_iter}" if max_iter else ""))
        if promise:
            lines.append(f"   Promise: {promise}")
    
    lines.append("\n" + "═" * 60)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Status line for long-task-harness")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--full", action="store_true", help="Detailed multi-line output")
    
    args = parser.parse_args()
    
    if args.json:
        print(format_json())
    elif args.full:
        print(format_full())
    else:
        print(format_status_line())


if __name__ == "__main__":
    main()
