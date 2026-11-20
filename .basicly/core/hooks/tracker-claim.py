from __future__ import annotations

import fnmatch
import importlib.util
import json
import os
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path
from typing import Any

LEDGER = Path(".basicly") / "ledger"
PLACES = ((Path(".basicly") / "core" / "kit" / "tracker" / "cli.py").as_posix(),)
LOCATE = Path(__file__).resolve().parent.parent / "kit" / "tracker" / "locate.py"
LEDGER_FILES = ("events-*.jsonl", "pending-*.jsonl")


def _harness(module: Any) -> Any:
    factory = getattr(module, "harness", None)
    if not callable(factory):
        raise ImportError(
            "the tracker kit lacks vault harness support; reinstall with `basicly install --force`"
        )
    return factory()


def _kit_module(name: str) -> Any:
    path = LOCATE.parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"basicly_tracker_kit_{name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {name}.py is missing at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"basicly_tracker_kit_{name}"] = module
    spec.loader.exec_module(module)
    return module


def _locate() -> Any:
    return _kit_module("locate")


def _project_root() -> Path:
    cwd = Path.cwd()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / ".git").exists():
            return candidate
    return cwd


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603 B607
        ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", check=False
    )


def _check_staged_claim(root: Path, message: str, tracker: Any) -> subprocess.CompletedProcess[str]:
    if (root / ".basicly-tracker.toml").is_file():
        return subprocess.run(  # nosec B603
            [*tracker.argv(sys.executable), "commit-check", str(root / LEDGER), message],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    staged = _git(root, "diff", "--cached", "--name-only")
    if staged.returncode != 0:
        sys.stderr.write(f"tracker-claim: cannot read staged paths: {staged.stderr}\n")
        raise ValueError("could not read staged Git state")
    with tempfile.TemporaryDirectory(prefix="basicly-staged-ledger-") as scratch:
        directory = Path(scratch)
        snapshot = directory / LEDGER
        snapshot.mkdir(parents=True)
        listed = _git(
            root,
            "ls-files",
            "-z",
            "--",
            *(str(LEDGER / glob) for glob in ("events-*.jsonl", "pending-*.jsonl")),
        )
        if listed.returncode != 0:
            sys.stderr.write(f"tracker-claim: cannot list staged ledger files: {listed.stderr}\n")
            raise ValueError("could not read staged Git state")
        modes = _git(
            root,
            "ls-files",
            "--stage",
            "-z",
            "--",
            *(str(LEDGER / glob) for glob in ("events-*.jsonl", "pending-*.jsonl")),
        )
        if modes.returncode != 0:
            raise ValueError("could not read staged Git modes")
        if any(entry.startswith("120000 ") for entry in modes.stdout.split("\0")):
            sys.stderr.write(
                "tracker-claim: the staged ledger contains a symlink; stage regular event files\n"
            )
            raise ValueError("the staged ledger contains a symlink")
        exported = subprocess.run(  # nosec B603 B607
            ["git", "checkout-index", "--stdin", "-z", f"--prefix={directory.as_posix()}/"],
            input=listed.stdout,
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if exported.returncode != 0:
            sys.stderr.write(f"tracker-claim: cannot read staged ledger: {exported.stderr}\n")
            raise ValueError("could not read staged Git state")
        return _commit_check(root, tracker, snapshot, message, staged.stdout)


def _commit_check(
    root: Path, tracker: Any, snapshot: Path, message: str, staged: str
) -> subprocess.CompletedProcess[str]:
    check = [
        "commit-check",
        str(snapshot),
        message,
        "--stdin",
        "--ledger-label",
        LEDGER.as_posix(),
        "--runner",
        tracker.typed(),
    ]
    return subprocess.run(  # nosec B603
        [*tracker.argv(sys.executable), *check],
        input=staged,
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def _target_git(target: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    return subprocess.run(  # nosec B603 B607
        ["git", *args],
        cwd=target,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def _check_redirect_claim(
    root: Path, message: str, tracker: Any
) -> subprocess.CompletedProcess[str] | None:
    if not (root / LEDGER / "redirect").is_file():
        return None
    layout = _kit_module("git_layout")
    try:
        target = layout.redirect_target(root / LEDGER, root)
    except layout.RedirectError as exc:
        sys.stderr.write(f"tracker-claim: {exc}\n")
        raise ValueError("the ledger redirect is broken") from exc
    if target is None:
        return None
    listed = _target_git(target, "ls-tree", "-z", "HEAD", "--", f"{LEDGER.as_posix()}/")
    staged = _git(root, "diff", "--cached", "--name-only")
    if listed.returncode != 0 or staged.returncode != 0:
        sys.stderr.write(f"tracker-claim: cannot read the ledger of {target} at HEAD\n")
        raise ValueError("could not read the redirect target")
    with tempfile.TemporaryDirectory(prefix="basicly-redirect-ledger-") as scratch:
        snapshot = Path(scratch) / LEDGER
        snapshot.mkdir(parents=True)
        for entry in filter(None, listed.stdout.split("\0")):
            info, _, path = entry.partition("\t")
            name = Path(path).name
            if not any(fnmatch.fnmatch(name, glob) for glob in LEDGER_FILES):
                continue
            if info.startswith("120000 "):
                sys.stderr.write("tracker-claim: the redirect target ledger holds a symlink\n")
                raise ValueError("the redirect target ledger contains a symlink")
            shown = _target_git(target, "show", f"HEAD:{path}")
            if shown.returncode != 0:
                raise ValueError("could not read the redirect target")
            (snapshot / name).write_text(shown.stdout, encoding="utf-8")
        return _commit_check(root, tracker, snapshot, message, staged.stdout)


def _exempt(root: Path, paths: list[str]) -> bool:
    if paths and (root / ".basicly-tracker.toml").is_file():
        return False
    if not paths or not (root / LEDGER).is_dir():
        return True
    if _git(root, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode == 0:
        return True
    if all(_git(root, "cat-file", "-e", f"HEAD:{place}").returncode for place in PLACES):
        sys.stderr.write("tracker-claim: this commit installs the tracker, so it needs no claim\n")
        return True
    return False


def main(argv: list[str] | None = None) -> int:
    paths = list(argv if argv is not None else sys.argv[1:])
    root = _project_root()
    if (
        (root / ".basicly-tracker.toml").exists()
        or (root / LEDGER).is_file()
        or (root / ".basicly/ledger-archive").exists()
    ):
        try:
            _harness(_locate()).harness_config(root)
        except (ValueError, OSError, ImportError) as exc:
            sys.stderr.write(f"tracker-claim: {exc}\n")
            return 1
    if _exempt(root, paths):
        return 0
    locate = _locate()
    tracker = locate.locate(root, PLACES)
    if tracker is None:
        sys.stderr.write(f"tracker-claim: {locate.missing(root, LEDGER.as_posix(), PLACES)}\n")
        return 1
    try:
        done = _check_staged_claim(root, paths[0], tracker)
        if done.returncode != 0:
            shared = _check_redirect_claim(root, paths[0], tracker)
            done = shared if shared is not None and shared.returncode == 0 else done
    except ValueError:
        return 1
    if done.returncode == 0:
        try:
            report = json.loads(done.stdout)
        except ValueError:
            report = {}
        if warning := report.get("warning"):
            sys.stderr.write(f"tracker-claim: {warning}; run `{report.get('next', '')}`\n")
        return 0
    try:
        report = json.loads(done.stdout)
        refused = report.get("refused") or done.stdout
        if remedy := report.get("next"):
            refused += f"; next: {remedy}"
    except ValueError:
        refused = done.stdout + done.stderr
    sys.stderr.write(f"tracker-claim: {refused}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
