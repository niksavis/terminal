#!/usr/bin/env bash
set -uo pipefail

if ((BASH_VERSINFO[0] < 4)); then
  echo "agents needs bash 4 or newer; this shell is bash $BASH_VERSION" >&2
  exit 2
fi

USAGE="usage: agents <status|update|install|uninstall> [--wsl|--win] [--force]"
CMD="update"
TARGET="all"
FORCE=0
for arg in "$@"; do
  case "$arg" in
    status | update | install | uninstall) CMD="$arg" ;;
    --wsl | --win) TARGET="$arg" ;;
    --force | -f) FORCE=1 ;;
    *)
      echo "agents: unknown argument '$arg'" >&2
      echo "$USAGE" >&2
      exit 2
      ;;
  esac
done

export PATH="$HOME/.local/bin:$PATH"
CODEX_DIR="${CODEX_HOME:-$HOME/.codex}"
NAMES=(claude codex daemon copilot)
declare -A LABEL=([claude]="Claude Code" [codex]="Codex" [daemon]="Codex daemon" [copilot]="Copilot CLI")
declare -A NPM_PACKAGE=([claude]="__NPM_CLAUDE__" [codex]="__NPM_CODEX__" [copilot]="__NPM_COPILOT__")
declare -A CUR NEW ST ORIGIN
FAILED=()
NESTED="${AGENTS_NESTED:-}"
SIDE="Linux"
IS_WSL=0
if grep -qi microsoft /proc/version 2>/dev/null; then
  IS_WSL=1
  SIDE="WSL"
fi

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
report() {
  if [[ -n "${AGENTS_REPORT:-}" ]]; then
    printf '%s\n' "$*" >>"$AGENTS_REPORT"
  fi
  return 0
}
step() {
  local name="$1"
  shift
  say "$name"
  if "$@"; then
    echo "$name: done"
  else
    echo "!! $name failed"
    FAILED+=("$name")
  fi
}
semver() { grep -oE '[0-9]+\.[0-9]+\.[0-9]+(-(alpha|beta|rc)(\.[0-9]+)*)?' | head -1; }

locate() {
  local found
  found="$(command -v "$1" 2>/dev/null)" || return 1
  case "$found" in /mnt/*) return 1 ;; esac
  printf '%s\n' "$found"
}
has() { locate "$1" >/dev/null; }

origin() {
  local found real prefix
  found="$(locate "$1")" || {
    echo missing
    return
  }
  real="$(readlink -f "$found" 2>/dev/null || printf '%s' "$found")"
  case "$real" in */node_modules/*)
    echo npm
    return
    ;;
  esac
  case "$real" in */Cellar/* | */Caskroom/*)
    echo brew
    return
    ;;
  esac
  if command -v brew >/dev/null 2>&1; then
    prefix="$(brew --prefix 2>/dev/null)"
    if [[ -n "$prefix" && "$real" == "$prefix"/* ]]; then
      echo brew
      return
    fi
  fi
  echo native
}

brew_name() {
  local real
  real="$(readlink -f "$(locate "$1")" 2>/dev/null)"
  if [[ "$real" =~ /(Cellar|Caskroom)/([^/]+)/ ]]; then
    echo "${BASH_REMATCH[2]}"
  else
    echo "$1"
  fi
}

refuse() {
  local agent="$1" how="$2" verb="$3" fix
  if [[ "$how" == npm && "$verb" == uninstall ]]; then
    fix="npm uninstall -g ${NPM_PACKAGE[$agent]}"
  elif [[ "$how" == npm ]]; then
    fix="npm install -g ${NPM_PACKAGE[$agent]}@latest"
  elif [[ "$verb" == uninstall ]]; then
    fix="brew uninstall $(brew_name "$agent")"
  else
    fix="brew upgrade $(brew_name "$agent")"
  fi
  echo "!! ${LABEL[$agent]} is a $how install, so agents does not $verb it. Run: $fix"
  return 1
}

cur() {
  local found
  found="$(locate "$1")" || return 0
  "$found" --version 2>/dev/null | semver
}
cur_daemon() { readlink "$CODEX_DIR/packages/app-server-daemon/current" 2>/dev/null | sed 's#.*/##' | semver; }

fetch() { curl -fsSL --max-time 15 "$@" 2>/dev/null; }
latest_claude() {
  local channel
  channel="$(grep -oE '"autoUpdatesChannel" *: *"(stable|latest)"' "$HOME/.claude/settings.json" 2>/dev/null | grep -oE '(stable|latest)"$' | tr -d '"')"
  fetch "__CLAUDE_LATEST_URL__/${channel:-latest}" | semver
}
latest_codex() { fetch "__CODEX_LATEST_URL__" | grep -oE '"tag_name" *: *"[^"]*"' | semver; }
latest_copilot() { curl -fsSI --max-time 15 "__COPILOT_LATEST_URL__" 2>/dev/null | grep -i '^location:' | semver; }

state() {
  local installed="$1" latest="$2"
  if [[ -z "$installed" ]]; then
    echo missing
  elif [[ -z "$latest" ]]; then
    echo unknown
  elif [[ "$installed" == "$latest" || "$(printf '%s\n%s\n' "$installed" "$latest" | sort -V | tail -1)" == "$installed" ]]; then
    echo ok
  else
    echo update
  fi
}

check_all() {
  local name
  NEW[claude]="$(latest_claude)"
  NEW[codex]="$(latest_codex)"
  NEW[copilot]="$(latest_copilot)"
  NEW[daemon]="${NEW[codex]}"
  CUR[claude]="$(cur claude)"
  CUR[codex]="$(cur codex)"
  CUR[copilot]="$(cur copilot)"
  CUR[daemon]="$(cur_daemon)"
  ORIGIN[claude]="$(origin claude)"
  ORIGIN[codex]="$(origin codex)"
  ORIGIN[copilot]="$(origin copilot)"
  ORIGIN[daemon]=native
  for name in "${NAMES[@]}"; do
    case "${ORIGIN[$name]}" in
      npm | brew) ST[$name]="${ORIGIN[$name]}" ;;
      *) ST[$name]="$(state "${CUR[$name]}" "${NEW[$name]}")" ;;
    esac
  done
}

changes_only() { [[ -n "${AGENTS_CHANGES_ONLY:-}" ]]; }
any_not_ok() {
  local name
  for name in "${NAMES[@]}"; do
    [[ "${ST[$name]}" != ok ]] && return 0
  done
  return 1
}

print_table() {
  local name color
  if changes_only && ! any_not_ok; then
    return
  fi
  printf '%-8s %-12s %-12s %s\n' agent installed latest state
  for name in "${NAMES[@]}"; do
    if changes_only && [[ "${ST[$name]}" == ok ]]; then
      continue
    fi
    case "${ST[$name]}" in
      ok) color=32 ;;
      unknown) color=31 ;;
      *) color=33 ;;
    esac
    local shown="$name"
    if [[ "$name" == daemon ]]; then
      shown="  daemon"
    fi
    printf '%-8s %-12s %-12s \033[%sm%s\033[0m\n' "$shown" "${CUR[$name]:--}" "${NEW[$name]:-?}" "$color" "${ST[$name]}"
  done
}

needs() { ((FORCE)) || [[ "${ST[$1]}" != ok ]]; }

install_claude() { __CLAUDE_INSTALL__; }
install_codex() { __CODEX_INSTALL__; }
install_copilot() { __COPILOT_INSTALL__; }
install_daemon() { __CODEX_DAEMON_INSTALL__; }

update_agent() {
  local agent="$1" found
  case "${ORIGIN[$agent]}" in
    npm | brew) refuse "$agent" "${ORIGIN[$agent]}" update ;;
    missing) "install_$agent" ;;
    *)
      found="$(locate "$agent")" || {
        "install_$agent"
        return
      }
      "$found" update
      ;;
  esac
}

update_daemon() {
  printf '\033[33mNote: this restarts the Codex daemon and stops running Codex work.\033[0m\n'
  if has codex && codex app-server daemon update; then
    return 0
  fi
  install_daemon
}

uninstall_claude() {
  rm -f "$HOME/.local/bin/claude"
  rm -rf "$HOME/.local/share/claude" "$HOME/.cache/claude"
}
uninstall_codex() {
  if has codex; then
    codex app-server daemon stop >/dev/null 2>&1
  fi
  rm -f "$HOME/.local/bin/codex" "$HOME/.local/bin/codex-code-mode-host"
  rm -rf "$CODEX_DIR/packages"
}
uninstall_copilot() { rm -f "$HOME/.local/bin/copilot"; }

maybe() {
  local agent="$1" action="$2"
  local label="${LABEL[$agent]} ($SIDE)"
  if needs "$agent"; then
    step "$label" "$action" "$agent"
    report "updated $agent"
  else
    changes_only || echo "$label: ok, up to date (${CUR[$agent]})"
    report "ok $agent"
  fi
}

run_local() {
  local name how
  case "$CMD" in
    status)
      check_all
      if [[ -z "${AGENTS_NO_HEADING:-}" ]]; then
        say "$SIDE"
      fi
      print_table
      ;;
    update)
      check_all
      if [[ -z "${AGENTS_NO_HEADING:-}" ]]; then
        say "$SIDE"
      fi
      print_table
      maybe claude update_agent
      maybe codex update_agent
      maybe daemon update_daemon
      maybe copilot update_agent
      ;;
    install)
      for name in claude codex copilot; do
        how="$(origin "$name")"
        if [[ "$how" == npm || "$how" == brew ]]; then
          step "${LABEL[$name]} ($SIDE)" refuse "$name" "$how" install
        elif ((FORCE)) || [[ "$how" == missing ]]; then
          step "${LABEL[$name]} ($SIDE)" "install_$name"
        else
          say "${LABEL[$name]} ($SIDE)"
          echo "already installed"
        fi
      done
      ;;
    uninstall)
      for name in claude codex copilot; do
        how="$(origin "$name")"
        if [[ "$how" == npm || "$how" == brew ]]; then
          step "${LABEL[$name]} ($SIDE)" refuse "$name" "$how" uninstall
        else
          step "${LABEL[$name]} ($SIDE)" "uninstall_$name"
        fi
      done
      ;;
  esac
}

run_windows() {
  local win_home ps1 ps1_linux shell
  win_home="$(cd /mnt/c 2>/dev/null && cmd.exe /c 'echo %USERPROFILE%' 2>/dev/null | tr -d '\r')"
  ps1="$win_home\\.local\\bin\\agents.ps1"
  ps1_linux="$(wslpath -u "$ps1" 2>/dev/null)"
  if [[ -z "$win_home" || -z "$ps1_linux" || ! -f "$ps1_linux" ]]; then
    echo "agents.ps1 is not on Windows, so agents skips Windows. To add it, run the terminal setup on Windows with --agents all."
    return 0
  fi
  shell="$(command -v pwsh.exe || command -v powershell.exe)" || {
    echo "!! Windows: neither pwsh.exe nor powershell.exe is on the PATH"
    FAILED+=("Windows")
    return 0
  }
  local args=("$CMD" --win)
  if ((FORCE)); then
    args+=(--force)
  fi
  (cd /mnt/c && AGENTS_CONFIRMED=1 AGENTS_NESTED=1 WSLENV="AGENTS_CONFIRMED:AGENTS_NESTED:${WSLENV:-}" "$shell" -NoProfile -ExecutionPolicy Bypass -File "$ps1" "${args[@]}") || FAILED+=("Windows")
}

if [[ "$CMD" == uninstall && -z "${AGENTS_CONFIRMED:-}" ]]; then
  read -r -p "Uninstall Claude Code, Codex and Copilot CLI ($TARGET)? The configuration is kept. Type yes: " answer || answer=""
  if [[ "$answer" != yes ]]; then
    echo "Cancelled."
    exit 1
  fi
  export AGENTS_CONFIRMED=1
fi

if [[ "$TARGET" != --win ]]; then
  run_local
fi
if [[ "$TARGET" != --wsl && "$IS_WSL" == 1 ]]; then
  run_windows
fi

if ((${#FAILED[@]})); then
  printf '\n\033[1;31mFailed: %s\033[0m\n' "${FAILED[*]}"
  exit 1
fi
if [[ -z "$NESTED" ]]; then
  printf '\n\033[1;32mAll done.\033[0m\n'
fi
