from __future__ import annotations

import hashlib
import os
import shutil
import subprocess  # nosec B404
from dataclasses import dataclass
from pathlib import Path

if os.name == "nt":
    import _winapi


@dataclass(frozen=True)
class Snapshot:
    root: Path
    tree: Path
    index: Path
    before: bytes
    env: dict[str, str]
    original_tree: bytes


def git(root: Path, *arguments: str, env: dict | None = None, data: bytes | None = None) -> bytes:
    return subprocess.run(  # nosec B603 B607
        ["git", *arguments], cwd=root, env=env, input=data, capture_output=True, check=True
    ).stdout


def index_path(root: Path) -> Path:
    path = Path(os.fsdecode(git(root, "rev-parse", "--git-path", "index")).strip())
    return path if path.is_absolute() else root / path


def digest(path: Path) -> bytes:
    return hashlib.sha256(path.read_bytes()).digest()


def link_directory(source: Path, destination: Path) -> None:
    try:
        destination.symlink_to(source, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise ValueError(
                "cannot share a snapshot directory; enable directory symlinks"
            ) from None
        try:
            _winapi.CreateJunction(str(source.resolve()), str(destination))
        except OSError as err:
            raise ValueError(
                "cannot share a snapshot directory; enable symlinks or use a volume "
                "supporting junctions"
            ) from err


def reuse_prepared_environment(snapshot: Path, env: dict[str, str]) -> None:
    if not (snapshot / ".venv").is_dir():
        return
    env["UV_NO_SYNC"] = "1"
    if (snapshot / "uv.lock").is_file():
        subprocess.run(  # nosec B603 B607
            ["uv", "sync", "--check", "--inexact", "--no-install-project", "--locked"],
            cwd=snapshot,
            env=env,
            check=True,
        )


def normalize_checkout(root: Path, paths: list[bytes], env: dict, original_tree: bytes) -> None:
    if os.name != "nt":
        return
    git(
        root,
        "add",
        "--renormalize",
        "--pathspec-from-file=-",
        "--pathspec-file-nul",
        env=env,
        data=b"\0".join(paths) + b"\0",
    )
    if git(root, "write-tree", env=env).strip() != original_tree:
        raise ValueError(
            "snapshot normalization changed staged content; "
            "check line-ending attributes and restage"
        )


def prepare(root: Path, directory: Path) -> Snapshot:
    index = index_path(root)
    before = digest(index)
    temporary_index = directory / "index"
    shutil.copyfile(index, temporary_index)
    snapshot = directory / "tree"
    snapshot.mkdir()
    common = os.fsdecode(git(root, "rev-parse", "--absolute-git-dir")).strip()
    env = {
        **os.environ,
        "GIT_INDEX_FILE": str(temporary_index),
        "GIT_WORK_TREE": str(snapshot),
        "GIT_DIR": common,
        "PYTHONPATH": str(snapshot / "src") + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    original_tree = git(root, "write-tree", env=env).strip()
    env["BASICLY_SNAPSHOT_TREE"] = original_tree.decode("ascii")
    files = git(root, "ls-files", "-z", env=env).split(b"\0")
    changed = git(root, "diff", "--cached", "--name-only", "-z", env=env).split(b"\0")
    if any(Path(os.fsdecode(path)).name.startswith(".env") for path in changed if path):
        raise ValueError("staged dotenv changes cannot enter a hook snapshot")
    paths = [path for path in files if path and not Path(os.fsdecode(path)).name.startswith(".env")]
    git(
        root,
        "checkout-index",
        "--force",
        "--prefix=" + snapshot.as_posix() + "/",
        "-z",
        "--stdin",
        env=env,
        data=b"\0".join(paths) + b"\0",
    )
    normalize_checkout(root, paths, env, original_tree)
    (snapshot / ".git").write_text(f"gitdir: {common}\n", encoding="utf-8")
    untracked = git(root, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0")
    for name in untracked:
        if not name:
            continue
        relative = Path(os.fsdecode(name))
        if relative.name.startswith(".env"):
            continue
        source = root / relative
        destination = snapshot / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination, follow_symlinks=False)
    for name in (".venv", "node_modules", "build/lefthook"):
        source = root / name
        if source.is_dir() and not (snapshot / name).exists():
            (snapshot / name).parent.mkdir(parents=True, exist_ok=True)
            link_directory(source, snapshot / name)
    reuse_prepared_environment(snapshot, env)
    usage = root / ".basicly/usage"
    usage.mkdir(parents=True, exist_ok=True)
    if not (usage / ".gitignore").exists():
        (usage / ".gitignore").write_text("*\n", encoding="utf-8")
    (snapshot / ".basicly").mkdir(exist_ok=True)
    destination = snapshot / ".basicly/usage"
    if not destination.exists():
        link_directory(usage, destination)
    for name in (".basicly/bin",):
        source = root / name
        destination = snapshot / name
        if source.is_dir() and not destination.exists():
            shutil.copytree(source, destination)
    local_config = root / "basicly.local.toml"
    if local_config.is_file() and not (snapshot / local_config.name).exists():
        shutil.copyfile(local_config, snapshot / local_config.name)
    return Snapshot(root, snapshot, temporary_index, before, env, original_tree)


def publish(state: Snapshot) -> None:
    root, snapshot, temporary_index = state.root, state.tree, state.index
    before, env, old = state.before, state.env, state.original_tree
    index = index_path(root)
    if digest(index) != before:
        raise ValueError("Git index changed during hook validation; rerun the commit")
    new = git(snapshot, "write-tree", env=env).strip()
    if new == old:
        return
    changed = git(root, "diff", "--name-only", "-z", os.fsdecode(old), os.fsdecode(new), env=env)
    dirty = set(git(root, "diff", "--name-only", "-z").split(b"\0"))
    lock = index.with_name(index.name + ".lock")
    created = False
    try:
        with lock.open("xb") as handle:
            created = True
            if digest(index) != before:
                raise ValueError("Git index changed during hook validation; rerun the commit")
            handle.write(temporary_index.read_bytes())
            for name in changed.split(b"\0"):
                if not name or name in dirty:
                    continue
                relative = Path(os.fsdecode(name))
                shutil.copyfile(snapshot / relative, root / relative)
        lock.chmod(index.stat().st_mode)
        lock.replace(index)
    finally:
        if created and lock.exists():
            lock.unlink()
