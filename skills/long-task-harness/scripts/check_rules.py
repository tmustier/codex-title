#!/usr/bin/env python3
"""
Hookify-style declarative rule checker for long-task-harness.

Checks operations against rules defined in .long-task-harness/rules/*.md files.

Rule file format (.long-task-harness/rules/my-rule.md):
```markdown
---
name: block-dangerous-rm
enabled: true
event: bash           # bash, file, commit, any
pattern: rm\\s+-rf
action: warn          # warn or block
---

⚠️ **Dangerous rm command detected!**

Please verify the path before proceeding.
```

Usage:
  # Check a bash command
  python3 check_rules.py bash "rm -rf /tmp/test"
  
  # Check a file edit
  python3 check_rules.py file path/to/file.py "new content"
  
  # Check before commit
  python3 check_rules.py commit
  
  # List all rules
  python3 check_rules.py list
"""

import argparse
import re
import sys
import yaml
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Rule:
    """A declarative rule."""
    name: str
    enabled: bool
    event: str  # bash, file, commit, any
    pattern: str | None
    action: str  # warn, block
    message: str
    file_path: Path
    
    # Optional conditions
    file_pattern: str | None = None  # For file events: match file path


def get_harness_dir() -> Path | None:
    """Find .long-task-harness directory."""
    cwd = Path.cwd()
    for path in [cwd, *cwd.parents]:
        harness_dir = path / ".long-task-harness"
        if harness_dir.exists():
            return harness_dir
    return None


def get_rules_dir() -> Path:
    """Get or create rules directory."""
    harness_dir = get_harness_dir()
    if not harness_dir:
        harness_dir = Path.cwd() / ".long-task-harness"
        harness_dir.mkdir(exist_ok=True)
    
    rules_dir = harness_dir / "rules"
    rules_dir.mkdir(exist_ok=True)
    return rules_dir


def parse_rule_file(file_path: Path) -> Rule | None:
    """Parse a rule from markdown file with YAML frontmatter."""
    content = file_path.read_text()
    
    # Split frontmatter and body
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
    """Load all enabled rules, optionally filtered by event type."""
    rules_dir = get_rules_dir()
    rules = []
    
    for rule_file in rules_dir.glob("*.md"):
        rule = parse_rule_file(rule_file)
        if rule and rule.enabled:
            if event_filter is None or rule.event in (event_filter, "any"):
                rules.append(rule)
    
    return rules


def check_pattern(pattern: str, text: str) -> bool:
    """Check if pattern matches text (regex)."""
    try:
        return bool(re.search(pattern, text, re.IGNORECASE))
    except re.error:
        return False


def check_bash_rules(command: str) -> tuple[list[Rule], list[Rule]]:
    """Check bash command against rules. Returns (warnings, blockers)."""
    rules = load_rules("bash")
    warnings = []
    blockers = []
    
    for rule in rules:
        if rule.pattern and check_pattern(rule.pattern, command):
            if rule.action == "block":
                blockers.append(rule)
            else:
                warnings.append(rule)
    
    return warnings, blockers


def check_file_rules(file_path: str, content: str) -> tuple[list[Rule], list[Rule]]:
    """Check file edit against rules. Returns (warnings, blockers)."""
    rules = load_rules("file")
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


def check_commit_rules() -> tuple[list[Rule], list[Rule]]:
    """Check pre-commit rules. Returns (warnings, blockers)."""
    harness_dir = get_harness_dir()
    warnings = []
    blockers = []
    
    if not harness_dir:
        return warnings, blockers
    
    rules = load_rules("commit")
    
    # Check if progress file is staged (using existing pre-commit logic)
    import subprocess
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True, timeout=5
        )
        staged_files = result.stdout.strip().split('\n') if result.returncode == 0 else []
    except (subprocess.TimeoutExpired, FileNotFoundError):
        staged_files = []
    
    progress_staged = any("long-task-progress.md" in f for f in staged_files)
    
    for rule in rules:
        # Special handling for progress-not-staged rule
        if rule.pattern == "progress-not-staged" and not progress_staged:
            if rule.action == "block":
                blockers.append(rule)
            else:
                warnings.append(rule)
            continue
        
        # Generic pattern matching against staged files
        if rule.pattern:
            for file in staged_files:
                if check_pattern(rule.pattern, file):
                    if rule.action == "block":
                        blockers.append(rule)
                    else:
                        warnings.append(rule)
                    break
    
    return warnings, blockers


def format_rule_output(rule: Rule) -> str:
    """Format a rule match for output."""
    icon = "🛑" if rule.action == "block" else "⚠️"
    return f"{icon} [{rule.name}]\n{rule.message}"


def list_rules():
    """List all rules."""
    rules_dir = get_rules_dir()
    rules = []
    
    for rule_file in rules_dir.glob("*.md"):
        rule = parse_rule_file(rule_file)
        if rule:
            rules.append(rule)
    
    if not rules:
        print("No rules found.")
        print(f"\nCreate rules in: {rules_dir}/")
        print("\nExample rule file (warn-console-log.md):")
        print("""---
name: warn-console-log
enabled: true
event: file
file_pattern: \\.tsx?$
pattern: console\\.log\\(
action: warn
---

🐛 **Debug code detected**

Remember to remove console.log before committing.
""")
        return
    
    print(f"Rules directory: {rules_dir}\n")
    
    for rule in rules:
        status = "✓" if rule.enabled else "○"
        action_icon = "🛑" if rule.action == "block" else "⚠️"
        print(f"{status} {action_icon} {rule.name}")
        print(f"   Event: {rule.event}")
        if rule.pattern:
            print(f"   Pattern: {rule.pattern}")
        if rule.file_pattern:
            print(f"   File: {rule.file_pattern}")
        print()


def create_default_rules():
    """Create default rule files if none exist."""
    rules_dir = get_rules_dir()
    
    # Progress not staged rule
    progress_rule = rules_dir / "warn-progress-not-staged.md"
    if not progress_rule.exists():
        progress_rule.write_text("""---
name: warn-progress-not-staged
enabled: true
event: commit
pattern: progress-not-staged
action: warn
---

📝 **Progress file not staged**

Consider updating .long-task-harness/long-task-progress.md before committing.
This helps maintain session continuity.
""")
    
    # Dangerous rm rule (example, disabled by default)
    rm_rule = rules_dir / "warn-dangerous-rm.md.example"
    if not rm_rule.exists():
        rm_rule.write_text("""---
name: warn-dangerous-rm
enabled: true
event: bash
pattern: rm\\s+-rf
action: warn
---

⚠️ **Dangerous rm command detected!**

Please verify the path is correct before proceeding.
Consider using a safer approach or making a backup.
""")


def main():
    parser = argparse.ArgumentParser(
        description="Check operations against declarative rules",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # bash command
    bash_parser = subparsers.add_parser("bash", help="Check a bash command")
    bash_parser.add_argument("cmd", help="The command to check")
    
    # file command
    file_parser = subparsers.add_parser("file", help="Check a file edit")
    file_parser.add_argument("path", help="File path")
    file_parser.add_argument("content", nargs="?", default="", help="New content (or pipe via stdin)")
    
    # commit command
    subparsers.add_parser("commit", help="Check pre-commit rules")
    
    # list command
    subparsers.add_parser("list", help="List all rules")
    
    # init command
    subparsers.add_parser("init", help="Create default rules")
    
    args = parser.parse_args()
    
    if args.command == "bash":
        warnings, blockers = check_bash_rules(args.cmd)
        
        for rule in warnings:
            print(format_rule_output(rule))
            print()
        
        for rule in blockers:
            print(format_rule_output(rule))
            print()
        
        if blockers:
            sys.exit(1)
        sys.exit(0)
    
    elif args.command == "file":
        content = args.content
        if not content and not sys.stdin.isatty():
            content = sys.stdin.read()
        
        warnings, blockers = check_file_rules(args.path, content)
        
        for rule in warnings:
            print(format_rule_output(rule))
            print()
        
        for rule in blockers:
            print(format_rule_output(rule))
            print()
        
        if blockers:
            sys.exit(1)
        sys.exit(0)
    
    elif args.command == "commit":
        warnings, blockers = check_commit_rules()
        
        for rule in warnings:
            print(format_rule_output(rule))
            print()
        
        for rule in blockers:
            print(format_rule_output(rule))
            print()
        
        if blockers:
            sys.exit(1)
        sys.exit(0)
    
    elif args.command == "list":
        list_rules()
    
    elif args.command == "init":
        create_default_rules()
        print("Default rules created. Run 'list' to see them.")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
