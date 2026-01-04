#!/usr/bin/env sh
set -eu

REPO="${CODEX_TITLE_REPO:-tmustier/codex-title}"
REF="${CODEX_TITLE_REF:-main}"
BIN_DIR="${CODEX_TITLE_BIN_DIR:-$HOME/.local/bin}"
SCRIPT_NAME="codex-title"
SOURCE_PATH="src/codex_title/cli.py"
CONFIG_PATH="${CODEX_TITLE_CONFIG:-$HOME/.config/codex-title/config.env}"
ALIAS_CODEX="${CODEX_TITLE_ALIAS_CODEX:-}"
ALIAS_CYOLO="${CODEX_TITLE_ALIAS_CYOLO:-}"

ADD_PATH=0
ADD_ALIAS=0
RC_FILE=""

usage() {
  cat <<'EOF'
Usage: install.sh [--add-path] [--alias] [--rc FILE]

Options:
  --add-path   Add ~/.local/bin to PATH in your shell rc
  --alias      Add aliases for codex + cyolo in your shell rc
  --rc FILE    Override rc file to edit (default: based on $SHELL)
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --add-path)
      ADD_PATH=1
      ;;
    --alias)
      ADD_ALIAS=1
      ;;
    --rc)
      shift
      RC_FILE="$1"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
 done

if [ -z "$RC_FILE" ]; then
  case "${SHELL:-}" in
    */zsh)
      RC_FILE="$HOME/.zshrc"
      ;;
    */bash)
      RC_FILE="$HOME/.bashrc"
      ;;
    *)
      RC_FILE="$HOME/.profile"
      ;;
  esac
fi

mkdir -p "$BIN_DIR"
TARGET="$BIN_DIR/$SCRIPT_NAME"

if [ -f "./$SOURCE_PATH" ]; then
  cp "./$SOURCE_PATH" "$TARGET"
else
  URL="https://raw.githubusercontent.com/$REPO/$REF/$SOURCE_PATH"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$URL" -o "$TARGET"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$TARGET" "$URL"
  else
    echo "Neither curl nor wget is available." >&2
    exit 1
  fi
fi

chmod +x "$TARGET"

echo "Installed $SCRIPT_NAME to $TARGET"

append_if_missing() {
  LINE="$1"
  FILE="$2"
  if [ ! -f "$FILE" ]; then
    printf '' > "$FILE"
  fi
  if ! grep -Fqs "$LINE" "$FILE"; then
    printf '%s\n' "$LINE" >> "$FILE"
  fi
}

get_config_value() {
  KEY="$1"
  FILE="$2"
  if [ ! -f "$FILE" ]; then
    return 0
  fi
  awk -F= -v key="$KEY" '
    /^[[:space:]]*#/ { next }
    NF < 2 { next }
    {
      k = $1
      sub(/^[[:space:]]+/, "", k)
      sub(/[[:space:]]+$/, "", k)
      k = tolower(k)
      if (k != key) {
        next
      }
      v = $2
      sub(/^[[:space:]]+/, "", v)
      sub(/[[:space:]]+$/, "", v)
      gsub(/^"|"$/, "", v)
      gsub(/^'\''|'\''$/, "", v)
      print v
      exit
    }
  ' "$FILE"
}

if [ "$ADD_PATH" -eq 1 ]; then
  case ":${PATH}:" in
    *":$BIN_DIR:"*)
      :
      ;;
    *)
      append_if_missing "export PATH=\"$BIN_DIR:\$PATH\" # codex-title" "$RC_FILE"
      echo "Added PATH line to $RC_FILE"
      ;;
  esac
fi

if [ "$ADD_ALIAS" -eq 1 ]; then
  if [ -z "$ALIAS_CODEX" ]; then
    ALIAS_CODEX="$(get_config_value "alias_codex" "$CONFIG_PATH")"
  fi
  if [ -z "$ALIAS_CYOLO" ]; then
    ALIAS_CYOLO="$(get_config_value "alias_cyolo" "$CONFIG_PATH")"
  fi
  ALIAS_CODEX="${ALIAS_CODEX:-codex}"
  ALIAS_CYOLO="${ALIAS_CYOLO:-cyolo}"
  append_if_missing "alias $ALIAS_CODEX='codex-title' # codex-title" "$RC_FILE"
  append_if_missing "alias $ALIAS_CYOLO='codex-title --yolo' # codex-title" "$RC_FILE"
  echo "Added aliases to $RC_FILE"
fi

if [ "$ADD_PATH" -eq 1 ] || [ "$ADD_ALIAS" -eq 1 ]; then
  echo "Reload your shell: source $RC_FILE"
else
  echo "Make sure $BIN_DIR is on your PATH, or run: $TARGET"
fi
