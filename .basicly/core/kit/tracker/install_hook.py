from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any

HOOK_NAME = "post-merge"

GIT_DIR_NAME = ".git"
_GIT_DIR_MARK = "gitdir:"
DEFAULT_HOOKS_DIR = "hooks"
HOOKS_PATH_KEY = "hookspath"

DEFAULT_INTERPRETER = "uv run --no-project --no-python-downloads python"

BEGIN = "# >>> basicly-tracker compact >>>"
END = "# <<< basicly-tracker compact <<<"
CLAIM_HOOK = "commit-msg"
CLAIM_BEGIN = "# >>> basicly-tracker claim >>>"
CLAIM_END = "# <<< basicly-tracker claim <<<"

SHEBANG = "#!/bin/sh"

CLI_FILE = "cli.py"

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside install_hook.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _within(path: Path, root: Path) -> str:

    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(Path(root).resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(
            f"{resolved} is not inside {root}, so no relative command can be written and "
            f"an absolute one would break the next clone"
        ) from exc


def git_dir(root: Path) -> Path | None:

    candidate = root / GIT_DIR_NAME
    if candidate.is_dir():
        return candidate
    if candidate.is_file():
        text = candidate.read_text(encoding="utf-8").strip()
        if text.startswith(_GIT_DIR_MARK):
            linked = Path(text[len(_GIT_DIR_MARK) :].strip())
            return linked if linked.is_absolute() else (root / linked).resolve()
    return None


def hooks_dir(root: Path) -> Path | None:

    found = git_dir(root)
    if found is None:
        return None
    config = found / "config"
    declared = ""
    if config.is_file():
        for line in config.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.strip().partition("=")
            if sep and name.strip().lower() == HOOKS_PATH_KEY:
                declared = value.strip()
    if not declared:
        return found / DEFAULT_HOOKS_DIR
    path = Path(declared)
    return path if path.is_absolute() else (root / path)


ON_DEFAULT_BRANCH = (
    'tracker_default="$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null)"',
    'tracker_default="${tracker_default#origin/}"',
    '[ -n "$tracker_default" ] || tracker_default="$(git config init.defaultBranch)"',
    '[ -n "$tracker_default" ] || tracker_default=main',
    '[ "$(git symbolic-ref --quiet --short HEAD 2>/dev/null)" = "$tracker_default" ] &&',
)


def body(interpreter: str, script: str, ledger: str, command: str = "", advice: str = "") -> str:

    if command:
        return "\n".join((
            BEGIN,
            *ON_DEFAULT_BRANCH[:-1],
            f"if {ON_DEFAULT_BRANCH[-1]}",
            f'  [ -z "$(git status --porcelain -- . ":(exclude){ledger}")" ]; then',
            f"  {command} >/dev/null 2>&1 ||",
            f"    echo 'tracker: the pending shards are not folded; run {advice or command}' >&2",
            "fi",
            END,
        ))
    manual = f"python {script} compact {ledger}"
    missing = "no uv or python on PATH, so the pending shards are not folded"
    return "\n".join((
        BEGIN,
        *ON_DEFAULT_BRANCH[:-1],
        f'if {ON_DEFAULT_BRANCH[-1]} [ -f "{script}" ] &&',
        f'  [ -z "$(git status --porcelain -- . ":(exclude){ledger}")" ]',
        "then",
        '  tracker_run=""',
        f'  for tracker_try in "{interpreter}" python3 python; do',
        '    case "$(command -v "${tracker_try%% *}" 2>/dev/null)" in',
        '      ""|*WindowsApps*) continue ;;',
        "    esac",
        '    tracker_run="$tracker_try"',
        "    break",
        "  done",
        '  if [ -z "$tracker_run" ]; then',
        f"    echo 'tracker: {missing}; run {manual}' >&2",
        f'  elif ! $tracker_run "{script}" compact "{ledger}" >/dev/null 2>&1; then',
        f"    echo 'tracker: the pending shards are not folded; run {manual}' >&2",
        f'  elif [ -n "$(git status --porcelain -- "{ledger}")" ]; then',
        f'    git add "{ledger}" >/dev/null 2>&1',
        '    git commit -q -m "chore(tracker): fold pending shards into the trunk log" \\',
        "      >/dev/null 2>&1 ||",
        '      echo "tracker: folded the shards but could not commit them; the ledger is'
        ' staged and your tree is not clean" >&2',
        "  fi",
        "fi",
        END,
    ))


INSTALLED_SKILLS = ("tracker", "board")
INSTALLED_FILES = (".gitignore", ".gitattributes")


def claim_body(script: str, ledger: str) -> str:
    kit_root = str(Path(script).parent.parent.as_posix())
    installed = [f"{kit_root}/", *INSTALLED_FILES]
    for agents in (".claude", ".agents"):
        installed += [f"{agents}/skills/{name}/" for name in INSTALLED_SKILLS]
    flags = " ".join(f'--installed "{one}"' for one in installed)
    check = f'"$tracker_try" "{script}" commit-check "{ledger}" "$1" --stdin {flags}'
    return "\n".join((
        CLAIM_BEGIN,
        f'if [ -f "{script}" ] && ! git rev-parse -q --verify MERGE_HEAD >/dev/null 2>&1; then',
        "  for tracker_try in python3 python; do",
        '    command -v "$tracker_try" >/dev/null 2>&1 || continue',
        f"    tracker_out=$(git diff --cached --name-only | {check}) ||",
        '      { echo "$tracker_out" >&2; exit 1; }',
        "    break",
        "  done",
        "fi",
        CLAIM_END,
    ))


def _stripped(text: str, begin: str = BEGIN, end: str = END) -> str:

    kept = []
    inside = False
    for line in text.splitlines():
        if line.strip() == begin:
            inside = True
            continue
        if line.strip() == end:
            inside = False
            continue
        if not inside:
            kept.append(line)
    return "\n".join(kept).rstrip("\n")


def merged(current: str, block: str, begin: str = BEGIN, end: str = END) -> str:

    if not current.strip():
        return f"{SHEBANG}\n\n{block}\n"
    kept = _stripped(current, begin, end)
    if not kept.splitlines() or not kept.splitlines()[0].startswith("#!"):
        kept = f"{SHEBANG}\n{kept}"
    return f"{kept.rstrip()}\n\n{block}\n"


def _make_executable(path: Path) -> None:
    try:
        mode = path.stat().st_mode
        path.chmod(mode | 0o111)
    except OSError:
        pass


def install(  # noqa: PLR0913 — one keyword per seam the host injects; a settings object would put an engine type in a stdlib-only kit
    root: Path,
    *,
    ledger: Path,
    dry_run: bool,
    interpreter: str,
    stream: Any,
    command: str = "",
    advice: str = "",
) -> int:

    script = "" if command else _within(_HERE / CLI_FILE, root)
    within = ensure_ledger(root, ledger, dry_run=dry_run, stream=stream)
    directory = hooks_dir(root)
    if directory is None:
        stream.write(
            f"tracker: {root} is not a git checkout, so there is no {HOOK_NAME} to wire; "
            f"run `compact` yourself after a merge\n"
        )
        return 0
    hook = directory / HOOK_NAME
    current = hook.read_text(encoding="utf-8") if hook.is_file() else ""
    wanted = merged(current, body(interpreter, script, within, command, advice))
    if current == wanted:
        stream.write(f"tracker: {HOOK_NAME} already folds shards after a merge\n")
        return 0
    if dry_run:
        stream.write(f"tracker: would write {HOOK_NAME} in {directory}\n")
        return 0
    directory.mkdir(parents=True, exist_ok=True)
    hook.write_text(wanted, encoding="utf-8")
    _make_executable(hook)
    kept = bool(_stripped(current).strip())
    how = "added the compact block to the existing" if kept else "wrote"
    stream.write(f"tracker: {how} {HOOK_NAME} in {directory}\n")
    return 0


def _install_claim(
    directory: Path, script: str, ledger: str, *, dry_run: bool, stream: Any
) -> None:

    hook = directory / CLAIM_HOOK
    current = hook.read_text(encoding="utf-8") if hook.is_file() else ""
    wanted = merged(current, claim_body(script, ledger), CLAIM_BEGIN, CLAIM_END)
    if current == wanted:
        return
    if dry_run:
        stream.write(f"tracker: would write {CLAIM_HOOK} in {directory}\n")
        return
    directory.mkdir(parents=True, exist_ok=True)
    hook.write_text(wanted, encoding="utf-8")
    _make_executable(hook)
    stream.write(f"tracker: {CLAIM_HOOK} now refuses a code commit on a record you do not hold\n")


def ensure_ledger(root: Path, ledger: Path, *, dry_run: bool, stream: Any) -> str:

    within = _within(ledger, root)
    if not ledger.is_dir():
        if dry_run:
            stream.write(f"tracker: would create the ledger {within}\n")
        else:
            ledger.mkdir(parents=True)
            stream.write(f"tracker: created the ledger {within}\n")
    return within


def pin_ledger(ledger: Path, *, dry_run: bool, stream: Any) -> None:

    pin = _load("pin.py", "basicly_tracker_kit_pin")
    if dry_run:
        stream.write(f"tracker: would pin the ledger to tracker {pin.KIT_VERSION}\n")
        return
    pin.write(ledger)
    stream.write(f"tracker: pinned the ledger to tracker {pin.KIT_VERSION}\n")


NO_FOLD = (
    "tracker: no post-merge fold is wired, so a pull request never edits the trunk log; "
    "run `compact` as its own pull request, or pass --fold-on-merge where one writer "
    "pushes to the default branch\n"
)


def _uninstall_claim(directory: Path | None, *, dry_run: bool) -> None:

    hook = directory / CLAIM_HOOK if directory is not None else None
    if hook is None or not hook.is_file() or dry_run:
        return
    current = hook.read_text(encoding="utf-8")
    if CLAIM_BEGIN not in current:
        return
    kept = _stripped(current, CLAIM_BEGIN, CLAIM_END).strip()
    if kept in ("", SHEBANG):
        hook.unlink()
    else:
        hook.write_text(f"{kept}\n", encoding="utf-8")


def install_claim(root: Path, *, ledger: Path, dry_run: bool, stream: Any) -> None:

    directory = hooks_dir(root)
    if directory is not None:
        script = _within(_HERE / CLI_FILE, root)
        _install_claim(directory, script, _within(ledger, root), dry_run=dry_run, stream=stream)


def uninstall(root: Path, *, dry_run: bool, stream: Any) -> int:

    _uninstall_claim(hooks_dir(root), dry_run=dry_run)
    return uninstall_fold(root, dry_run=dry_run, stream=stream)


def uninstall_fold(root: Path, *, dry_run: bool, stream: Any) -> int:

    directory = hooks_dir(root)
    hook = directory / HOOK_NAME if directory is not None else None
    if hook is None or not hook.is_file():
        return 0
    current = hook.read_text(encoding="utf-8")
    if BEGIN not in current:
        stream.write(f"tracker: {HOOK_NAME} carries no block this kit wrote, so it is left alone\n")
        return 0
    if dry_run:
        stream.write(f"tracker: would remove the compact block from {HOOK_NAME}\n")
        return 0
    kept = _stripped(current).strip()
    if kept in ("", SHEBANG):
        hook.unlink()
        stream.write(f"tracker: removed {HOOK_NAME}, which held nothing else\n")
        return 0
    hook.write_text(f"{kept}\n", encoding="utf-8")
    stream.write(f"tracker: removed the compact block from {HOOK_NAME}\n")
    return 0


def main(argv: Any = None) -> int:

    offer = _load("import_offer.py", "basicly_tracker_kit_import_offer")
    parser = argparse.ArgumentParser(
        description=(
            "Wire a post-merge hook that folds every pending writer shard into the "
            "trunk log, so a consumer never has to remember `compact`."
        )
    )
    parser.add_argument("--root", default=".", help="the repository to wire")
    parser.add_argument(
        "--ledger",
        default="",
        help="the ledger directory the hook compacts; defaults beside the vendored kit",
    )
    parser.add_argument(
        "--uninstall", action="store_true", help="remove only the block this writes"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="report what would change and write nothing"
    )
    parser.add_argument(
        "--command",
        default="",
        help="run this instead of the kit, for a host that folds through its own seam",
    )
    parser.add_argument(
        "--advice",
        default="",
        help="the command a reader should type when --command fails; defaults to --command",
    )
    parser.add_argument(
        "--fold-on-merge",
        action="store_true",
        help="wire the fold; safe only where one writer pushes to the default branch",
    )
    parser.add_argument(
        "--pin",
        action="store_true",
        help="pin the ledger to this kit's version; the standalone installer passes it",
    )
    parser.add_argument(
        "--interpreter",
        default=DEFAULT_INTERPRETER,
        help="the command that runs the kit; the default needs only uv",
    )
    parser.add_argument(
        "--import",
        dest="import_source",
        default="",
        choices=offer.SOURCES,
        help="import the backlog of this tracker; without it only a terminal answer imports",
    )
    parser.add_argument(
        "--import-command",
        default=offer.KIT_IMPORT,
        help="the command the offer names, with {source}, {path}, {cli} and {ledger} filled in",
    )
    args = parser.parse_args(None if argv is None else list(argv))
    root = Path(args.root).resolve()
    if args.uninstall:
        return uninstall(root, dry_run=args.dry_run, stream=sys.stdout)
    ledger = Path(args.ledger) if args.ledger else _HERE.parent.parent / "ledger"
    if not ledger.is_absolute():
        ledger = root / ledger
    asked = offer.Install(root, ledger, args.import_source, args.import_command, args.dry_run)
    try:
        backlogs = offer.chosen_backlogs(asked)
    except offer.ImportOfferError as exc:
        raise SystemExit(f"tracker: {exc}") from exc
    ensure_ledger(root, ledger, dry_run=args.dry_run, stream=sys.stdout)
    if args.pin:
        pin_ledger(ledger, dry_run=args.dry_run, stream=sys.stdout)
    if not args.command:
        install_claim(root, ledger=ledger, dry_run=args.dry_run, stream=sys.stdout)
    if not args.fold_on_merge:
        sys.stdout.write(NO_FOLD)
        wired = uninstall_fold(root, dry_run=args.dry_run, stream=sys.stdout)
    else:
        wired = install(
            root,
            ledger=ledger,
            dry_run=args.dry_run,
            interpreter=args.interpreter,
            stream=sys.stdout,
            command=args.command,
            advice=args.advice,
        )
    terminal = sys.stdin is not None and sys.stdin.isatty()
    try:
        offer.offer_import(asked, backlogs, ask=input if terminal else None, stream=sys.stdout)
    except offer.ImportOfferError as exc:
        raise SystemExit(f"tracker: {exc}") from exc
    return wired


if __name__ == "__main__":
    sys.exit(main())
