from __future__ import annotations

import base64
import importlib.util
import json
import os
import re
import subprocess  # nosec B404
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any


class MissingRuntimeError(ValueError):
    pass


def project_root() -> Path:
    for root in Path(__file__).resolve().parents:
        if (root / ".git").exists():
            return root
    raise ValueError("hook runtime is outside a Git checkout")


def combine_output(outputs: list[bytes]) -> bytes:
    nonempty = [out for out in outputs if out.strip()]
    if len(nonempty) < 2:
        return b"".join(nonempty)
    merged: dict = {}
    for out in nonempty:
        value = json.loads(out)
        if not isinstance(value, dict):
            raise ValueError("agent hook response must be a JSON object")
        for key, item in value.items():
            if key == "hookSpecificOutput":
                target = merged.setdefault(key, {})
                for name, data in item.items():
                    if name == "additionalContext" and name in target:
                        target[name] += "\n" + data
                    elif name in target and target[name] != data:
                        raise ValueError(f"conflicting agent hook response: {name}")
                    else:
                        target[name] = data
            elif key == "additionalContext" and key in merged:
                merged[key] += "\n" + item
            elif key in merged and merged[key] != item:
                raise ValueError(f"conflicting agent hook response: {key}")
            else:
                merged[key] = item
    return (json.dumps(merged) + "\n").encode()


def matches(spec: dict, payload: dict) -> bool:
    matcher = spec.get("matcher", "")
    if spec["manager"] == "claude" and not matcher:
        matcher = "Edit|Write|NotebookEdit"
    if not matcher or matcher == "*":
        return True
    field = "source" if spec["stage"] == "sessionstart" else "tool_name"
    return re.fullmatch(matcher, str(payload.get(field, ""))) is not None


def staged_paths(root: Path) -> list[str]:
    proc = subprocess.run(  # nosec B603 B607
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
    )
    return [os.fsdecode(path) for path in proc.stdout.split(b"\0") if path]


def record_result(code: int, outputs: list[bytes], errors: list[bytes], agent: bool) -> None:
    target = os.environ.get("BASICLY_HOOK_RESULT")
    if not target:
        if agent:
            raise ValueError("agent dispatcher requires its protocol launcher")
        return
    result: dict = {"code": code}
    if agent:
        result.update({
            "stdout": base64.b64encode(combine_output(outputs)).decode(),
            "stderr": base64.b64encode(b"".join(errors)).decode(),
        })
    Path(target).write_text(json.dumps(result), encoding="utf-8")


def dispatch() -> int:
    root = project_root()
    specs = json.loads(os.environ["BASICLY_HOOK_SPECS"])
    agent = specs[0]["manager"] != "git"
    raw = sys.stdin.buffer.read() if agent else b""
    payload = json.loads(raw or b"{}") if agent else {}
    arguments = json.loads(os.environ.get("BASICLY_HOOK_ARGS", "[]"))
    paths = staged_paths(root) if not agent else []
    exclude = os.environ.get("BASICLY_SECRET_EXCLUDE", "")
    paths = [path for path in paths if not exclude or not re.search(exclude, path)]
    outputs: list[bytes] = []
    errors: list[bytes] = []
    code = 0
    for spec in specs:
        if agent and not matches(spec, payload):
            continue
        files = [path for path in paths if not spec["files"] or re.search(spec["files"], path)]
        if not agent and spec["stage"] == "pre-commit" and not files and not spec["always_run"]:
            continue
        args = arguments if spec["stage"] == "commit-msg" else files
        command = [sys.executable, str(root / spec["script"])]
        if spec["pass_filenames"]:
            command.extend(args)
        proc = subprocess.run(  # nosec B603
            command,
            cwd=root,
            input=raw if agent else None,
            capture_output=agent,
            timeout=spec.get("timeout", 60) if agent else None,
            check=False,
        )
        if agent:
            outputs.append(proc.stdout)
            errors.append(proc.stderr)
        if proc.returncode:
            code = proc.returncode
            break
    record_result(code, outputs, errors, agent)
    return code


def run_foreign_hook(root: Path, arguments: list[str], raw: bytes | None) -> int:
    foreign = os.environ.get("BASICLY_FOREIGN_HOOK")
    if not foreign:
        return 0
    command = [foreign, *arguments]
    if os.name == "nt":
        command = ["sh", "-c", 'exec "$@"', "basicly-foreign-hook", *command]
    return subprocess.run(  # nosec B603 B607
        command, cwd=root, input=raw, check=False
    ).returncode


def adds_commits(root: Path, refs: str) -> bool:
    if not refs.strip():
        return True
    for line in refs.splitlines():
        parts = line.split()
        if len(parts) != 4:
            return True
        local, remote = parts[1], parts[3]
        if set(local) == {"0"} or local == remote:
            continue
        found = subprocess.run(  # nosec B603 B607
            ["git", "rev-list", "--max-count=1", local, "--not", "--remotes"],
            cwd=root,
            env=_clean_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if found.returncode != 0 or found.stdout.strip():
            return True
    return False


def orch_note(root: Path, **fields: object) -> None:
    source = Path(__file__).resolve().parents[1] / "kit" / "orch" / "orch_state" / "note.py"
    spec = importlib.util.spec_from_file_location("basicly_orch_note", source)
    if spec is None or spec.loader is None or not source.is_file():
        return
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        module.note(root, os.environ, **fields)
    except OSError, ValueError, ImportError:
        return


def runtime_module(name: str):
    source = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"basicly_{name}", source)
    if spec is None or spec.loader is None:
        raise ValueError("hook runtime is missing; run basicly hooks-build")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _snapshot(
    manager: str, stage: str, root: Path, directory: Path, env: dict[str, str]
) -> tuple[Any, Path]:
    if manager != "git" or stage not in ("pre-commit", "pre-push"):
        return None, root
    module = runtime_module("staged-snapshot")
    pushed = module.pushed_commit(env.get("BASICLY_PUSH_REFS", "")) if stage == "pre-push" else None
    if stage == "pre-push" and not pushed:
        return None, root
    state = module.prepare(root, directory, pushed)
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        env.pop(key, None)
    env.update(module.job_env(state, stage))
    return ((module, state) if stage == "pre-commit" else None), state.tree


CORE_KEYS = ("core.worktree", "core.bare")


def _clean_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def common_config(root: Path) -> Path:
    found = subprocess.run(  # nosec B603 B607
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=root,
        env=_clean_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return Path(found.stdout.strip()) / "config"


def core_settings(config: Path) -> dict[str, str]:
    values = {}
    for key in CORE_KEYS:
        read = subprocess.run(  # nosec B603 B607
            ["git", "config", "--file", str(config), "--get", key],
            cwd=config.anchor,
            env=_clean_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if read.returncode == 0:
            values[key] = read.stdout.strip()
    return values


def changed_core(stage: str, config: Path, before: dict[str, str]) -> int:
    after = core_settings(config)
    changed = [key for key in CORE_KEYS if before.get(key) != after.get(key)]
    for key in changed:
        old = before.get(key)
        repair = (
            f"git config --file {config} --unset {key}"
            if old is None
            else f"git config --file {config} {key} {old}"
        )
        print(
            f"basicly hook: the {stage} hook run changed {key} in {config} to "
            f"{after.get(key)!r}; a job ran git with the hook's GIT_ variables. "
            f"Repair it with: {repair}",
            file=sys.stderr,
        )
    return 1 if changed else 0


def launch(manager: str, stage: str, arguments: list[str]) -> int:
    if manager != "git":
        return _launch(manager, stage, arguments)
    config = common_config(project_root())
    before = core_settings(config)
    code = _launch(manager, stage, arguments)
    return changed_core(stage, config, before) or code


def _finish_git(
    launch: tuple[list[str], Path, dict[str, str], bytes | None],
    code: int,
    result_path: Path,
    snapshot_state: Any,
    hook: tuple[str, Path],
) -> int:
    command, run_root, env, raw = launch
    stage, root = hook
    if code == 0 and not result_path.is_file():
        command[3:3] = ["--force", "--job", "basicly-dispatch"]
        code = subprocess.run(  # nosec B603
            command, cwd=run_root, env=env, input=raw, check=False
        ).returncode
    if code == 0 and not result_path.is_file():
        print("managed Git dispatcher did not run; run `basicly hooks-build`", file=sys.stderr)
        return 2
    if snapshot_state is not None and code == 0:
        module, state = snapshot_state
        module.publish(state)
    if code == 0 and stage == "pre-push":
        orch_note(root, last="pushing: the pre-push checks passed")
    return code


def _launch(manager: str, stage: str, arguments: list[str]) -> int:
    root = project_root()
    suffix = ".exe" if os.name == "nt" else ""
    binary = root / ".basicly/bin" / f"lefthook{suffix}"
    if not binary.is_file():
        raise MissingRuntimeError(
            "repository-local Lefthook runtime is missing. "
            "Run the repository's pinned basicly command with `hooks-build --runtime-only`, "
            "then `hooks-check`, and retry. In a basicly source checkout, use "
            "`uv run basicly hooks-build --runtime-only` and `uv run basicly hooks-check`."
        )
    env = {**os.environ, "BASICLY_HOOK_ARGS": json.dumps(arguments)}
    agent = manager != "git"
    name = stage if not agent else f"basicly-{manager}-{stage}"
    raw = sys.stdin.buffer.read() if agent or stage == "pre-push" else None
    if stage == "pre-push" and raw is not None:
        env["BASICLY_PUSH_REFS"] = raw.decode("utf-8", "replace")
        if not agent and not adds_commits(root, env["BASICLY_PUSH_REFS"]):
            print(
                "basicly hook: pre-push skipped: the push only deletes refs or adds no commit",
                file=sys.stderr,
            )
            return 0
    if not agent:
        foreign_code = run_foreign_hook(root, arguments, raw)
        if foreign_code:
            return foreign_code
    with tempfile.TemporaryDirectory(prefix="basicly-hook-") as directory:
        snapshot_state, run_root = _snapshot(manager, stage, root, Path(directory), env)
        result_path = Path(directory) / "result.json"
        env["BASICLY_HOOK_RESULT"] = str(result_path)
        command = [str(binary), "run", name, "--no-auto-install", "--no-tty"]
        if arguments:
            command.extend(["--", *arguments])
        proc = subprocess.run(  # nosec B603
            command,
            cwd=run_root,
            env=env,
            input=raw,
            capture_output=agent,
            check=False,
        )
        if not agent:
            return _finish_git(
                (command, run_root, env, raw),
                proc.returncode,
                result_path,
                snapshot_state,
                (stage, root),
            )
        if not result_path.is_file():
            sys.stderr.buffer.write(proc.stdout + proc.stderr)
            print(
                "Lefthook did not produce an agent result; run `basicly hooks-build`",
                file=sys.stderr,
            )
            return 2
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if proc.returncode and not result["code"]:
            sys.stderr.buffer.write(proc.stdout + proc.stderr)
            return 2
        sys.stdout.buffer.write(base64.b64decode(result["stdout"]))
        sys.stderr.buffer.write(base64.b64decode(result["stderr"]))
        return int(result["code"])


def main() -> int:
    try:
        if sys.argv[1:] == ["dispatch"]:
            return dispatch()
        if len(sys.argv) < 3:
            print("use lefthook-runtime.py <git|claude|codex|copilot> <event>", file=sys.stderr)
            return 2
        return launch(sys.argv[1], sys.argv[2], sys.argv[3:])
    except MissingRuntimeError as exc:
        print(f"basicly hook failed: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f"basicly hook failed: {described(exc)}", file=sys.stderr)
        return 2


def described(exc: BaseException) -> str:
    hooks = Path(__file__).resolve().parent
    frames = traceback.extract_tb(exc.__traceback__)
    own = [frame for frame in frames if Path(frame.filename).resolve().parent == hooks] or frames
    place = f" at {Path(own[-1].filename).name}:{own[-1].lineno}" if own else ""
    text = str(exc)
    for private in (str(Path.cwd()), str(Path.home())):
        text = text.replace(private, ".")
    return f"{type(exc).__name__}: {text}{place}" if text else f"{type(exc).__name__}{place}"


if __name__ == "__main__":
    raise SystemExit(main())
