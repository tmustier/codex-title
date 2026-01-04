# codex-title

Small wrapper for developers with too many Codex sessions. Runs Codex
(optionally with `--yolo`) and updates your terminal tab title while it works.

Default titles (configurable):

| State | Tab title |
| --- | --- |
| New session | `codex:new` |
| Working | `codex:running...` |
| Done with a commit | `codex:✅` |
| Done but maybe stuck (no commit) | `codex:🚧` |

Works by watching Codex session logs in `~/.codex/sessions/...` and uses the
last recorded turn to seed the initial title when resuming with `--resume` or
`--last`.

## Install

One‑liner:

```bash
curl -fsSL https://raw.githubusercontent.com/tmustier/codex-title/main/install.sh | bash
```

Optional flags:

```bash
# Add PATH line if needed
curl -fsSL https://raw.githubusercontent.com/tmustier/codex-title/main/install.sh | bash -s -- --add-path

# Add aliases (codex + cyolo)
curl -fsSL https://raw.githubusercontent.com/tmustier/codex-title/main/install.sh | bash -s -- --alias
```

Homebrew:

```bash
brew tap tmustier/tap
brew install codex-title
```

uv:

```bash
uv tool install git+https://github.com/tmustier/codex-title
```

## Usage

```bash
codex-title

# Pass Codex args
codex-title -- --resume --last

# Follow resume signals across tabs (may sync titles across sessions)
codex-title --follow-global-resume -- --resume

# Launch with full‑auto (Codex bypass flag)
codex-title --yolo

# Show the resolved title and log path without changing the tab title
codex-title --status
```

Customize titles:

```bash
codex-title --new-title 'codex:new' --running-title 'codex:thinking' --done-title 'codex:done'
```

Commit-aware done title (override the default):

```bash
codex-title --no-commit-title 'codex:🚧'
```

Config file (optional):

`~/.config/codex-title/config.env`

```text
new_title=codex:new
running_title=codex:thinking
done_title=codex:done
no_commit_title=codex:🚧
alias_codex=codex
alias_cyolo=cyolo
```

Pass a different config file:

```bash
codex-title --config ~/my-codex-title.env
```

Environment overrides (take precedence over config):

- `CODEX_TITLE_CONFIG` (config file path)
- `CODEX_TITLE_NEW_TITLE`
- `CODEX_TITLE_RUNNING_TITLE`
- `CODEX_TITLE_DONE_TITLE`
- `CODEX_TITLE_NO_COMMIT_TITLE`
- `CODEX_TITLE_IDLE_DONE_SECS` (idle seconds before treating a tool-only turn as done; set `0` to disable)
- `CODEX_TITLE_FOLLOW_GLOBAL_RESUME` (set to `1` to follow resume signals from other tabs/sessions)
- `CODEX_TITLE_ALIAS_CODEX` (for install.sh --alias)
- `CODEX_TITLE_ALIAS_CYOLO` (for install.sh --alias)
- `CODEX_TITLE_LOG_PATH` (set to an empty string to disable the debug log)

CLI flags override both env and config values.

When `no_commit_title` is non-empty, the wrapper treats a turn as committed if it
sees a successful `git commit` in the Codex tool logs for that turn, or if the git
HEAD changed in the current working directory. Otherwise it uses `no_commit_title`.
This includes `git -C /path/to/repo commit ...` commands run by Codex.

## Aliases

Recommended:

```bash
alias codex='codex-title'
alias cyolo='codex-title --yolo'
```

To customize alias names for `install.sh --alias`, set `alias_codex` and
`alias_cyolo` in the config file (or use the env vars above).

## How it works

Codex writes JSONL session logs under `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`.
This wrapper tails the newest log and flips the tab title when it sees:

- User message begins processing -> running
- Assistant message (or aborted turn) -> done
- If no assistant message arrives, mark done after the log has been idle for a short period (default 3s)
- If `no_commit_title` is non-empty, show it when no commit happened in the last turn
- By default, resume signals only switch logs when you launch with `--resume/--last` or issue `/resume` in the same session (use `CODEX_TITLE_FOLLOW_GLOBAL_RESUME=1` or `--follow-global-resume` to opt in globally)

## Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/tmustier/codex-title/main/uninstall.sh | bash
```

## License

MIT

## Release notes

See `CHANGELOG.md`.
