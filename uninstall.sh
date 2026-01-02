#!/usr/bin/env sh
set -eu

BIN_DIR="${CODEX_TITLE_BIN_DIR:-$HOME/.local/bin}"
SCRIPT_NAME="codex-title"
TARGET="$BIN_DIR/$SCRIPT_NAME"
RC_FILE=""

usage() {
  cat <<'EOF'
Usage: uninstall.sh [--rc FILE]

Options:
  --rc FILE    Override rc file to clean (default: based on $SHELL)
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
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

if [ -f "$TARGET" ]; then
  rm "$TARGET"
  echo "Removed $TARGET"
else
  echo "No installed binary found at $TARGET"
fi

if [ -f "$RC_FILE" ] && grep -q "# codex-title" "$RC_FILE"; then
  TMP_FILE="${RC_FILE}.codex-title.tmp"
  grep -v "# codex-title" "$RC_FILE" > "$TMP_FILE"
  mv "$TMP_FILE" "$RC_FILE"
  echo "Removed codex-title lines from $RC_FILE"
  echo "Reload your shell: source $RC_FILE"
fi
