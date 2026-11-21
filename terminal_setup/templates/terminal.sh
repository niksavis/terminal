#!/usr/bin/env bash
set -uo pipefail

USAGE="usage: terminal status [--wsl|--win]"
CMD=""
TARGET="all"
for arg in "$@"; do
  case "$arg" in
    status) CMD="$arg" ;;
    --wsl | --win) TARGET="$arg" ;;
    *)
      echo "terminal: unknown argument '$arg'" >&2
      echo "$USAGE" >&2
      exit 2
      ;;
  esac
done
if [[ -z "$CMD" ]]; then
  echo "$USAGE" >&2
  exit 2
fi

export PATH="$HOME/.local/bin:$PATH"
SETUP_SOURCE="__SETUP_SOURCE__"
FAILED=0
IS_WSL=0
if grep -qi microsoft /proc/version 2>/dev/null; then
  IS_WSL=1
fi

run_local() {
  if ! command -v uvx >/dev/null 2>&1; then
    echo "!! uvx is not on the PATH, so terminal cannot read the tool versions. Run the terminal setup again to install uv."
    FAILED=1
    return
  fi
  uvx --from "$SETUP_SOURCE" terminal-setup --only status || FAILED=1
  if command -v agents >/dev/null 2>&1; then
    if ((IS_WSL)); then
      AGENTS_NESTED=1 agents status --wsl || FAILED=1
    else
      AGENTS_NESTED=1 agents status || FAILED=1
    fi
  fi
}

run_windows() {
  local win_home ps1 ps1_linux shell
  win_home="$(cd /mnt/c 2>/dev/null && cmd.exe /c 'echo %USERPROFILE%' 2>/dev/null | tr -d '\r')"
  ps1="$win_home\\.local\\bin\\terminal.ps1"
  ps1_linux="$(wslpath -u "$ps1" 2>/dev/null)"
  if [[ -z "$win_home" || -z "$ps1_linux" || ! -f "$ps1_linux" ]]; then
    echo "terminal.ps1 is not on Windows, so terminal skips Windows. To add it, run the terminal setup on Windows."
    return
  fi
  shell="$(command -v pwsh.exe || command -v powershell.exe)" || {
    echo "!! Windows: neither pwsh.exe nor powershell.exe is on the PATH"
    FAILED=1
    return
  }
  (cd /mnt/c && "$shell" -NoProfile -ExecutionPolicy Bypass -File "$ps1" "$CMD" --win) || FAILED=1
}

if [[ "$TARGET" != --win ]]; then
  run_local
fi
if [[ "$TARGET" != --wsl && "$IS_WSL" == 1 ]]; then
  run_windows
fi
exit "$FAILED"
