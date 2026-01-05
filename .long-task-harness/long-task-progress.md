# codex-title - Progress Log

## Project Overview

**Started**: 2026-01-05
**Status**: In Progress
**Repository**: (local)

### Project Goals

- Provide a `codex` launcher that updates the terminal tab title based on Codex session state (new/running/done).
- Keep per-tab correctness by binding to the active Codex session log (prefer PID-based binding; avoid cross-tab bleed).
- Explore OS-native macOS integration (libproc, and eventually a menu bar UI for session status).

### Key Decisions

- **[D1]** Keep the Python wrapper as the reference implementation and correctness oracle.
- **[D2]** Use Swift + `libproc` for PID→open-file discovery (candidate replacement for `lsof`).
- **[D3]** Launch Codex via `posix_spawn` (not `Process`) to preserve interactive TTY behavior.

---

## Current State

**Last Updated**: 2026-01-05

### What's Working
- Python wrapper (`codex-title`) launches Codex and updates terminal tab title based on session logs.
- Swift POC (`./codex-title-poc --`) launches Codex interactively.
- Swift POC can resolve the active log path via `libproc` + fallback discovery (unit tested).

### What's Not Working
- Swift POC does not yet update the terminal tab title/status (no log tailing/title-writer loop yet).

### Blocked On
- Nothing; next work is implementing the title watcher in Swift.

---

## Session Log

### Session 1 | 2026-01-05 | Commits: (pending)

#### Metadata
- **Features**: setup-001 (completed), poc-001 (completed), title-001 (started)
- **Files Changed**:
  - `.long-task-harness/*` - initialized project continuity tracking
  - `skills/long-task-harness/*` - vendored the skill into the repo
  - `swift-poc/*` - Swift POC for libproc log discovery + Codex launcher
  - `codex-title-poc` - repo script to run the Swift launcher

#### Goal
Set up long-task-harness in this repo and checkpoint current Swift POC work.

#### Accomplished
- [x] Initialized long-task-harness structure
- [x] Added an initial feature list for this project
- [x] Added AGENTS.md hint to invoke the harness skill
- [ ] Implement Swift tab-title watcher (parity with Python)

#### Decisions
- **[D1]** Keep Python version as baseline for behavior parity.
- **[D2]** Vendor `long-task-harness` into `skills/` so the repo is self-contained.
- **[D3]** Use `posix_spawn` for launching interactive Codex from Swift.

#### Context & Learnings
- Swift `Process` launch had TTY issues; switching to `posix_spawn` made interactive launch reliable.
- To avoid breaking the Codex TUI, the Swift wrapper stays quiet by default in interactive terminals.

#### Next Steps
1. Implement `title-001` (Swift log tailing + terminal title updates)
2. Add Swift tests for the title state machine using fixture JSONL logs (mirroring Python tests)

---

<!--
=============================================================================
SESSION TEMPLATE - Copy below this line for new sessions
=============================================================================

### Session N | YYYY-MM-DD | Commits: abc123..def456

#### Metadata
- **Features**: feature-id (started|progressed|completed|blocked)
- **Files Changed**: 
  - `path/to/file.ts` (+lines/-lines) - brief description
- **Commit Summary**: `type: message`, `type: message`

#### Goal
[One-liner: what you're trying to accomplish this session]

#### Accomplished
- [x] Completed task
- [ ] Incomplete task (carried forward)

#### Decisions
- **[DN]** Decision made and rationale (reference in features.json)

#### Context & Learnings
[What you learned, gotchas, context future sessions need to know.
Focus on WHAT and WHY, not the struggle/errors along the way.]

#### Next Steps
1. [Priority 1] → likely affects: feature-id
2. [Priority 2]

=============================================================================
GUIDELINES FOR GOOD SESSION ENTRIES
=============================================================================

1. METADATA is for machines (subagent lookup)
   - Always list features touched with status
   - Always list files with change magnitude
   - Always include commit range or hashes

2. DECISIONS are for continuity
   - Number them [D1], [D2] so they can be referenced
   - Copy key decisions to features.json history
   - Include rationale, not just the choice

3. CONTEXT is for future you/agents
   - Capture the WHY behind non-obvious choices
   - Note gotchas and edge cases discovered
   - Omit error-correction loops - just document resolution

4. COMMIT SUMMARY style
   - Use conventional commits: feat|fix|refactor|test|docs|chore
   - Keep to one-liners that scan quickly

5. Keep sessions BOUNDED
   - One session = one work period (not one feature)
   - If session runs long, split into multiple entries
   - Target: scannable in <30 seconds

-->
