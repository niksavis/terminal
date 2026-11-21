#!/usr/bin/env bash
set -uo pipefail

USAGE="usage: terminal <status|update> [--wsl|--win] [--pinned]"
CMD=""
TARGET="all"
PINNED=0
for arg in "$@"; do
  case "$arg" in
    status | update) CMD="$arg" ;;
    --wsl | --win) TARGET="$arg" ;;
    --pinned) PINNED=1 ;;
    *)
      echo "terminal: unknown argument '$arg'" >&2
      echo "$USAGE" >&2
      exit 2
      ;;
  esac
done
if [[ -z "$CMD" || ("$PINNED" == 1 && "$CMD" != update) ]]; then
  echo "$USAGE" >&2
  exit 2
fi

export PATH="$HOME/.local/bin:$PATH"
SETUP_SOURCE="__SETUP_SOURCE__"
INSTALLED_REF="__SETUP_REF__"
RELEASES="__RELEASES__"
TAG_PATTERN='^v[0-9]+\.[0-9]+\.[0-9]+$'
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

target_ref() {
  local location tag
  if ((PINNED)); then
    printf '%s\n' "$INSTALLED_REF"
    return 0
  fi
  location="$(curl -fsSI --max-time 15 "$RELEASES/latest" 2>/dev/null | tr -d '\r' | sed -n 's/^[Ll]ocation: *//p' | tail -1)"
  tag="${location##*/}"
  if [[ "$tag" =~ $TAG_PATTERN ]]; then
    printf '%s\n' "$tag"
    return 0
  fi
  return 1
}

SIDE_NAME="Linux"
if ((IS_WSL)); then
  SIDE_NAME="WSL"
elif [[ "$(uname -s 2>/dev/null)" == Darwin ]]; then
  SIDE_NAME="macOS"
fi
FAILED_STEPS=""

run_step() {
  local name="$1" start="$SECONDS"
  shift
  echo "==> $name"
  if "$@"; then
    echo "$name: done ($((SECONDS - start)) s)"
    return 0
  fi
  echo "!! $name: failed ($((SECONDS - start)) s)"
  FAILED=1
  FAILED_STEPS="${FAILED_STEPS:+$FAILED_STEPS, }$name"
  return 1
}

# shellcheck disable=SC2329
bootstrap_release() {
  curl -fsSL "$RELEASES/download/$1/install.sh" | TERMINAL_SETUP_REF="$1" sh
}

# shellcheck disable=SC2329
bootstrap_ref() {
  TERMINAL_SETUP_REF="$1" uvx --python 3.14 --refresh-package terminal --from "$SETUP_SOURCE" terminal-setup
}

plan_field() {
  sed -n "s/^$1 [^ ]* //p" "$2" | tr '\n' ' ' | sed 's/ *$//'
}

update_local() {
  local target plan outdated apt checked reasons="" updated="" report agents_count=0 agents_updated=""
  echo "$SIDE_NAME: checking the setup release, the tools and the agents..."
  if ! target="$(target_ref)"; then
    echo "!! the latest terminal release could not be read from $RELEASES/latest, so terminal does not update. To update with the installed release, run: terminal update --pinned"
    FAILED=1
    FAILED_STEPS="release lookup"
    return
  fi
  echo "setup: installed $INSTALLED_REF, target $target"
  plan="$(mktemp)"
  if ! run_step "status check" env TERMINAL_STATUS_PLAN="$plan" uvx --from "$SETUP_SOURCE" terminal-setup --only status; then
    rm -f "$plan"
    return
  fi
  outdated="$(plan_field outdated "$plan")"
  apt="$(plan_field apt "$plan")"
  checked="$(plan_field checked "$plan")"
  rm -f "$plan"
  if [[ "$target" != "$INSTALLED_REF" ]]; then
    reasons="setup $INSTALLED_REF -> $target"
  fi
  if [[ -n "$outdated" ]]; then
    reasons="${reasons:+$reasons; }not up to date: $outdated"
  fi
  if [[ -z "$reasons" ]]; then
    echo "setup $target: ok, every tool is up to date"
  else
    echo "setup $target runs, because of $reasons"
    if [[ "$target" =~ $TAG_PATTERN ]]; then
      run_step "setup $target" bootstrap_release "$target" && updated="setup $target"
    else
      run_step "setup $target" bootstrap_ref "$target" && updated="setup $target"
    fi
  fi
  if [[ -n "$apt" ]]; then
    echo "$apt: a newer distro package exists; terminal update leaves distro packages. To upgrade them, run the install command with --update."
  fi
  if command -v agents >/dev/null 2>&1; then
    local side=""
    if ((IS_WSL)); then
      side="--wsl"
    fi
    report="$(mktemp)"
    run_step "agents update" env AGENTS_REPORT="$report" AGENTS_NESTED=1 agents update ${side:+"$side"} || true
    agents_count="$(grep -cE '^(ok|updated) (claude|codex|copilot)$' "$report" || true)"
    agents_updated="$(sed -n 's/^updated //p' "$report" | sed 's/^daemon$/codex daemon/' | tr '\n' ' ' | sed 's/ *$//')"
    rm -f "$report"
  fi
  if [[ -n "$agents_updated" ]]; then
    updated="${updated:+$updated, }$agents_updated"
  fi
  if ((FAILED)); then
    echo "$SIDE_NAME: failed: $FAILED_STEPS${updated:+; updated: $updated}"
  elif [[ -z "$updated" ]]; then
    echo "$SIDE_NAME: Everything is up to date (setup $target, ${checked:-0} tools, $agents_count agents)"
  else
    echo "$SIDE_NAME: updated $updated"
  fi
}

windows_ps1() {
  local win_home
  win_home="$(cd /mnt/c 2>/dev/null && cmd.exe /c 'echo %USERPROFILE%' 2>/dev/null | tr -d '\r')"
  [[ -n "$win_home" ]] || return 1
  printf '%s\n' "$win_home\\.local\\bin\\terminal.ps1"
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
  local args=("$CMD")
  if [[ "$CMD" == status ]]; then
    args+=(--win)
  fi
  if ((PINNED)); then
    args+=(--pinned)
  fi
  (cd /mnt/c && "$shell" -NoProfile -ExecutionPolicy Bypass -File "$ps1" "${args[@]}") || FAILED=1
}

windows_present() {
  local ps1
  ps1="$(windows_ps1)" || return 1
  [[ -f "$(wslpath -u "$ps1" 2>/dev/null)" ]]
}

if [[ "$CMD" == update ]]; then
  if [[ "$TARGET" == --win ]] || { [[ "$IS_WSL" == 1 && "$TARGET" != --wsl ]] && windows_present; }; then
    run_windows
  else
    if [[ "$IS_WSL" == 1 && "$TARGET" != --wsl ]]; then
      echo "terminal.ps1 is not on Windows, so terminal updates only WSL."
    fi
    update_local
  fi
  exit "$FAILED"
fi
if [[ "$TARGET" != --win ]]; then
  run_local
fi
if [[ "$TARGET" != --wsl && "$IS_WSL" == 1 ]]; then
  run_windows
fi
exit "$FAILED"