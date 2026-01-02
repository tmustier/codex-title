# codex-title

Small wrapper that runs Codex and updates your terminal tab title while it is working.

- Sets tab title to `codex:running...` when a user message is received
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
codex-title --running-title 'codex:thinking' --done-title 'codex:done'
```

## Aliases

Recommended:

```bash
alias codex='codex-title'
alias cyolo='codex-title --yolo'
```

## How it works

Codex writes JSONL session logs under `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`.
This wrapper tails the newest log and flips the tab title when it sees:

- `event_msg` with `user_message` -> running
- `response_item` with `assistant` message -> done

## Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/tmustier/codex-title/main/uninstall.sh | bash
```

## License

MIT
