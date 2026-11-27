from __future__ import annotations

import argparse
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import runner
from orch_lessons.log import RefusedError

WHEEL = "https://github.com/niksavis/basicly/releases/download/v{0}/basicly-{0}-py3-none-any.whl"
RELEASE = re.compile(r"\d+\.\d+\.\d+")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
RECORD = re.compile(r"[a-z][a-z0-9]*-[a-z0-9]+(?:\.\d+)*")
TIMEOUT = 1800
TAIL = 40
USAGE = "orch install --release X.Y.Z --repo NAME=RECORD [--repo NAME=RECORD ...] [--dry-run]"

Exec = Callable[[list[str], Path], runner.Done]


def add_parser(groups: argparse._SubParsersAction) -> None:
    kit = groups.add_parser("install", usage=USAGE)
    kit.add_argument("--release", required=True)
    kit.add_argument("--repo", action="append", required=True)
    kit.add_argument("--dry-run", action="store_true")


def run_step(argv: list[str], cwd: Path) -> runner.Done:
    return runner.attempt(argv, TIMEOUT, str(cwd))


@dataclass(frozen=True)
class Target:
    name: str
    record: str
    root: Path
    lane: str

    @property
    def lane_path(self) -> Path:
        return self.root.parent / f"{self.root.name}.worktrees" / self.lane


def wheel(release: str) -> str:
    if not RELEASE.fullmatch(release):
        raise RefusedError(f"--release {release!r} is not a version like 0.49.4; run: {USAGE}")
    return WHEEL.format(release)


def lane_name(release: str) -> str:
    return "kit-" + release.replace(".", "")


def subject(record: str) -> str:
    return f"chore(basicly): install the released kit ({record})"


def target(workspace: Path, spec: str, release: str) -> Target:
    name, _, record = spec.partition("=")
    if not NAME.fullmatch(name) or not RECORD.fullmatch(record):
        raise RefusedError(
            f"--repo {spec!r} needs a project name and the record that the commit names, "
            f"for example --repo terminal=term-p9q02t; run: {USAGE}"
        )
    root = workspace if name == workspace.name else workspace / name
    if not (root / ".git").exists():
        raise RefusedError(f"--repo {name}: {root} is not a git repository of the workspace")
    return Target(name, record, root, lane_name(release))


def targets(workspace: Path, specs: list[str], release: str) -> list[Target]:
    found = [target(workspace, spec, release) for spec in specs]
    names = [t.name for t in found]
    if len(set(names)) != len(names):
        raise RefusedError(f"--repo names a project twice: {', '.join(names)}")
    return found


def _tail(done: runner.Done) -> str:
    text = (done.err.strip() + "\n" + done.out.strip()).strip()
    return "\n".join(text.splitlines()[-TAIL:])


class Installer:
    def __init__(self, release: str, execute: Exec = run_step) -> None:
        self.release = release
        self.wheel = wheel(release)
        self.execute = execute

    def _step(self, t: Target, step: str, argv: list[str], cwd: Path) -> runner.Done:
        done = self.execute(argv, cwd)
        if done.code == 0:
            return done
        where = (
            f"the lane {t.lane} at {t.lane_path} is left as it is; "
            f"inspect it with git -C {t.lane_path} status"
            if t.lane_path.exists()
            else f"no lane {t.lane} was made"
        )
        raise RefusedError(
            f"install {t.name}: {step} failed (exit {done.code}) in {cwd}; {where}\n{_tail(done)}"
        )

    def _basicly(self, *args: str) -> list[str]:
        return ["uvx", "--from", self.wheel, "basicly", *args]

    def dirty(self, t: Target) -> str | None:
        if not t.lane_path.exists():
            return None
        done = self._step(
            t, "git status", ["git", "--no-optional-locks", "status", "--porcelain"], t.lane_path
        )
        if not done.out.strip():
            return None
        return (
            f"install {t.name}: the lane {t.lane} at {t.lane_path} has uncommitted changes; "
            f"inspect them with git -C {t.lane_path} status, then commit them "
            f"or remove the lane with basicly worktree cleanup {t.lane}"
        )

    def plan(self, t: Target) -> list[str]:
        state = "exists and is clean" if t.lane_path.exists() else "would be created"
        shown = self._step(
            t, "basicly install --dry-run", self._basicly("install", "--dry-run"), t.root
        )
        return [
            f"{t.name}: lane {t.lane} at {t.lane_path} ({state})",
            f"{t.name}: release wheel {self.wheel}",
            f"{t.name}: commit subject {subject(t.record)}",
            *(f"{t.name}: {line}" for line in shown.out.splitlines()),
        ]

    def install(self, t: Target) -> str:
        if t.lane_path.exists():
            top = self._step(t, "git log", ["git", "log", "-1", "--format=%H %s"], t.lane_path)
            head, _, title = top.out.strip().partition(" ")
            if title == subject(t.record):
                return f"{t.name}: lane {t.lane} already holds commit {head} {title}; no new commit"
        else:
            self._step(
                t, "basicly worktree create", self._basicly("worktree", "create", t.lane), t.root
            )
        self._step(t, "basicly install", self._basicly("install"), t.lane_path)
        self._step(t, "git add", ["git", "add", "--all"], t.lane_path)
        staged = self.execute(["git", "diff", "--cached", "--quiet"], t.lane_path)
        if staged.code == 0:
            head = self._step(t, "git rev-parse", ["git", "rev-parse", "HEAD"], t.lane_path)
            return (
                f"{t.name}: lane {t.lane} has no change from basicly {self.release}; "
                f"no commit, lane head {head.out.strip()}"
            )
        body = f"Installs basicly v{self.release} from the release wheel with orch install."
        self._step(
            t, "git commit", ["git", "commit", "-m", subject(t.record), "-m", body], t.lane_path
        )
        head = self._step(t, "git rev-parse", ["git", "rev-parse", "HEAD"], t.lane_path).out.strip()
        return f"{t.name}: lane {t.lane} commit {head} {subject(t.record)}"


def run(
    workspace: Path, release: str, specs: list[str], dry_run: bool, execute: Exec = run_step
) -> Iterator[str]:
    installer = Installer(release, execute)
    chosen = targets(workspace, specs, release)
    refused = [r for r in (installer.dirty(t) for t in chosen) if r]
    if refused:
        raise RefusedError("\n".join(refused))
    for t in chosen:
        if dry_run:
            yield from installer.plan(t)
        else:
            yield installer.install(t)
    if dry_run:
        yield "dry run: nothing written"
