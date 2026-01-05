#!/usr/bin/env python3
"""
Git add wrapper that checks rules before staging files.

Use instead of `git add` to get warnings/blocks before staging.

Usage:
  python3 git_add.py file1.py file2.ts    # Stage specific files
  python3 git_add.py .                     # Stage all
  python3 git_add.py -A                    # Stage all (including deletions)
  python3 git_add.py --check-only file.py  # Check without staging
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Import from check_rules if available, otherwise inline the logic
try:
    from check_rules import load_rules, check_pattern, Rule
except ImportError:
    import json
    import yaml
    from dataclasses import dataclass
    
    @dataclass
    class Rule:
        name: str
        enabled: bool
        event: str
        pattern: str | None
        action: str
        message: str
        file_path: Path
        file_pattern: str | None = None
    
    def get_harness_dir() -> Path | None:
        cwd = Path.cwd()
        for path in [cwd, *cwd.parents]:
            harness_dir = path / ".long-task-harness"
            if harness_dir.exists():
                return harness_dir
        return None
    
    def parse_rule_file(file_path: Path) -> Rule | None:
        content = file_path.read_text()
        if not content.startswith("---"):
            return None
        parts = content.split("---", 2)
        if len(parts) < 3:
            return None
        try:
            frontmatter = yaml.safe_load(parts[1])
            message = parts[2].strip()
        except yaml.YAMLError:
            return None
        if not frontmatter:
            return None
        return Rule(
            name=frontmatter.get("name", file_path.stem),
            enabled=frontmatter.get("enabled", True),
            event=frontmatter.get("event", "any"),
            pattern=frontmatter.get("pattern"),
            action=frontmatter.get("action", "warn"),
            message=message,
            file_path=file_path,
            file_pattern=frontmatter.get("file_pattern")
        )
    
    def load_rules(event_filter: str | None = None) -> list[Rule]:
        harness_dir = get_harness_dir()
        if not harness_dir:
            return []
        rules_dir = harness_dir / "rules"
        if not rules_dir.exists():
            return []
        rules = []
        for rule_file in rules_dir.glob("*.md"):
            rule = parse_rule_file(rule_file)
            if rule and rule.enabled:
                if event_filter is None or rule.event in (event_filter, "any"):
                    rules.append(rule)
        return rules
    
    def check_pattern(pattern: str, text: str) -> bool:
        try:
            return bool(re.search(pattern, text, re.IGNORECASE))
        except re.error:
            return False


def get_file_content(file_path: str) -> str | None:
    """Get file content, return None if file doesn't exist, is a directory, or is binary."""
    path = Path(file_path)
    if not path.exists() or path.is_dir():
        return None
    try:
        return path.read_text()
    except (UnicodeDecodeError, PermissionError):
        return None


def check_file_rules(file_path: str, content: str) -> tuple[list, list]:
    """Check file against staging rules. Returns (warnings, blockers)."""
    rules = load_rules("file") + load_rules("stage")
    warnings = []
    blockers = []
    
    for rule in rules:
        # Check file path pattern if specified
        if rule.file_pattern and not check_pattern(rule.file_pattern, file_path):
            continue
        
        # Check content pattern
        if rule.pattern and check_pattern(rule.pattern, content):
            if rule.action == "block":
                blockers.append(rule)
            else:
                warnings.append(rule)
    
    return warnings, blockers


def check_progress_not_staged(files_to_stage: list[str]) -> tuple[list, list]:
    """Check if progress file should be staged too."""
    rules = load_rules("commit")
    warnings = []
    blockers = []
    
    # Check if any code files are being staged without progress
    code_extensions = {'.py', '.js', '.ts', '.tsx', '.jsx', '.go', '.rs', '.java', '.rb'}
    staging_code = any(Path(f).suffix in code_extensions for f in files_to_stage)
    progress_included = any('long-task-progress.md' in f for f in files_to_stage)
    
    if staging_code and not progress_included:
        for rule in rules:
            if rule.pattern == "progress-not-staged":
                if rule.action == "block":
                    blockers.append(rule)
                else:
                    warnings.append(rule)
    
    return warnings, blockers


def format_rule_output(rule, file_path: str = None) -> str:
    """Format a rule match for output."""
    icon = "🛑" if rule.action == "block" else "⚠️"
    file_info = f" ({file_path})" if file_path else ""
    return f"{icon} [{rule.name}]{file_info}\n{rule.message}"


def get_files_to_stage(args: list[str]) -> list[str]:
    """Expand git add arguments to list of files."""
    if not args:
        return []
    
    # Handle special cases
    if args == ['.'] or args == ['-A'] or args == ['--all']:
        # Get all modified/untracked files
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            return []
        
        files = []
        for line in result.stdout.strip().split('\n'):
            if line and len(line) > 3:
                # Status is first 2 chars, then space, then filename
                filename = line[3:].strip()
                # Handle renamed files (old -> new)
                if ' -> ' in filename:
                    filename = filename.split(' -> ')[1]
                files.append(filename)
        return files
    
    # Otherwise, expand globs and return files
    files = []
    for arg in args:
        if arg.startswith('-'):
            continue
        path = Path(arg)
        if path.is_file():
            files.append(str(path))
        elif path.is_dir():
            # Get all files in directory
            for f in path.rglob('*'):
                if f.is_file():
                    files.append(str(f))
        else:
            # Might be a glob
            files.extend(str(f) for f in Path('.').glob(arg) if f.is_file())
    
    return files


def main():
    parser = argparse.ArgumentParser(
        description="Git add with rule checking",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('files', nargs='*', help='Files to stage')
    parser.add_argument('--check-only', '-c', action='store_true',
                        help='Check rules without staging')
    parser.add_argument('-A', '--all', action='store_true',
                        help='Stage all changes (like git add -A)')
    parser.add_argument('-f', '--force', action='store_true',
                        help='Stage even if rules would block')
    
    args = parser.parse_args()
    
    # Build file list
    if args.all:
        files_to_stage = get_files_to_stage(['-A'])
    else:
        files_to_stage = get_files_to_stage(args.files)
    
    if not files_to_stage:
        print("No files to stage.")
        return
    
    all_warnings = []
    all_blockers = []
    
    # Check each file
    for file_path in files_to_stage:
        content = get_file_content(file_path)
        if content is None:
            continue
        
        warnings, blockers = check_file_rules(file_path, content)
        for w in warnings:
            all_warnings.append((w, file_path))
        for b in blockers:
            all_blockers.append((b, file_path))
    
    # Check progress file rule
    prog_warnings, prog_blockers = check_progress_not_staged(files_to_stage)
    for w in prog_warnings:
        all_warnings.append((w, None))
    for b in prog_blockers:
        all_blockers.append((b, None))
    
    # Output warnings
    if all_warnings:
        print("\n" + "─" * 60)
        print("STAGING WARNINGS")
        print("─" * 60 + "\n")
        for rule, file_path in all_warnings:
            print(format_rule_output(rule, file_path))
            print()
    
    # Output blockers
    if all_blockers:
        print("\n" + "─" * 60)
        print("STAGING BLOCKED")
        print("─" * 60 + "\n")
        for rule, file_path in all_blockers:
            print(format_rule_output(rule, file_path))
            print()
        
        if not args.force:
            print("Use --force to stage anyway.\n")
            sys.exit(1)
        else:
            print("--force specified, staging anyway.\n")
    
    # Stage files if not check-only
    if args.check_only:
        print(f"Would stage {len(files_to_stage)} file(s):")
        for f in files_to_stage[:10]:
            print(f"  {f}")
        if len(files_to_stage) > 10:
            print(f"  ... and {len(files_to_stage) - 10} more")
    else:
        # Actually run git add
        cmd = ['git', 'add'] + args.files
        if args.all:
            cmd = ['git', 'add', '-A']
        
        result = subprocess.run(cmd)
        if result.returncode == 0:
            print(f"✓ Staged {len(files_to_stage)} file(s)")
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()
