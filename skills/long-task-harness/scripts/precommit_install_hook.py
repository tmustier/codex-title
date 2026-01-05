#!/usr/bin/env python3
"""
Install/uninstall a repo-local git pre-commit hook for long-task-harness.

This is intended for agents without native hook support. It affects all commits
in the current repository clone.
"""

import argparse
import os
from pathlib import Path
import subprocess
import sys
from typing import Optional


HOOK_MARKER = "long-task-harness pre-commit hook"


def get_repo_root(project_dir: Path) -> Optional[Path]:
    result = subprocess.run(
        ["git", "-C", str(project_dir), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("  WARNING: not a git repository.", file=sys.stderr)
        return None
    return Path(result.stdout.strip())


def get_hooks_dir(project_dir: Path) -> Optional[Path]:
    repo_root = get_repo_root(project_dir)
    if repo_root is None:
        return None

    result = subprocess.run(
        ["git", "-C", str(project_dir), "rev-parse", "--git-path", "hooks"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("  WARNING: unable to locate git hooks directory.", file=sys.stderr)
        return None

    hooks_path = Path(result.stdout.strip())
    if not hooks_path.is_absolute():
        hooks_path = (repo_root / hooks_path).resolve()
    return hooks_path


def get_hook_body(script_dir: Path) -> str:
    check_script = script_dir / "precommit_check.py"
    return "\n".join(
        [
            "#!/usr/bin/env bash",
            f"# {HOOK_MARKER}",
            "# Installed by scripts/precommit_install_hook.py",
            f"python3 \"{check_script}\"",
            "",
        ]
    )


def install_hook(project_dir: Path, force: bool) -> bool:
    hooks_dir = get_hooks_dir(project_dir)
    if hooks_dir is None:
        return False

    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hooks_dir / "pre-commit"
    script_dir = Path(__file__).parent.resolve()
    hook_body = get_hook_body(script_dir)

    if hook_path.exists():
        existing = hook_path.read_text()
        if HOOK_MARKER in existing:
            print("  OK: pre-commit hook already installed.")
            return False
        if not force:
            print(
                "  WARNING: pre-commit hook already exists; not modifying.",
                file=sys.stderr,
            )
            print("  Re-run with --force to replace it.", file=sys.stderr)
            return False
        backup_path = hook_path.with_suffix(".backup")
        hook_path.replace(backup_path)
        print(f"  NOTE: existing hook backed up to {backup_path}")

    hook_path.write_text(hook_body)
    os.chmod(hook_path, 0o755)
    print(f"  OK: installed pre-commit hook at {hook_path}")
    print("  NOTE: this affects all commits in this repository clone.")
    return True


def uninstall_hook(project_dir: Path) -> bool:
    hooks_dir = get_hooks_dir(project_dir)
    if hooks_dir is None:
        return False

    hook_path = hooks_dir / "pre-commit"
    if not hook_path.exists():
        print("  WARNING: no pre-commit hook found.", file=sys.stderr)
        return False

    existing = hook_path.read_text()
    if HOOK_MARKER not in existing:
        print(
            "  WARNING: pre-commit hook exists but was not installed by long-task-harness.",
            file=sys.stderr,
        )
        return False

    hook_path.unlink()
    print("  OK: removed long-task-harness pre-commit hook.")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install or uninstall the long-task-harness pre-commit hook"
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove the hook instead of installing it",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace existing pre-commit hook (backs up to .backup)",
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Project directory (default: current directory)",
    )

    args = parser.parse_args()

    if args.uninstall:
        uninstall_hook(args.path)
    else:
        install_hook(args.path, args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
