#!/bin/sh
set -eu

ref="${TERMINAL_SETUP_REF:-main}"
source_url="https://github.com/niksavis/terminal/archive/${ref}.zip"
PATH="$HOME/.local/bin:$PATH"
export PATH

if ! command -v uv >/dev/null 2>&1; then
  if ! command -v curl >/dev/null 2>&1; then
    echo "install.sh: curl is missing. Install it, then re-run: sudo apt-get install -y curl" >&2
    exit 1
  fi
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

exec uvx --python 3.14 --refresh-package terminal --from "$source_url" terminal-setup "$@"
