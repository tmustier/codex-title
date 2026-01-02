# codex-title

Small wrapper that runs Codex and updates your terminal tab title while it is working.

- Sets tab title to `codex:new` on session start
- Sets tab title to `codex:running...` while Codex is working on a prompt
- Sets tab title to `codex:✅` when Codex finishes a response
- Works by watching Codex session logs in `~/.codex/sessions/...`

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

# Launch with full‑auto (Codex bypass flag)
codex-title --yolo
```

Customize titles:

```bash
codex-title --new-title 'codex:new' --running-title 'codex:thinking' --done-title 'codex:done'
```

Config file (optional):

`~/.config/codex-title/config.env`

```text
new_title=codex:new
running_title=codex:thinking
done_title=codex:done
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
- `CODEX_TITLE_ALIAS_CODEX` (for install.sh --alias)
- `CODEX_TITLE_ALIAS_CYOLO` (for install.sh --alias)

CLI flags override both env and config values.

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

## Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/tmustier/codex-title/main/uninstall.sh | bash
```

## License

MIT
