from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import runner
from orch_lessons.log import RefusedError

from orch_automode import conflicts, render

Claude = Callable[[Path], runner.Done]
GUIDE = (
    "steps: 1. run /auto-mode-setup in Claude Code; 2. orch automode plan --config FILE; "
    "3. orch automode apply --config FILE --plan TOKEN; 4. claude auto-mode critique. "
    "Workers run one guarded step per call: a call that bundles a safe step "
    "with a risky one is refused whole."
)
CONFIG_TIMEOUT_S = 120


@dataclass(frozen=True)
class Planned:
    before: str
    after: str
    made: dict[str, list[str]]
    found: list[conflicts.Conflict]

    @property
    def token(self) -> str:
        return f"{_sha(self.before)}-{_sha(self.after)}"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def add_parsers(groups: argparse._SubParsersAction) -> None:
    auto = groups.add_parser(
        "automode", help="write the auto mode rules orchestrated basicly needs"
    )
    actions = auto.add_subparsers(dest="action", required=True)
    for name in ("plan", "apply"):
        one = actions.add_parser(name)
        one.add_argument("--config", type=Path, required=True)
        one.add_argument("--settings", type=Path)
    actions.choices["apply"].add_argument("--plan", required=True)
    actions.add_parser("guide")


def _dump(document: object) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def settings_path(args: argparse.Namespace, environ: dict[str, str]) -> Path:
    if args.settings is not None:
        return args.settings
    home = Path(environ.get("CLAUDE_CONFIG_DIR") or Path(environ.get("HOME", "~")) / ".claude")
    return home.expanduser() / "settings.json"


def prepare(config_path: Path, settings: Path) -> Planned:
    config = render.load_config(config_path)
    try:
        before = settings.read_text(encoding="utf-8")
        document = json.loads(before)
    except FileNotFoundError as exc:
        raise RefusedError(
            f"automode: {settings} does not exist; run /auto-mode-setup first"
        ) from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RefusedError(f"automode: cannot read {settings} ({exc}); fix the file first") from exc
    if not isinstance(document, dict):
        raise RefusedError(f"automode: {settings} is not a JSON object")
    made = render.entries(config)
    after = _dump(render.merge(document, made, config.drop))
    return Planned(before, after, made, conflicts.find(config, settings))


def show(planned: Planned, settings: Path) -> list[str]:
    old = _dump(json.loads(planned.before)).splitlines(keepends=True)
    diff = difflib.unified_diff(
        old, planned.after.splitlines(keepends=True), str(settings), "planned"
    )
    lines = ["".join(diff).rstrip() or "no change"]
    if "".join(old) != planned.before:
        lines.append("note: apply also rewrites the whole file as JSON indented by 2 spaces")
    lines += [item.line() for item in planned.found]
    whole = json.loads(planned.after)["autoMode"]
    lines.append(
        f"size: {render.size(planned.made)} characters in the generated allow and "
        f"soft_deny entries, {render.size(whole)} in all of them after the merge"
    )
    lines.append(f"plan token: {planned.token}")
    return lines


def claude_config(folder: Path) -> runner.Done:
    env = {**runner.environ(), "CLAUDE_CONFIG_DIR": str(folder)}
    return runner.attempt_env(["claude", "auto-mode", "config"], CONFIG_TIMEOUT_S, env)


def missing(done: runner.Done, made: dict[str, list[str]]) -> list[str]:
    if done.code != 0:
        return [f"claude auto-mode config exited {done.code}: {done.err.strip()[:200]}"]
    try:
        shown = json.loads(done.out)
    except json.JSONDecodeError:
        return ["claude auto-mode config printed no JSON"]
    return [
        f"{kind}: {entry[:60]}"
        for kind, items in made.items()
        for entry in items
        if entry not in shown.get(kind, [])
    ]


def _write(path: Path, text: str) -> None:
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".automode-")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    Path(temp).chmod(path.stat().st_mode & 0o777)
    Path(temp).replace(path)


def apply(planned: Planned, token: str, settings: Path, check: Claude, now: datetime) -> list[str]:
    if token != planned.token:
        raise RefusedError(
            f"automode: plan token {token} does not match {planned.token}; {settings} or the "
            "rules changed since the plan. Run orch automode plan again and read the diff"
        )
    if planned.found:
        raise RefusedError(
            f"automode: {len(planned.found)} conflict(s) left; " + planned.found[0].line()
        )
    with tempfile.TemporaryDirectory(prefix="orch-automode-") as trial:
        (Path(trial) / "settings.json").write_text(planned.after, encoding="utf-8")
        if gaps := missing(check(Path(trial)), planned.made):
            raise RefusedError(
                f"automode: Claude Code did not read the planned rules: {gaps[0]}; nothing written"
            )
    backup = settings.with_name(f"{settings.name}.orch-automode-{now:%Y%m%dT%H%M%SZ}")
    mode = settings.stat().st_mode & 0o777
    with os.fdopen(
        os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode), "w", encoding="utf-8"
    ) as handle:
        handle.write(planned.before)
    _write(settings, planned.after)
    if gaps := missing(check(settings.parent), planned.made):
        _write(settings, planned.before)
        raise RefusedError(
            f"automode: Claude Code did not read the written rules ({gaps[0]}); {settings} restored"
        )
    return [f"written: {settings}", f"backup: {backup}", "next: claude auto-mode critique"]


def run(
    args: argparse.Namespace, _cwd: Path, environ: dict[str, str], check: Claude = claude_config
) -> str | None:
    if args.group != "automode":
        return None
    if args.action == "guide":
        return GUIDE
    settings = settings_path(args, environ)
    planned = prepare(args.config, settings)
    if args.action == "plan":
        lines = show(planned, settings)
        if planned.found:
            raise RefusedError(
                "\n".join(lines)
                + f"\nautomode: {len(planned.found)} conflict(s); apply refuses until none is left"
            )
        return "\n".join(lines)
    return "\n".join(apply(planned, args.plan, settings, check, datetime.now(UTC)))
