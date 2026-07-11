#!/usr/bin/env bash

set -Eeuo pipefail

TARGET_VERSION="26.04"
BACKUP_DIR_UNIX="/d/WSL-Backups"
BACKUP_DIR_WIN="D:\\WSL-Backups"

DISTRO=""
BACKUP_TAR_UNIX=""
BACKUP_TAR_WIN=""
UPGRADE_LOG=""
SETUP_REPORT_LOG=""

log() {
    printf '[INFO] %s\n' "$*"
}

warn() {
    printf '[WARN] %s\n' "$*"
}

die() {
    printf '[ERROR] %s\n' "$*" >&2
    exit 1
}

print_cmd() {
    printf '\n[CMD] '
    printf '%q ' "$@"
    printf '\n'
}

run() {
    print_cmd "$@"
    "$@"
}

run_capture() {
    print_cmd "$@" >&2
    "$@"
}

run_with_tee() {
    local logfile="$1"
    shift

    print_cmd "$@"
    set +e
    "$@" 2>&1 | tee "$logfile"
    local rc=${PIPESTATUS[0]}
    set -e
    return "$rc"
}

contains_line_exact() {
    local needle="$1"
    shift
    local line
    for line in "$@"; do
        if [[ "$line" == "$needle" ]]; then
            return 0
        fi
    done
    return 1
}

choose_distro() {
    local -a distros=()
    mapfile -t distros < <(
        wsl --list --quiet \
            | tr -d '\000' \
            | tr -d '\r' \
            | sed '/^[[:space:]]*$/d; s/^[[:space:]]*//; s/[[:space:]]*$//'
    )

    if contains_line_exact "Ubuntu-24.04" "${distros[@]}"; then
        DISTRO="Ubuntu-24.04"
        return 0
    fi

    if contains_line_exact "Ubuntu" "${distros[@]}"; then
        DISTRO="Ubuntu"
        return 0
    fi

    return 1
}

should_retry_with_dev_channel() {
    local logfile="$1"
    grep -Eiq 'No new release found|no supported upgrades|development release|could not calculate the upgrade|meta-release' "$logfile"
}

detect_repo_path() {
    local home_dir=""
    home_dir="$(run_capture wsl -d "$DISTRO" -- bash -lc 'printf "%s" "$HOME"')"

    local -a candidates=(
        "$home_dir/development/terminal"
        "$home_dir/terminal"
        "$home_dir/src/terminal"
    )

    local candidate=""
    local escaped_candidate=""
    for candidate in "${candidates[@]}"; do
        printf -v escaped_candidate '%q' "$candidate"
        if wsl -d "$DISTRO" -- bash -lc "[[ -d ${escaped_candidate} ]]"; then
            wsl -d "$DISTRO" -- bash -lc "cd ${escaped_candidate} && pwd"
            return 0
        fi
    done

    return 1
}

main() {
    log "Step 1: Detect distro and prepare backup path"
    run wsl --list --quiet

    if ! choose_distro; then
        die "Neither Ubuntu-24.04 nor Ubuntu exists. Stopping."
    fi

    log "Selected distro: ${DISTRO}"

    run mkdir -p "$BACKUP_DIR_UNIX"

    local timestamp
    timestamp="$(date +%Y%m%d-%H%M%S)"
    BACKUP_TAR_UNIX="${BACKUP_DIR_UNIX}/${DISTRO}-pre-${TARGET_VERSION}-${timestamp}.tar"
    BACKUP_TAR_WIN="${BACKUP_DIR_WIN}\\${DISTRO}-pre-${TARGET_VERSION}-${timestamp}.tar"

    log "Planned backup file: ${BACKUP_TAR_WIN}"

    log "Step 2: Backup distro"
    run wsl --shutdown
    run wsl --export "$DISTRO" "$BACKUP_TAR_WIN"

    if [[ ! -f "$BACKUP_TAR_UNIX" ]]; then
        die "Backup file was not created at ${BACKUP_TAR_UNIX}."
    fi

    run ls -lh "$BACKUP_TAR_UNIX"

    log "Step 3: Pre-upgrade package prep inside distro"
    run wsl -d "$DISTRO" -- bash -lc "sudo apt update && sudo apt full-upgrade -y && sudo apt install -y update-manager-core ubuntu-release-upgrader-core"
    run wsl -d "$DISTRO" -- bash -lc "sudo sed -i 's/^Prompt=.*/Prompt=lts/' /etc/update-manager/release-upgrades; grep '^Prompt=' /etc/update-manager/release-upgrades"

    local from_release
    from_release="$(run_capture wsl -d "$DISTRO" -- bash -lc "cat /etc/os-release | egrep '^(PRETTY_NAME|VERSION=|VERSION_ID=)'")"

    printf '\n[CONFIRM] About to start in-place release upgrade for %s to Ubuntu %s.\n' "$DISTRO" "$TARGET_VERSION"
    read -r -p "Type UPGRADE to continue: " confirm_upgrade
    if [[ "$confirm_upgrade" != "UPGRADE" ]]; then
        warn "Upgrade canceled by user before release upgrade started."
        printf '\nBackup file remains available at: %s\n' "$BACKUP_TAR_WIN"
        return 0
    fi

    log "Step 4: In-place upgrade"
    UPGRADE_LOG="/tmp/${DISTRO}-upgrade-${timestamp}.log"

    if run_with_tee "$UPGRADE_LOG" wsl -d "$DISTRO" -- bash -lc "sudo do-release-upgrade -f DistUpgradeViewNonInteractive"; then
        log "Primary release upgrade command completed."
    else
        if should_retry_with_dev_channel "$UPGRADE_LOG"; then
            warn "Primary release detection did not find target release. Retrying with -d."
            if ! run_with_tee "$UPGRADE_LOG" wsl -d "$DISTRO" -- bash -lc "sudo do-release-upgrade -d -f DistUpgradeViewNonInteractive"; then
                die "Release upgrade retry with -d failed. See log: ${UPGRADE_LOG}"
            fi
        else
            die "Release upgrade failed. See log: ${UPGRADE_LOG}"
        fi
    fi

    log "Step 5: Post-upgrade cleanup and verification"
    run wsl -d "$DISTRO" -- bash -lc "sudo apt autoremove -y && sudo apt clean"
    local to_release
    to_release="$(run_capture wsl -d "$DISTRO" -- bash -lc "cat /etc/os-release | egrep '^(PRETTY_NAME|VERSION=|VERSION_ID=)'")"
    run wsl --shutdown

    log "Step 6: Re-apply terminal setup from repo"
    local repo_path
    if ! repo_path="$(detect_repo_path)"; then
        die 'Repo path not found in distro under $HOME (checked: ~/development/terminal, ~/terminal, ~/src/terminal).'
    fi

    log "Detected repo path inside distro: ${repo_path}"

    SETUP_REPORT_LOG="/tmp/${DISTRO}-setup-report-${timestamp}.log"
    local setup_script
    setup_script=$(cat <<EOF
set -euo pipefail
command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="\$HOME/.local/bin:\$PATH"
cd "${repo_path}"
uv sync
uv run python setup-terminal.py --report
EOF
)

    if ! run_with_tee "$SETUP_REPORT_LOG" wsl -d "$DISTRO" -- bash -lc "$setup_script"; then
        die "Re-applying terminal setup failed. See log: ${SETUP_REPORT_LOG}"
    fi

    local ok_count missing_count
    ok_count="$(grep -c '\[REPORT\]\[OK\]' "$SETUP_REPORT_LOG" || true)"
    missing_count="$(grep -c '\[REPORT\]\[MISSING\]' "$SETUP_REPORT_LOG" || true)"

    log "Step 7: Final summary"
    printf '\n========== FINAL SUMMARY =========='
    printf '\nBackup file path: %s\n' "$BACKUP_TAR_WIN"
    printf 'Distro upgraded: %s\n' "$DISTRO"
    printf '\nFrom:\n%s\n' "$from_release"
    printf '\nTo:\n%s\n' "$to_release"
    printf '\nsetup-terminal report highlights: [REPORT][OK]=%s, [REPORT][MISSING]=%s\n' "$ok_count" "$missing_count"

    if [[ "$missing_count" != "0" ]]; then
        printf '\nMissing tools/configs reported:\n'
        grep '\[REPORT\]\[MISSING\]' "$SETUP_REPORT_LOG" || true
        printf '\nManual steps: install/fix the above missing items, then rerun setup report.\n'
    else
        printf '\nManual steps: none reported by setup-terminal --report.\n'
    fi

    printf '\nRollback commands (not executed):\n'
    printf 'wsl --shutdown\n'
    printf 'wsl --unregister "%s"\n' "$DISTRO"
    printf 'wsl --import "%s" "C:\\WSL\\%s" "%s" --version 2\n' "$DISTRO" "$DISTRO" "$BACKUP_TAR_WIN"

    printf '\nLogs:\n'
    printf 'Upgrade log: %s\n' "$UPGRADE_LOG"
    printf 'Setup report log: %s\n' "$SETUP_REPORT_LOG"
}

main "$@"
