# Implementation Notes

This document explains how `codex-title` binds to Codex logs, how it sets
titles, and the fixes we shipped for resume correctness.

## Overview

`codex-title` launches Codex, monitors the active session log, and updates
the terminal tab title based on the latest turn state. The core loop is:

1. Spawn `codex` and capture its PID.
2. Resolve the active log path (prefer PID-attached logs).
3. Tail the log and update the title as events arrive.
4. Keep watching for PID log changes to handle `/resume`.

When run with `--watch-only`, step 1 is skipped and only log discovery/tailing
is performed.

## Log Discovery (Per-Tab Binding)

When a Codex PID is available and `lsof` is present, the log selection logic
prefers the PID-opened JSONL file. This is the only per-tab signal that is not
global, so it is authoritative. The order is:

1. **PID log** (via `lsof -p <pid>`).
2. **TUI resume log** if external resume switching is allowed.
3. **Session dir candidate** (new logs created after startup).
4. **Recent logs fallback** if external switching is allowed.

If PID detection is unavailable (missing `lsof` or disabled by env), the
selection falls back to the non-PID sources.

## Initial Title

The initial title is computed from the active log by scanning its events:

- Bootstrap messages (AGENTS/environment) are ignored.
- A user message sets the state to "running".
- An assistant or aborted message marks the turn as "done".
- Tool-only turns are treated as done after a short idle timeout (default 5s).
- A successful `git commit` detected in tool output marks the turn as done.
- If `no_commit_title` is set, it is used when no commit happened.

The "seen in history" check is a guardrail for new sessions, but if a log has
real user input it is treated as resumable even when history has not updated.

## Resume Handling

`/resume` is not written to the JSONL session log, so relying only on log
content is insufficient. To keep resume per-tab and deterministic:

- **PID detection** attaches the wrapper to the Codex-opened log.
- **PID switching while running** ensures we follow the new log after `/resume`.
- Global TUI resume signals are **opt-in** only (`--follow-global-resume`).

This keeps tabs isolated even when multiple sessions are active.

## Status Command

`codex-title --status` is a diagnostic helper. It uses the **global** TUI log
to pick a log path, then derives the title from that log. This is useful for
inspecting activity but it may not match a specific tab's binding.

For per-tab debugging, use `lsof -p <codex-pid>` and the debug log described
below.

## Debugging

By default, `codex-title` writes a lightweight debug log to:

- `~/.codex/log/codex-title.log`

Useful markers:

- `wait_for_log:pid path=...` (bound to PID log)
- `wait_for_log:session_dir path=...` (bound via session dir)
- `watcher:start path=...` (tailing this log)
- `watcher:initial_title title=...` (initial title chosen)
- `switch:pid from=... to=...` (PID log changed, e.g. `/resume`)

Disable by setting `CODEX_TITLE_LOG_PATH` to an empty string.

## Fixes Shipped (Resume + Cross-Tab)

These are the key changes that made resume reliable and isolated:

- **Cross-tab resume sync**: TUI resume signals are now opt-in to avoid
  global switching. Local `/resume` is still honored.
- **PID log detection**: bind to the log opened by the Codex process.
- **Delayed `/resume`**: keep polling the PID after the fast window to catch
  late log opens.
- **Session-dir misbinding**: defer session-dir candidates when PID is
  available so we do not bind to the wrong log.
- **PID switching while running**: follow the PID-attached log if it changes
  after `/resume`, even when external resume signals are disabled.
- **History guardrails**: accept unseen sessions with real user input to avoid
  getting stuck on `codex:new`.

The current design makes the PID the single source of truth for per-tab
binding, with optional global resume behavior behind an explicit flag.
