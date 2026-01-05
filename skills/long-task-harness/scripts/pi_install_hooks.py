#!/usr/bin/env python3
"""
Install Pi agent hooks for long-task-harness.

Installs hooks to ~/.pi/agent/hooks/ that:
- Track session titles from git commit messages
- Update terminal tab title on commits

Note: These hooks are for Pi agent only. Claude Code and Factory Droid have separate installers.
"""

import argparse
import shutil
from pathlib import Path


def get_script_dir():
    """Get the directory containing this script."""
    return Path(__file__).parent.resolve()


def get_pi_hooks_dir() -> Path:
    """Get the Pi agent hooks directory."""
    return Path.home() / ".pi" / "agent" / "hooks"


def get_source_hook() -> Path:
    """Get the path to the source hook file."""
    return get_script_dir().parent / "hooks" / "pi" / "resume-sessions.ts"


def install_hooks() -> bool:
    """Install Pi agent hooks."""
    hooks_dir = get_pi_hooks_dir()
    source_hook = get_source_hook()
    dest_hook = hooks_dir / "resume-sessions.ts"

    if not source_hook.exists():
        print(f"  ❌ Source hook not found: {source_hook}")
        return False

    # Create hooks directory if it doesn't exist
    hooks_dir.mkdir(parents=True, exist_ok=True)

    # Check if already installed
    if dest_hook.exists():
        # Check if it's the same file
        if dest_hook.read_text() == source_hook.read_text():
            print("  ⚠️  Hooks already installed and up to date")
            return False
        else:
            print("  ℹ️  Updating existing hook...")

    # Copy the hook file
    shutil.copy2(source_hook, dest_hook)
    print(f"  ✅ Installed Pi agent hook to {dest_hook}")
    print("  ℹ️  Restart Pi agent to activate the hook")
    return True


def uninstall_hooks() -> bool:
    """Remove Pi agent hooks."""
    dest_hook = get_pi_hooks_dir() / "resume-sessions.ts"

    if not dest_hook.exists():
        print("  ⚠️  No Pi agent hook found")
        return False

    dest_hook.unlink()
    print("  ✅ Removed Pi agent hook")
    print("  ℹ️  Restart Pi agent to deactivate the hook")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Install or uninstall long-task-harness Pi agent hooks"
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove hooks instead of installing"
    )

    args = parser.parse_args()

    if args.uninstall:
        uninstall_hooks()
    else:
        install_hooks()


if __name__ == "__main__":
    main()
