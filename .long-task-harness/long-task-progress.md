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
- Swift POC resolves the active log path via `libproc` + fallback discovery (unit tested).
- Swift POC tails the active JSONL log and updates the terminal tab title (new/running/done) with commit-aware done state.
- Swift POC supports an inactivity timeout overlay (`codex:🛑`) while running (configurable; default 3s for testing).

### What's Not Working
- No menu bar UI (future).
- Swift POC does not yet have full CLI/config/env parity with the Python wrapper (future).

### Blocked On
- Nothing; next work is deciding defaults and exploring native UI.

---

## Session Log

### Session 1 | 2026-01-05 | Commits: 1a221ac..af170bf

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

### Session 2 | 2026-01-05 | Commits: af170bf..21229dc

#### Metadata
- **Features**: title-001 (completed)
- **Files Changed**:
  - `swift-poc/Sources/LibprocPoc/CodexLogReducer.swift` - log reducer + title state machine
  - `swift-poc/Sources/CodexTitlePoc/main.swift` - add inactivity timeout overlay + configurable titles
  - `swift-poc/Sources/LibprocPoc/CodexTimeoutOverlay.swift` - timeout overlay state machine
  - `swift-poc/Tests/LibprocPocTests/LibprocPocTests.swift` - unit tests for overlay
  - `src/codex_title/cli.py` - tune idle-done default + refresh running on reasoning
  - `README.md`, `docs/implementation.md`, `CHANGELOG.md`, `pyproject.toml`, `src/codex_title/__init__.py`, `tests/test_cli_state.py` - docs/tests/version bump
- **Commit Summary**: `feat(swift): update terminal title from logs`, `feat(swift): use 🚧 when no commit`, `feat: increase idle-done default to 15s`, `feat(swift): add inactivity timeout overlay`

#### Goal
Finish the Swift title watcher and fix the Python wrapper's long-running tool-only title behavior.

#### Accomplished
- [x] Swift: tail the active JSONL log and update terminal tab title (new/running/done), including commit-aware done state
- [x] Add `codex:🛑` overlay when no log activity occurs for a configurable duration while running
- [x] Add CLI flags for customizing titles + inactivity timeout
- [x] Add unit tests for the timeout overlay
- [x] Python: increase the tool-only idle fallback default to 15s and re-arm `codex:running...` on model activity; update docs/tests/version

#### Context & Learnings
- In sandboxed environments, SwiftPM may need `HOME` and `CLANG_MODULE_CACHE_PATH` set to a repo-local writable directory.

#### Next Steps
1. Decide a default inactivity threshold (target ~120s)
2. Investigate assistant-text streaming gaps (optional)
3. Continue native-001 (menu bar UX + additional OS-native integrations)

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
