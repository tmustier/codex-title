#!/usr/bin/env python3
"""
Initialize the long-task-harness structure in the current project.

Creates:
- long-task-progress.md: Work history and session notes
- features.json: Testable feature checklist
- init.sh: Environment setup script (optional)
"""

import os
import json
import shutil
from datetime import datetime
from pathlib import Path


def get_script_dir():
    """Get the directory containing this script."""
    return Path(__file__).parent.resolve()


def get_skill_dir():
    """Get the skill root directory."""
    return get_script_dir().parent


def get_harness_dir(project_dir: Path) -> Path:
    """Get or create the .long-task-harness directory."""
    harness_dir = project_dir / ".long-task-harness"
    harness_dir.mkdir(exist_ok=True)
    return harness_dir


def create_progress_file(project_dir: Path, project_name: str):
    """Create the long-task-progress.md file from template."""
    harness_dir = get_harness_dir(project_dir)
    template_path = get_skill_dir() / "assets" / "progress_template.md"
    output_path = harness_dir / "long-task-progress.md"

    # Also check for legacy location
    legacy_path = project_dir / "long-task-progress.md"
    if legacy_path.exists():
        print(f"  ⚠️  Found long-task-progress.md in project root (legacy location)")
        print(f"      Consider moving to .long-task-harness/long-task-progress.md")
        return

    if output_path.exists():
        print(f"  ⚠️  long-task-progress.md already exists, skipping")
        return

    if template_path.exists():
        content = template_path.read_text()
        content = content.replace("{{PROJECT_NAME}}", project_name)
        content = content.replace("{{DATE}}", datetime.now().strftime("%Y-%m-%d"))
    else:
        content = f"""# {project_name} - Progress Log

## Project Overview

**Started**: {datetime.now().strftime("%Y-%m-%d")}
**Status**: In Progress

## Current State

[Describe the current state of the project]

## Session Log

### Session 1 - {datetime.now().strftime("%Y-%m-%d")}

**Goal**: [What you're working on]

**Accomplished**:
- [List accomplishments]

**Next Steps**:
- [List next steps]

**Blockers**:
- [List any blockers]
"""

    output_path.write_text(content)
    print(f"  ✅ Created long-task-progress.md")


def create_features_file(project_dir: Path):
    """Create the features.json file from template."""
    harness_dir = get_harness_dir(project_dir)
    template_path = get_skill_dir() / "assets" / "features_template.json"
    output_path = harness_dir / "features.json"

    # Also check for legacy location
    legacy_path = project_dir / "features.json"
    if legacy_path.exists():
        print(f"  ⚠️  Found features.json in project root (legacy location)")
        print(f"      Consider moving to .long-task-harness/features.json")
        return

    if output_path.exists():
        print(f"  ⚠️  features.json already exists, skipping")
        return

    if template_path.exists():
        shutil.copy(template_path, output_path)
    else:
        features = {
            "version": "1.0",
            "description": "Feature checklist for the project",
            "features": [
                {
                    "id": "feature-001",
                    "name": "Example Feature",
                    "description": "Description of the feature",
                    "steps": [
                        "Step 1: Do something",
                        "Step 2: Do something else"
                    ],
                    "passes": False,
                    "notes": ""
                }
            ]
        }
        output_path.write_text(json.dumps(features, indent=2))

    print(f"  ✅ Created features.json")


def create_init_script(project_dir: Path):
    """Create an optional init.sh script for environment setup."""
    harness_dir = get_harness_dir(project_dir)
    output_path = harness_dir / "init.sh"

    # Also check for legacy location
    legacy_path = project_dir / "init.sh"
    if legacy_path.exists():
        print(f"  ⚠️  Found init.sh in project root (legacy location)")
        print(f"      Consider moving to .long-task-harness/init.sh")
        return

    if output_path.exists():
        print(f"  ⚠️  init.sh already exists, skipping")
        return

    content = """#!/bin/bash
# Environment initialization script
# Customize this for your project's setup needs

echo "Initializing project environment..."

# Example: Install dependencies
# npm install
# pip install -r requirements.txt

# Example: Start services
# docker-compose up -d

# Example: Run migrations
# python manage.py migrate

echo "Environment ready!"
"""

    output_path.write_text(content)
    os.chmod(output_path, 0o755)
    print(f"  ✅ Created init.sh")


def check_harness_configured(project_dir: Path) -> bool:
    """Check if CLAUDE.md or AGENTS.md contains harness instructions."""
    for filename in ["CLAUDE.md", "AGENTS.md"]:
        filepath = project_dir / filename
        if filepath.exists():
            content = filepath.read_text()
            if "long-task-harness" in content.lower() or "long-task-progress.md" in content:
                return True
    return False


def main():
    project_dir = Path.cwd()
    project_name = project_dir.name

    print(f"\n🚀 Initializing long-task-harness in: {project_dir}\n")

    create_progress_file(project_dir, project_name)
    create_features_file(project_dir)
    create_init_script(project_dir)

    is_configured = check_harness_configured(project_dir)

    print(f"""
✅ Harness initialized!

Files created in .long-task-harness/:
- long-task-progress.md  (session history)
- features.json          (feature tracking)
- init.sh                (environment setup)

Next steps:
1. Edit .long-task-harness/features.json to add your project's specific features
2. Update .long-task-harness/long-task-progress.md with project overview
3. Customize .long-task-harness/init.sh for your environment setup
4. Create an initial git commit: git add . && git commit -m "Initialize long-task-harness"

At the start of each session, read:
- .long-task-harness/long-task-progress.md for context
- .long-task-harness/features.json for next tasks
- git log for recent history
""")

    if not is_configured:
        print("""⚠️  Consider adding harness instructions to AGENTS.md or CLAUDE.md
   so future sessions automatically invoke this skill.
""")


if __name__ == "__main__":
    main()
