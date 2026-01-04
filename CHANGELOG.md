# Changelog

## 0.1.31

- Prefer PID-attached logs over new session-dir candidates to avoid mis-binding resumed sessions.

## 0.1.30

- Treat unseen logs with a real user message as resumable even when history has not recorded the session ID.

## 0.1.29

- Keep polling the Codex PID for a resumed log even after the fast detection window expires.

## 0.1.28

- Detect the active session log via the Codex process PID (avoids cross-tab resume conflicts).
- Allow resume selection based on the PID-opened log even when the log already exists.

## 0.1.27

- Avoid cross-tab resume switching when launching with `--resume/--last`; only switch after a local `/resume` or global opt-in.
- Allow initial titles for resumed sessions even if history has not yet recorded the session ID.

## 0.1.26

- Tolerate clock skew in log timestamps when selecting sessions and applying idle fallbacks.
- Tail logs from a byte offset to avoid relying on timestamp ordering.

## 0.1.25

- Mark tool-only turns as done after a short idle fallback (default 3s).
- Add resume-selection tests and a Makefile test target.
- Use a single source for the CLI and update install.sh to fetch it.
- Avoid cross-tab log switching by default; follow resume signals only when requested or when `/resume` is used.

## 0.1.24

- Treat successful `git commit` commands in Codex tool logs as committed turns, even outside the launch repo.

## 0.1.23

- Keep fresh sessions on `codex:new` until a real user prompt arrives by ignoring bootstrap messages.

## 0.1.22

- Pin the active log once a resume signal is detected to prevent oscillating between logs.

## 0.1.21

- Check for resume switches even while the current log is actively receiving events.

## 0.1.20

- Add `--status` to print the resolved title and active log path without modifying the tab title.
- Document the debug log env var and status command.

## 0.1.19

- Always write a lightweight debug log to `~/.codex/log/codex-title.log` to capture which log path is selected or switched.

## 0.1.18

- Pick the most recent resume line regardless of timestamp to avoid missing fast `/resume` events.
- Track history updates by file size and start from the current end to avoid scanning old sessions.

## 0.1.17

- Switch to resumed sessions even if the current log remains active by prioritizing resume signals.
- Use history session IDs as authoritative without comparing log mtimes.

## 0.1.16

- Follow the active session via `~/.codex/history.jsonl` when `/resume` does not emit a usable TUI signal.
- Scan a deeper tail of the TUI log to avoid missing resume lines during heavy logging.

## 0.1.15

- Prefer the TUI resume log (from `~/.codex/log/codex-tui.log`) when `/resume` switches to an older session log.

## 0.1.14

- Switch to the most recently updated Codex log when resuming into older sessions.

## 0.1.13

- Track resumed sessions that append to existing logs outside today's folder.

## 0.1.12

- Seed the initial title from recent logs when resuming via `--resume`/`--last`.

## 0.1.11

- Set the initial title from the last recorded turn when resuming a session.

## 0.1.10

- Default to `codex:🚧` when no commit happens in the last turn.

## 0.1.9

- Reframe the README intro and default state table.

## 0.1.8

- Hide advanced debug flags from `--help` output.
- Keep the balanced flag set for human-first usage.

## 0.1.7

- Add commit-aware done titles with `--no-commit-title`.

## 0.1.6

- Add config file support for title defaults.
- Allow configurable alias names for `install.sh --alias`.
