from __future__ import annotations

import json
import math
import subprocess  # nosec B404
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

SCHEMA = "basicly-affected/v1"
MAX_RESPONSE_BYTES = 1024 * 1024


class SnapshotChangedError(ValueError):
    pass


def parse_provider(section: object, checks: list[str]) -> dict[str, Any] | None:
    if section is None:
        return None
    if not isinstance(section, dict) or set(section) - {"command", "checks", "timeout_seconds"}:
        raise ValueError(
            "verify.affected must declare command, checks and optional timeout_seconds"
        )
    command = section.get("command")
    names = section.get("checks")
    timeout = section.get("timeout_seconds", 30)
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(x, str) and x for x in command)
    ):
        raise ValueError("verify.affected.command must be a nonempty argv list")
    if (
        not isinstance(names, list)
        or not names
        or not all(isinstance(x, str) and x in checks for x in names)
        or len(set(names)) != len(names)
    ):
        raise ValueError("verify.affected.checks must name distinct configured checks")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (float, int))
        or not math.isfinite(timeout)
        or not 0 < timeout <= 300
    ):
        raise ValueError(
            "verify.affected.timeout_seconds must be greater than zero and at most 300"
        )
    return {"command": list(command), "checks": list(names), "timeout_seconds": float(timeout)}


def _git(root: Path, *args: str, env: dict[str, str] | None = None) -> bytes:
    return subprocess.run(  # nosec B603 B607
        ["git", *args], cwd=root, env=env, capture_output=True, check=True
    ).stdout


def _path(raw: bytes) -> str:
    value = raw.decode("utf-8")
    parts = value.replace("\\", "/").split("/")
    if (
        not value
        or PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).drive
        or PureWindowsPath(value).root
        or ".." in parts
        or any(part.startswith(".env") for part in parts)
    ):
        raise ValueError("changed path is external or protected")
    return value


def changes(root: Path, env: dict[str, str] | None = None) -> list[dict[str, str]]:
    fields = _git(
        root,
        "diff",
        "--cached",
        "--name-status",
        "--no-ext-diff",
        "-z",
        "--find-renames",
        "HEAD",
        env=env,
    ).split(b"\0")
    if fields.pop() != b"":
        raise ValueError("Git change inventory is not NUL terminated")
    result = []
    index = 0
    while index < len(fields):
        status = fields[index].decode("ascii")
        index += 1
        if not status or status[0] not in "AMDRCT":
            raise ValueError("Git returned an unsupported change status")
        old = _path(fields[index])
        index += 1
        if status[0] in "RC":
            path = _path(fields[index])
            index += 1
            result.append({"status": status, "old_path": old, "path": path})
        elif status == "A":
            result.append({"status": status, "path": old})
        elif status == "D":
            result.append({"status": status, "old_path": old})
        elif status in {"M", "T"}:
            result.append({"status": status, "old_path": old, "path": old})
        else:
            raise ValueError("Git returned an unsupported change status")
    return result


def _request(
    root: Path, names: list[str], snapshot_tree: str | None, env: dict[str, str] | None
) -> dict[str, Any]:
    if not snapshot_tree:
        raise ValueError("selection requires a prepared index snapshot")
    if _git(root, "write-tree", env=env).decode().strip() != snapshot_tree:
        raise ValueError("index snapshot identity changed")
    _git(root, "diff", "--quiet", "--no-ext-diff", env=env)
    prepared = {b".basicly/usage", b".venv", b"node_modules", b"build/lefthook"}
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", "-z", env=env)
    if any(
        name and not (name in prepared and (root / name.decode()).is_symlink())
        for name in untracked.split(b"\0")
    ):
        raise ValueError("untracked inputs prevent a complete index-only scope")
    changed = changes(root, env)
    if not changed:
        raise ValueError("no staged changes; broad verification retained")
    return {
        "schema": SCHEMA,
        "snapshot_tree": snapshot_tree,
        "base_tree": _git(root, "rev-parse", "--verify", "HEAD^{tree}", env=env).decode().strip(),
        "changes": changed,
        "checks": names,
    }


def _response(
    provider: dict[str, Any], root: Path, request: dict, env: dict[str, str] | None
) -> dict:
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        result = subprocess.run(  # nosec B603
            provider["command"],
            cwd=root,
            env=env,
            input=json.dumps(request).encode(),
            stdout=stdout,
            stderr=stderr,
            timeout=provider["timeout_seconds"],
            check=False,
        )
        stdout.seek(0)
        raw = stdout.read(MAX_RESPONSE_BYTES + 1)
        stderr.seek(0)
        errors = stderr.read(MAX_RESPONSE_BYTES + 1)
    usage = root / ".basicly/usage"
    if usage.is_dir():
        (usage / "affected-provider.stdout").write_bytes(raw)
        (usage / "affected-provider.stderr").write_bytes(errors)
    if result.returncode:
        raise ValueError(f"provider exited with status {result.returncode}")
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("provider response exceeds one MiB")
    response = json.loads(raw)
    if not isinstance(response, dict) or set(response) != set(request) | {
        "complete",
        "selected",
        "reasons",
        "unverified",
    }:
        raise ValueError("provider response has an unsupported schema")
    if any(response.get(key) != value for key, value in request.items()):
        raise ValueError("provider response does not match the snapshot request")
    if response["complete"] is not True or response["unverified"] != []:
        raise ValueError("provider did not establish complete affected scope")
    selected = response["selected"]
    if (
        not isinstance(selected, list)
        or not all(isinstance(x, str) and x in request["checks"] for x in selected)
        or len(set(selected)) != len(selected)
    ):
        raise ValueError("provider selected unknown or duplicate checks")
    reasons = response["reasons"]
    if (
        not isinstance(reasons, dict)
        or set(reasons) != set(request["checks"])
        or not all(isinstance(value, str) and value.strip() for value in reasons.values())
    ):
        raise ValueError("provider must explain every scoped check")
    return response


def select(
    root: Path,
    provider: dict[str, Any],
    names: list[str],
    *,
    snapshot_tree: str | None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    scoped = [name for name in names if name in provider["checks"]]
    plan: dict[str, Any] = {
        "provider": provider["command"],
        "selected": list(names),
        "reasons": {},
        "fallback": "",
        "snapshot_tree": snapshot_tree,
        "base_tree": "",
        "unverified": [],
        "invalid_snapshot": False,
    }
    if not scoped:
        return plan
    try:
        request = _request(root, scoped, snapshot_tree, env)
        plan["base_tree"] = request["base_tree"]
        plan["request"] = request
        plan["diagnostics"] = {
            "stdout": ".basicly/usage/affected-provider.stdout",
            "stderr": ".basicly/usage/affected-provider.stderr",
            "limit_bytes": MAX_RESPONSE_BYTES + 1,
        }
        try:
            response = _response(provider, root, request, env)
        finally:
            try:
                after = _request(root, scoped, snapshot_tree, env)
            except (OSError, ValueError, IndexError, subprocess.SubprocessError) as exc:
                raise SnapshotChangedError(
                    "provider changed snapshot inputs; rerun verification"
                ) from exc
            if after != request:
                raise SnapshotChangedError("provider changed snapshot inputs; rerun verification")
        plan.update(
            selected=[name for name in names if name not in scoped or name in response["selected"]],
            reasons=response["reasons"],
        )
    except SnapshotChangedError as exc:
        plan.update(invalid_snapshot=True, fallback=str(exc), unverified=list(names))
    except subprocess.TimeoutExpired:
        plan["fallback"] = "provider timed out; broad verification retained"
    except (OSError, subprocess.CalledProcessError) as exc:
        plan["fallback"] = (
            f"provider or Git unavailable ({type(exc).__name__}); broad verification retained"
        )
    except (ValueError, IndexError, UnicodeError) as exc:
        plan["fallback"] = f"{exc}; broad verification retained"
    return plan
