# Changelog

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
