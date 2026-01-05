#!/usr/bin/env python3
"""
Extract relevant feature information from features.json for session startup.

Default: shows incomplete features (full details) + completed features (names only)
Use --all for full features.json content.
"""

import argparse
import json
import sys
from pathlib import Path


def find_features_file() -> Path | None:
    """Find features.json in current directory or parents.
    
    Checks .long-task-harness/ first (new location), then falls back to
    project root (legacy location).
    """
    cwd = Path.cwd()
    for path in [cwd, *cwd.parents]:
        # Check new location first
        new_location = path / ".long-task-harness" / "features.json"
        if new_location.exists():
            return new_location
        # Fall back to legacy location
        legacy_location = path / "features.json"
        if legacy_location.exists():
            return legacy_location
    return None


def format_feature_compact(feature: dict) -> str:
    """Format a feature as readable text (for incomplete features)."""
    lines = []
    lines.append(f"### {feature['id']}: {feature['name']}")
    lines.append(f"    {feature.get('description', 'No description')}")
    
    # Steps
    steps = feature.get('steps', [])
    if steps:
        lines.append("    Steps:")
        for step in steps:
            lines.append(f"      - {step}")
    
    # Notes
    notes = feature.get('notes', '')
    if notes:
        lines.append(f"    Notes: {notes}")
    
    # History (v2 format)
    history = feature.get('history', {})
    if history:
        # Sessions
        sessions = history.get('sessions', [])
        if sessions:
            lines.append("    History:")
            for s in sessions[-3:]:  # Last 3 sessions
                lines.append(f"      - Session {s.get('session')} ({s.get('date')}): {s.get('action')} - {s.get('summary', '')}")
            if len(sessions) > 3:
                lines.append(f"      ... and {len(sessions) - 3} earlier sessions")
        
        # Key files
        files = history.get('files', [])
        if files:
            lines.append(f"    Files: {', '.join(files[:5])}")
            if len(files) > 5:
                lines.append(f"      ... and {len(files) - 5} more")
        
        # Recent decisions
        decisions = history.get('decisions', [])
        if decisions:
            lines.append("    Key Decisions:")
            for d in decisions[-2:]:  # Last 2 decisions
                lines.append(f"      - [Session {d.get('session')}] {d.get('decision')}")
    
    return '\n'.join(lines)


def format_feature_oneline(feature: dict) -> str:
    """Format a feature as a single line (for completed features)."""
    status = "✓" if feature.get("passes") else "○"
    return f"  {feature['id']:20} {feature['name']:40} {status}"


def format_output(data: dict, show_all: bool) -> str:
    """Format the features output."""
    features = data.get("features", [])
    metadata = data.get("metadata", {})

    total = len(features)
    completed = [f for f in features if f.get("passes")]
    incomplete = [f for f in features if not f.get("passes")]

    output_parts = []

    # Summary line
    output_parts.append(f"[Features: {len(completed)}/{total} complete]\n")

    if show_all:
        # Show full JSON
        output_parts.append("\n" + json.dumps(data, indent=2))
        return ''.join(output_parts)

    # Priority order (if available)
    priority_order = metadata.get("priority_order", [])

    # Sort incomplete by priority order
    if priority_order:
        def priority_key(f):
            try:
                return priority_order.index(f["id"])
            except ValueError:
                return len(priority_order)
        incomplete = sorted(incomplete, key=priority_key)

    # Incomplete features (full details)
    if incomplete:
        output_parts.append("\nINCOMPLETE (full details):\n")
        for feature in incomplete:
            output_parts.append(f"\n{format_feature_compact(feature)}\n")
    else:
        output_parts.append("\nAll features complete! 🎉\n")

    # Completed features (names only)
    if completed:
        output_parts.append(f"\nCOMPLETED ({len(completed)}):\n")
        # Sort by id for consistent display
        for feature in sorted(completed, key=lambda f: f["id"]):
            output_parts.append(format_feature_oneline(feature) + "\n")

    # Hint
    output_parts.append(f"\n[Full details: --all]")

    return ''.join(output_parts)


def format_feature_detail(feature: dict) -> str:
    """Format a single feature with full details including history."""
    lines = []
    lines.append(f"# {feature['id']}: {feature['name']}")
    lines.append(f"Status: {'COMPLETE' if feature.get('passes') else 'INCOMPLETE'}")
    lines.append(f"\n{feature.get('description', 'No description')}\n")
    
    # Steps
    steps = feature.get('steps', [])
    if steps:
        lines.append("## Steps")
        for i, step in enumerate(steps, 1):
            lines.append(f"  {i}. {step}")
    
    # Notes
    notes = feature.get('notes', '')
    if notes:
        lines.append(f"\n## Notes\n{notes}")
    
    # Full History (v2 format)
    history = feature.get('history', {})
    if history:
        lines.append("\n## History")
        
        sessions = history.get('sessions', [])
        if sessions:
            lines.append("\n### Sessions")
            for s in sessions:
                lines.append(f"  - Session {s.get('session')} ({s.get('date')}): {s.get('action')}")
                if s.get('summary'):
                    lines.append(f"    {s.get('summary')}")
        
        files = history.get('files', [])
        if files:
            lines.append("\n### Files Touched")
            for f in files:
                lines.append(f"  - {f}")
        
        decisions = history.get('decisions', [])
        if decisions:
            lines.append("\n### Key Decisions")
            for d in decisions:
                lines.append(f"  - [Session {d.get('session')}] {d.get('decision')}")
    
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Extract relevant feature information from features.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 read_features.py                    # incomplete (full) + completed (names)
  python3 read_features.py --all              # full features.json
  python3 read_features.py --feature auth-001 # details for specific feature
  python3 read_features.py --json             # raw JSON output (for subagents)
        """
    )
    parser.add_argument('--all', action='store_true',
                        help='Show full features.json content')
    parser.add_argument('--feature', '-f', type=str,
                        help='Show details for a specific feature by ID')
    parser.add_argument('--json', action='store_true',
                        help='Output raw JSON (for programmatic use)')
    parser.add_argument('--file', type=Path,
                        help='Path to features.json (default: auto-detect)')

    args = parser.parse_args()

    # Find features file
    if args.file:
        features_file = args.file
    else:
        features_file = find_features_file()

    if not features_file or not features_file.exists():
        print("Error: features.json not found", file=sys.stderr)
        print("Run from a project directory with features.json, or use --file", file=sys.stderr)
        sys.exit(1)

    # Read and parse
    try:
        data = json.loads(features_file.read_text())
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in features.json: {e}", file=sys.stderr)
        sys.exit(1)

    # Handle --feature flag
    if args.feature:
        features = data.get("features", [])
        feature = next((f for f in features if f["id"] == args.feature), None)
        if not feature:
            print(f"Error: Feature '{args.feature}' not found", file=sys.stderr)
            print(f"Available features: {', '.join(f['id'] for f in features)}", file=sys.stderr)
            sys.exit(1)
        if args.json:
            print(json.dumps(feature, indent=2))
        else:
            print(format_feature_detail(feature))
        return

    # Handle --json flag for full output
    if args.json:
        print(json.dumps(data, indent=2))
        return

    # Format output
    output = format_output(data, args.all)
    print(output)


if __name__ == "__main__":
    main()
