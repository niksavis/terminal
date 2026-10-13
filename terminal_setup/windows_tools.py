from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass
from enum import Enum, auto
from functools import partial
from pathlib import Path, PureWindowsPath

from . import release_install
from .platform import PlatformInfo, setup_command
from .prerequisites import (
    _add_to_user_path,
    _ensure_wezterm_user_install,
    attempt,
    is_user_scope,
    read_user_path_entries,
    remove_from_user_path,
    report_release_message,
)
from .runner import Runner

MSVC = r"[^/]*-{arch}-pc-windows-msvc\.zip"


@dataclass(frozen=True)
class WindowsTool:
    command: str
    repo: str
    patterns: tuple[str, ...]


WINDOWS_TOOLS = (
    WindowsTool("rg", "BurntSushi/ripgrep", (MSVC,)),
    WindowsTool("fd", "sharkdp/fd", (MSVC,)),
    WindowsTool("bat", "sharkdp/bat", (MSVC,)),
    WindowsTool("jq", "jqlang/jq", (r"jq-windows-{arch}\.exe",)),
    WindowsTool("yq", "mikefarah/yq", (r"yq_windows_{arch}\.exe",)),
    WindowsTool("ast-grep", "ast-grep/ast-grep", (MSVC,)),
    WindowsTool("sd", "chmln/sd", (MSVC,)),
    WindowsTool("delta", "dandavison/delta", (MSVC,)),
    WindowsTool("typos", "crate-ci/typos", (MSVC,)),
    WindowsTool("just", "casey/just", (MSVC,)),
    WindowsTool("xh", "ducaale/xh", (MSVC,)),
    WindowsTool("shellcheck", "koalaman/shellcheck", (r"shellcheck-v[0-9.]+\.zip",)),
    WindowsTool("fzf", "junegunn/fzf", (r"fzf-[0-9.]+-windows_{arch}\.zip",)),
    WindowsTool("lazygit", "jesseduffield/lazygit", (r"lazygit_[0-9.]+_windows_{arch}\.zip",)),
)
STARSHIP = WindowsTool("starship", "starship/starship", (MSVC,))
WINGET_SOURCE_SUFFIX = "_Microsoft.Winget.Source_"


class Origin(Enum):
    MISSING = auto()
    OURS = auto()
    LEGACY = auto()
    WINGET = auto()
    MACHINE = auto()
    OTHER = auto()


ORIGIN_LABELS = {
    Origin.MISSING: "not found",
    Origin.OURS: "terminal-tools",
    Origin.LEGACY: "old setup folder",
    Origin.WINGET: "winget",
    Origin.MACHINE: "machine-wide",
    Origin.OTHER: "user profile",
}


def _same_dir(path: PureWindowsPath, directory: Path) -> bool:
    return str(path).lower().rstrip("\\") == str(PureWindowsPath(directory)).lower().rstrip("\\")


def legacy_dirs(platform: PlatformInfo, tool: WindowsTool) -> tuple[Path, ...]:
    if tool.command != "starship":
        return ()
    old = platform.user_programs_dir / "starship"
    return (old, old / "bin")


def winget_package_dir(path: str) -> PureWindowsPath | None:
    parts = PureWindowsPath(path).parts
    lowered = [part.lower() for part in parts]
    for index in range(len(parts) - 3):
        if (
            lowered[index : index + 3] == ["microsoft", "winget", "packages"]
            and WINGET_SOURCE_SUFFIX.lower() in lowered[index + 3]
        ):
            return PureWindowsPath(*parts[: index + 4])
    return None


def winget_id(package_dir: PureWindowsPath) -> str:
    return package_dir.name.split(WINGET_SOURCE_SUFFIX, 1)[0]


def classify(path: str | None, platform: PlatformInfo, tool: WindowsTool) -> Origin:
    if path is None:
        return Origin.MISSING
    parent = PureWindowsPath(path).parent
    if _same_dir(parent, platform.terminal_tools_dir):
        return Origin.OURS
    if any(_same_dir(parent, old) for old in legacy_dirs(platform, tool)):
        return Origin.LEGACY
    if not is_user_scope(path, platform):
        return Origin.MACHINE
    if winget_package_dir(path) is not None:
        return Origin.WINGET
    return Origin.OTHER


def _resolved(path: str) -> str:
    try:
        return str(Path(path).resolve())
    except OSError:
        return path


def all_copies(command: str, platform: PlatformInfo) -> list[str]:
    copies: list[str] = []
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry or _same_dir(PureWindowsPath(entry), platform.terminal_tools_dir):
            continue
        which = shutil.which(command, path=entry)
        if which is None:
            continue
        found = _resolved(which)
        if all(found.lower() != known.lower() for known in copies):
            copies.append(found)
    return copies


def _install(runner: Runner, platform: PlatformInfo, tool: WindowsTool, *, update: bool) -> Path:
    target = platform.terminal_tools_dir
    executable = target / f"{tool.command}.exe"
    runner.reporter.command(
        [tool.repo, f"{tool.command}.exe"], f"install {tool.command} into {target}"
    )
    if runner.dry_run:
        return executable
    try:
        message = release_install.run(
            tool.repo,
            f"{tool.command}.exe",
            update,
            list(tool.patterns),
            bin_dir=target,
            state_dir=platform.setup_data_dir / "releases",
        )
    except release_install.InstallError as error:
        raise RuntimeError(f"{tool.command}: {error}") from error
    report_release_message(runner, message)
    return executable


def _verify(runner: Runner, executable: Path) -> None:
    if runner.dry_run:
        return
    result = runner.run([str(executable), "--version"], check=False, dry_run_safe=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"{executable} --version failed with exit code {result.returncode}; "
            "setup keeps the existing copy"
        )


def _replace_wanted(runner: Runner, policy: str | None, prompt: str) -> bool:
    if policy == "replace":
        return True
    if policy == "keep" or runner.unattended:
        return False
    if runner.dry_run:
        runner.reporter.prompt(f"{prompt} (answer 'no' by default in dry-run mode)")
        return False
    return runner.confirm(prompt)


def _path_backup(platform: PlatformInfo) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return platform.setup_data_dir / f"user-path-{stamp}.txt"


def _drop_path_entries(runner: Runner, platform: PlatformInfo, gone: list[PureWindowsPath]) -> None:
    stale: list[str] = []
    for entry in read_user_path_entries(runner):
        expanded = PureWindowsPath(os.path.expandvars(entry))
        for root in gone:
            inside = str(expanded).lower().startswith(str(root).lower().rstrip("\\"))
            if inside and (runner.dry_run or not Path(str(expanded)).exists()):
                stale.append(entry)
                break
    remove_from_user_path(runner, stale, _path_backup(platform))


def _uninstall_winget(runner: Runner, platform: PlatformInfo, package_dir: PureWindowsPath) -> None:
    runner.run(
        [
            "winget",
            "uninstall",
            "--id",
            winget_id(package_dir),
            "--exact",
            "--scope",
            "user",
            "--silent",
            "--disable-interactivity",
            "--accept-source-agreements",
        ],
        interactive=True,
        label=f"winget uninstall {winget_id(package_dir)}",
    )
    _drop_path_entries(runner, platform, [package_dir])


def _retire_legacy(runner: Runner, platform: PlatformInfo, tool: WindowsTool) -> None:
    old = platform.user_programs_dir / tool.command
    runner.reporter.info(f"remove the old {tool.command} folder {old}")
    if not runner.dry_run and old.is_dir():
        shutil.rmtree(old)
    _drop_path_entries(runner, platform, [PureWindowsPath(old)])


def _keep_message(tool: str, path: str, reason: str) -> str:
    return f"{tool}: keeps {path} ({reason}); setup installs no second copy"


def _keep_winget_message(tool: str, path: str) -> str:
    return (
        _keep_message(tool, path, "from winget")
        + f"; to replace it, run: {setup_command('--winget-versions replace')}"
    )


def ensure_tool(
    runner: Runner,
    platform: PlatformInfo,
    tool: WindowsTool,
    *,
    update: bool,
    policy: str | None,
) -> None:
    copies = all_copies(tool.command, platform)
    found = copies[0] if copies else None
    origin = classify(found, platform, tool)
    package_dir = winget_package_dir(found) if found else None
    if found is None or origin == Origin.OURS:
        _install(runner, platform, tool, update=update)
    elif origin == Origin.LEGACY:
        _verify(runner, _install(runner, platform, tool, update=update))
        _retire_legacy(runner, platform, tool)
    elif origin == Origin.MACHINE:
        runner.reporter.info(
            _keep_message(tool.command, found, "machine-wide; removing it needs administrator")
        )
    elif origin == Origin.WINGET and package_dir is not None:
        prompt = (
            f"{tool.command} at {found} came from winget ({winget_id(package_dir)}). "
            f"Replace it with the setup copy in {platform.terminal_tools_dir}?"
        )
        if _replace_wanted(runner, policy, prompt):
            _verify(runner, _install(runner, platform, tool, update=update))
            _uninstall_winget(runner, platform, package_dir)
        else:
            runner.reporter.info(_keep_winget_message(tool.command, found))
    else:
        runner.reporter.info(_keep_message(tool.command, found, "not from setup or winget"))
    remove_hidden_winget(runner, platform, tool.command, copies[1:], policy=policy)


def remove_hidden_winget(
    runner: Runner, platform: PlatformInfo, command: str, hidden: list[str], *, policy: str | None
) -> None:
    for path in hidden:
        package_dir = winget_package_dir(path)
        if package_dir is None or not is_user_scope(path, platform):
            continue
        prompt = (
            f"{command} at {path} came from winget ({winget_id(package_dir)}) and never runs, "
            "because another copy comes first on PATH. Uninstall the unused winget copy?"
        )
        if _replace_wanted(runner, policy, prompt):
            _uninstall_winget(runner, platform, package_dir)
            continue
        runner.reporter.info(
            f"{command}: keeps the unused winget copy at {path}; to remove it, run: "
            f"{setup_command('--winget-versions replace')}"
        )


def replace_winget_wezterm(runner: Runner, platform: PlatformInfo, *, policy: str | None) -> None:
    copies = all_copies("wezterm", platform)
    remove_hidden_winget(runner, platform, "wezterm", copies[1:], policy=policy)
    found = copies[0] if copies else None
    package_dir = winget_package_dir(found) if found else None
    if found is None or package_dir is None or not is_user_scope(found, platform):
        return
    prompt = (
        f"WezTerm at {found} came from winget ({winget_id(package_dir)}). "
        f"Replace it with the setup copy in {platform.user_programs_dir / 'WezTerm'}?"
    )
    if not _replace_wanted(runner, policy, prompt):
        runner.reporter.info(_keep_winget_message("wezterm", found))
        return
    _ensure_wezterm_user_install(runner, platform)
    _verify(runner, platform.user_programs_dir / "WezTerm" / "wezterm.exe")
    _uninstall_winget(runner, platform, package_dir)


def ensure_windows_tools(
    runner: Runner,
    platform: PlatformInfo,
    *,
    update: bool,
    policy: str | None,
    include_starship: bool,
) -> None:
    tools = (*WINDOWS_TOOLS, STARSHIP) if include_starship else WINDOWS_TOOLS
    target = platform.terminal_tools_dir
    runner.ensure_dir(target)
    for tool in tools:
        attempt(
            runner,
            f"install {tool.command} on Windows",
            partial(ensure_tool, runner, platform, tool, update=update, policy=policy),
        )
    if runner.dry_run or any(target.glob("*.exe")):
        _add_to_user_path(runner, target)
    attempt(
        runner,
        "replace a winget WezTerm",
        partial(replace_winget_wezterm, runner, platform, policy=policy),
    )
